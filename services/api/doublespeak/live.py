"""Live call feed: per-session verdict stabiliser wiring + a bounded, read-only Server-Sent-Events broadcast.

The page only DISPLAYS. It cannot control a session and never sees audio, tokens or session ids. The stabiliser only
changes what the live stream SHOWS; it never edits a stored tier and the scorer/thresholds are untouched.

GET /live/events  (text/event-stream; loopback client + allowed Origin/Host only; max 4 subscribers -> 429)
  Each frame is `data: <json>` followed by a blank line. Event schema (field names are a contract with the page):

  {"type":"state","active":bool,"source":str,"elapsed_s":num,"listening":bool}
      Sent on connect, on every change (session start/end) and every 5 s as a keep-alive. `source` is a short label
      the listener gives ("tap", "file", "stream" by default); "" when inactive. `elapsed_s` is AUDIO time received
      by the newest live session. `listening` is True while a session is receiving audio.
  {"type":"verdict","tick":int,"elapsed_s":num,"verdict":<Verdict.to_dict()>,"stable":{...}}
      One per analysis tick of any live session. `verdict` is the RAW per-window verdict (exactly /analyze's shape,
      transcript of the window included: loopback only, never persisted). `stable` is the displayed, smoothed answer:
        {"tier": "warming_up|human|unsure|ai_disclosed|ai_undisclosed|scam",
         "state": "warming|steady|escalated|latched",
         "alert": "none|amber|red",
         "since_s": num,              # seconds (audio clock) since tier/state/alert last changed
         "reasons": [str, ...]}       # <= 4 fixed plain sentences, never caller text
  {"type":"ended","reason":str}
      A session stopped (stop|kill|disconnect|heartbeat_timeout|max_length|deleted|panic|ended ...).

POST /live/dismiss (loopback) acknowledges a latched red alert on every live session -> {"dismissed": n}.
The same is available on the stream as the WS control message {"type":"dismiss"}.

Bounds and privacy: each subscriber has a 64-event queue that drops its OLDEST event when full; at most 4 subscribers.
Nothing is persisted. The hub holds no audio and no history: only the set of live sessions, wiped when they end.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncIterator, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from . import personal
from .signals import shadow
from .stabiliser import INTENT_FAMILIES, RawTick, Stabiliser

router = APIRouter()

MAX_SUBSCRIBERS = 4
QUEUE_MAX = 64
STATE_EVERY_S = 5.0
LOOPBACK_CLIENTS = {"127.0.0.1", "::1", "localhost", "testclient"}   # "testclient" is Starlette's TestClient only

ALERT_SENTENCES = {
    "corroborated_intent": "Several scam warning signs showed up together, including a request for money or a code.",
    "high_p_scam": "The call has sounded like a scam for several checks in a row.",
    "uncorroborated_scam": "Part of this call sounds like a scam. Do not share money, codes or passwords.",
    "sustained_ai_evidence": "The voice has sounded automated for a while.",
}
WARMING_SENTENCE = "Still listening: not enough speech yet to judge."


def clean_source(s: Any) -> str:
    """A listener-supplied label ("tap", "file"): short, lowercase, no free text."""
    if not isinstance(s, str):
        return "stream"
    s = re.sub(r"[^a-z0-9 ._-]", "", s.lower())[:24].strip()
    return s or "stream"


def raw_tick(d: dict, t: float, speech_s: float) -> RawTick:
    tells = d.get("tells") or []
    families = {x.get("name") for x in tells
                if x.get("family") == "intent" and x.get("applicable", True) and float(x.get("score", 0)) >= 0.5
                and x.get("name") in INTENT_FAMILIES}
    return RawTick(t=t, raw_tier=d.get("tier", "unsure"), p_ai=float(d.get("p_ai") or 0),
                   p_scam=float(d.get("p_scam") or 0), confidence=float(d.get("confidence") or 0),
                   disclosed_ai=bool(d.get("disclosed_ai")), intent_families=families,
                   speech_seconds=max(0.0, speech_s), words=len((d.get("transcript") or "").split()), degraded=[])


class StableTracker:
    """One per live session: Stabiliser + the `stable` object. Pure; time is the audio clock."""

    def __init__(self) -> None:
        self.stab = Stabiliser()
        self._key: tuple | None = None
        self._since_t = 0.0
        self.last: dict | None = None
        self._persist: dict[str, list[float]] = {"pella": [], "hf": []}   # SHADOW: neural scores over the call, never fed back
        self.pcall = personal.CallTracker()      # numbers only; read by the personal layer, never by the stabiliser
        self.personal_alert: str | None = None   # None unless DOUBLESPEAK_PERSONAL=1 AND the user opted in

    def _shadow_persistence(self, d: dict) -> None:
        """SHADOW only: call-level persistence of the per-window neural scores, attached to this tick's egress.context.shadow.
        Runs after the stabiliser has consumed the tick; nothing here is read by it or by any tier/score."""
        try:
            ctx = (d.get("egress") or {}).get("context")
            if not isinstance(ctx, dict):
                return
            for w in ctx.get("voice_windows") or []:
                for voter, buf in self._persist.items():
                    if voter in w:
                        buf.append(float(w[voter]))
                        del buf[:-200]
            sh = ctx.setdefault("shadow", {})
            for voter, buf in self._persist.items():
                for k, (v, ev) in shadow.persistence(buf).items():
                    sh[f"call_persist_{voter}_{k}"] = shadow._pack(v, ev)
        except Exception:  # noqa: BLE001  shadow must never break a tick
            pass

    def observe(self, d: dict, t0: float, t1: float) -> dict:
        sv = self.stab.update(raw_tick(d, t1, t1 - t0))
        alert = sv.alert or "none"
        if sv.shown_tier == "warming_up" and alert != "red":
            state = "warming"
        elif self.stab.latched:
            state = "latched"
        elif alert == "amber" or sv.shown_tier in ("scam", "ai_undisclosed"):
            state = "escalated"
        else:
            state = "steady"
        key = (sv.shown_tier, state, alert)
        if key != self._key:
            self._key, self._since_t = key, t1
        reasons = [ALERT_SENTENCES[r] for r in sv.alert_reason if r in ALERT_SENTENCES]
        if state == "warming":
            reasons = [WARMING_SENTENCE]
        for r in d.get("reasons") or []:
            if isinstance(r, str) and r not in reasons and len(reasons) < 4:
                reasons.append(r)
        self.last = {"tier": sv.shown_tier, "state": state, "alert": alert,
                     "since_s": round(max(0.0, t1 - self._since_t), 2), "reasons": reasons[:4]}
        self._shadow_persistence(d)
        self._personal(d)
        return self.last

    def _personal(self, d: dict) -> None:
        """Opt-in notification sensitivity. Runs AFTER `self.last` is final and only sets `personal_alert`; it can never
        change `stable` (tier, state, alert, reasons). Any failure leaves it None, i.e. the event is unchanged."""
        try:
            self.personal_alert = personal.LAYER.on_tick(self.pcall, d, self.last["alert"], self.last["tier"])
        except Exception:  # noqa: BLE001
            self.personal_alert = None

    def dismiss(self) -> bool:
        return self.stab.dismiss(None)

    def wipe(self) -> None:
        self.stab.reset()
        self._key, self.last = None, None
        self._persist = {"pella": [], "hf": []}
        self.pcall = personal.CallTracker()
        self.personal_alert = None


class Hub:
    """Fan-out of live events to at most MAX_SUBSCRIBERS read-only listeners. Event-loop only (no locks needed)."""

    def __init__(self) -> None:
        self.subs: set[asyncio.Queue] = set()
        self.sessions: dict[str, Any] = {}

    # --- subscribers ---------------------------------------------------------------------------------------
    def subscribe(self) -> "asyncio.Queue | None":
        if len(self.subs) >= MAX_SUBSCRIBERS:
            return None
        q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
        self.subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subs.discard(q)

    def publish(self, ev: dict) -> None:
        for q in list(self.subs):
            while q.full():                          # drop-oldest: a slow page never blocks or grows memory
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    break
            q.put_nowait(ev)

    # --- session lifecycle (called from stream.py / session.py on the event loop) -----------------------------
    def state(self) -> dict:
        live = [s for s in self.sessions.values() if not s.closed]
        if not live:
            return {"type": "state", "active": False, "source": "", "elapsed_s": 0.0, "listening": False}
        s = live[-1]
        return {"type": "state", "active": True, "source": s.source, "elapsed_s": round(s.received_s, 1),
                "listening": True}

    def session_started(self, s: Any) -> None:
        self.sessions[s.id] = s
        self.publish(self.state())

    def session_ended(self, s: Any, reason: str) -> None:
        if self.sessions.pop(s.id, None) is None:
            return
        try:
            personal.LAYER.on_call_end(getattr(getattr(s, "stab", None), "pcall", None))
        except Exception:  # noqa: BLE001
            pass
        self.publish({"type": "ended", "reason": reason})
        self.publish(self.state())

    def on_tick(self, s: Any, d: dict, stable: dict, tick: int, personal_alert: str | None = None) -> None:
        if s.id in self.sessions and not s.closed:
            ev = {"type": "verdict", "tick": tick, "elapsed_s": round(s.received_s, 1), "verdict": d, "stable": stable}
            if personal_alert is not None:           # only present when the user opted in: otherwise the event is unchanged
                ev["personal_alert"] = personal_alert
            self.publish(ev)

    def dismiss_all(self) -> int:
        return sum(1 for s in list(self.sessions.values()) if s.stab.dismiss())

    def reset(self) -> None:
        """Wipe everything (tests)."""
        self.sessions.clear()
        self.subs.clear()


HUB = Hub()


def _frame(ev: dict) -> bytes:
    return b"data: " + json.dumps(ev, separators=(",", ":")).encode() + b"\n\n"


async def events(q: asyncio.Queue, hub: Hub = HUB, is_gone: Callable[[], Any] | None = None,
                 state_every: float = STATE_EVERY_S) -> AsyncIterator[bytes]:
    """Frames for one subscriber: current state first, then queued events, a state keep-alive every `state_every`."""
    try:
        yield _frame(hub.state())
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), state_every)
            except asyncio.TimeoutError:
                ev = hub.state()
                if is_gone is not None and await is_gone():
                    return
            yield _frame(ev)
    finally:
        hub.unsubscribe(q)


def _loopback_only(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in LOOPBACK_CLIENTS:
        raise HTTPException(403, "loopback only")


@router.get("/live/events")
async def live_events(request: Request) -> StreamingResponse:
    _loopback_only(request)
    q = HUB.subscribe()
    if q is None:
        raise HTTPException(429, "too many live listeners")
    return StreamingResponse(events(q, is_gone=request.is_disconnected), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("/live/dismiss")
async def live_dismiss(request: Request) -> dict:
    _loopback_only(request)
    return {"dismissed": HUB.dismiss_all()}
