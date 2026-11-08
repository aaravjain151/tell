"""Live streaming sessions: RAM-only ring, audio-clock tick scheduler, token registry. No I/O, no network.

Flow: POST /session -> Session(state=pending) + single-use token (60 s). WebSocket hello redeems the token ->
state=live, ring allocated. Each time `hop_s` of new audio has arrived and no job is in flight, `maybe_tick`
copies the last `window_s` out of the ring and runs pipeline.analyze on it in the shared worker thread. One job in
flight per session; ticks that come due meanwhile are counted as skipped and the next window simply covers the
newest audio (the oldest unanalysed audio is dropped and counted in `dropped_ms`). Only the latest verdict matters.

The tick clock is the AUDIO clock (samples received), not wall time, so replay at --speed 4 behaves like a real call
and tests need no sleeps. Heartbeat/hello timeouts are wall-clock and live in stream.py.

Final flush (`finish`, graceful ends only: stop, normal close, max length): no new ticks start; a job already in
flight is allowed to finish and emit; then, if at least FINAL_MIN_NEW_S of audio arrived after the end of the last
SCORED window and it is not silence, ONE more analysis runs over the last `window_s` up to the end of received audio
and goes through the same stabiliser. All of it is bounded by `final_flush_s` (<= TELL_ANALYZE_TIMEOUT_S); past that
the session ends without it (logged). Kill, panic, DELETE, heartbeat timeout and errors never flush: immediate wipe.

Privacy: audio exists only in `Ring` (zeroed on close) and in the one window copy handed to the worker, which lives
until that analysis returns (bounded by TELL_ANALYZE_TIMEOUT_S plus thread end). Pipeline runs with
ephemeral=True so TELL_DEBUG_SAVE and the opt-in history file are bypassed for streams.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import secrets
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Callable

import numpy as np

from . import env as _env
from . import limits, live, pipeline
from .ring import SR, Ring

MAX_SESSIONS = 2
RING_DEFAULT_S, RING_CAP_S = 30.0, 120.0
WINDOW_S, HOP_S = 10.0, 3.0
HEARTBEAT_S, HELLO_TIMEOUT_S, TOKEN_TTL_S = 15.0, 5.0, 60.0
MAX_SESSION_S = 7200.0
MAX_FRAME_BYTES = 128 * 1024        # 4 s of PCM16 @ 16 kHz; clients send ~20-100 ms frames
MAX_TEXT_BYTES = 4096
SIDES = ("far", "near", "mix")
# side="mix" carries both speakers (e.g. a speakerphone capture): the acoustic tells then measure a blend, so the
# DISPLAYED confidence is capped here. p_ai / p_scam / tier are untouched (scorer.py is not edited).
MIX_CONF_CAP = 0.6
LAG_WARN_FACTOR = 2.0               # warn "lagging" when a verdict is more than 2 hops behind live audio
WARN_MIN_GAP_S = 5.0
# Final flush on a graceful end: the unscored tail must hold this much new audio, with at least FINAL_MIN_VOICED_S of
# 30 ms frames above VOICED_RMS (about -50 dBFS), or it is skipped. FINAL_FLUSH_S bounds the whole flush.
FINAL_MIN_NEW_S, FINAL_MIN_VOICED_S, VOICED_RMS = 2.0, 0.5, 0.003
FINAL_FLUSH_S = 6.0

log = logging.getLogger("tell.stream")
_now = time.monotonic              # patched in tests
_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stream")   # one analysis at a time, all sessions

Emit = Callable[[dict], Awaitable[None]]


def _env_f(name: str, default: float, lo: float, hi: float) -> float:
    try:
        v = float(_env.get(name, ""))
    except ValueError:
        return default
    return min(max(v, lo), hi) if v > 0 else default


def params() -> dict:
    """Effective stream parameters, read from env at call time (tests and the UI both see the same numbers)."""
    window = _env_f("TELL_STREAM_WINDOW_S", WINDOW_S, 0.05, 60)
    hop = min(_env_f("TELL_STREAM_HOP_S", HOP_S, 0.05, 60), window)   # hop > window would skip audio by design
    ring = max(_env_f("TELL_STREAM_RING_S", RING_DEFAULT_S, 0.05, RING_CAP_S), window)
    return {"sample_rate": SR, "format": "pcm_s16le", "hop_s": hop, "window_s": window, "ring_s": ring,
            "heartbeat_s": _env_f("TELL_STREAM_HEARTBEAT_S", HEARTBEAT_S, 0.05, 120),
            "hello_timeout_s": _env_f("TELL_STREAM_HELLO_TIMEOUT_S", HELLO_TIMEOUT_S, 0.05, 30),
            "token_ttl_s": _env_f("TELL_STREAM_TOKEN_TTL_S", TOKEN_TTL_S, 0.05, 600),
            "max_session_s": _env_f("TELL_STREAM_MAX_SESSION_S", MAX_SESSION_S, 0.05, MAX_SESSION_S),
            "final_flush_s": _env_f("TELL_STREAM_FINAL_S", FINAL_FLUSH_S, 0.05, 60),
            "max_frame_bytes": MAX_FRAME_BYTES, "max_sessions": MAX_SESSIONS, "sides": list(SIDES)}


def pcm16_to_float(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype="<i2").astype(np.float32) / 32768.0


def _wav_bytes(x: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def _analyze_window(x: np.ndarray) -> dict:
    """Worker thread. In-memory WAV -> the existing pipeline, ephemeral (no debug save, no history)."""
    return pipeline.analyze(_wav_bytes(x), None, ephemeral=True).to_dict()


class Full(Exception):
    pass


class Session:
    def __init__(self, sid: str, p: dict) -> None:
        self.id = sid
        self.p = p
        self.state = "pending"            # pending -> live -> closed
        self.side = "far"
        self.source = "stream"            # short label for the live feed (listener-supplied, sanitised)
        self.stab = live.StableTracker()  # display-only smoothing; never touches a stored tier
        self.ring: Ring | None = None
        self.created = _now()
        self.ticks = 0                    # verdicts sent
        self.seq = 0
        self.dropped_ms = 0
        self.skipped_ticks = 0
        self.last_lag_s = 0.0
        self.last_job_s = 0.0
        self._received = 0                # samples received (survives wipe)
        self._last_tick = 0               # sample count at the last dispatch
        self._analysed_end = 0
        self._scored_end = 0              # sample count at the end of the last window whose verdict was emitted
        self._finishing = False           # graceful end in progress: no new ticks
        self._inflight = False
        self._overload = False
        self._last_warn: dict[str, float] = {}
        self._task: "asyncio.Task | None" = None
        self._wake: "asyncio.Event | None" = None
        self._loop: "asyncio.AbstractEventLoop | None" = None
        self.close_reason = ""

    @property
    def closed(self) -> bool:
        return self.state == "closed"

    @property
    def inflight(self) -> bool:
        return self._inflight

    def activate(self, side: str, source: str = "stream") -> None:
        self.side = side
        self.source = live.clean_source(source)
        self.ring = Ring(self.p["ring_s"])
        self.state = "live"

    def attach(self, loop: "asyncio.AbstractEventLoop", wake: "asyncio.Event") -> None:
        self._loop, self._wake = loop, wake
        if self.closed:
            wake.set()

    def close(self, reason: str) -> bool:
        """Wipe and mark closed. Safe from any thread, idempotent. Returns True the first time."""
        if self.state == "closed":
            return False
        self.state = "closed"
        self.close_reason = reason
        self.stab.wipe()
        if self.ring is not None:
            self.ring.wipe()
        if self._loop is not None and self._wake is not None:
            try:
                self._loop.call_soon_threadsafe(self._wake.set)
            except RuntimeError:          # loop already closed
                pass
        return True

    def cancel_job(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()

    # --- audio in ---------------------------------------------------------------------------------------------
    def ingest(self, pcm: bytes) -> int:
        """Append one PCM16 frame to the ring. O(frame), never waits. Returns samples that fell out of the ring."""
        if self.ring is None or self.closed:
            return 0
        x = pcm16_to_float(pcm)
        self._received += len(x)
        return self.ring.write(x)

    @property
    def received_s(self) -> float:
        return self._received / SR

    # --- ticks ------------------------------------------------------------------------------------------------
    def due(self) -> bool:
        return (not self.closed and self._received - self._last_tick >= int(self.p["hop_s"] * SR))

    def maybe_tick(self, emit: Emit) -> bool:
        """Start an analysis if a hop of new audio is waiting and none is in flight. Must run on the event loop."""
        if not self.due() or self._inflight or self.ring is None or self._finishing:
            return False
        hop = int(self.p["hop_s"] * SR)
        missed = (self._received - self._last_tick) // hop - 1
        x = self.ring.last(self.p["window_s"])
        if len(x) == 0:
            return False
        end = self._received
        start = end - len(x)
        gap = max(0, start - self._analysed_end)
        if gap:                                        # audio nobody analysed: drop the oldest, count it
            self.dropped_ms += int(1000 * gap / SR)
            self._overload = True
        if missed > 0:
            self.skipped_ticks += missed
            self._overload = True
        self._last_tick, self._analysed_end = end, end
        self._inflight = True
        self.seq += 1
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._job(x, start / SR, end / SR, end, self.seq, emit))
        return True

    async def _job(self, x: np.ndarray, t0: float, t1: float, end_samples: int, seq: int, emit: Emit) -> None:
        loop = asyncio.get_running_loop()
        started = _now()
        fut = loop.run_in_executor(_EXEC, _analyze_window, x)

        def _done(f: "asyncio.Future[Any]") -> None:      # inflight clears only when the thread really ended
            if not f.cancelled():
                f.exception()
            self._inflight = False

        fut.add_done_callback(_done)
        del x
        try:
            d = await asyncio.wait_for(asyncio.shield(fut), limits.analyze_timeout_s())
        except asyncio.TimeoutError:
            await self._warn("overloaded", emit)
            return
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            limits._log_failure("stream analysis", e)
            if not self.closed:
                await emit({"type": "error", "code": "analysis_failed"})
            return
        if self.closed:                                    # wiped while analysing: drop the result
            return
        await self._publish(d, seq, t0, t1, end_samples, started, emit)
        if self._finishing:                                # graceful end: finish() decides about the tail
            return
        if self.last_lag_s > LAG_WARN_FACTOR * self.p["hop_s"]:
            await self._warn("lagging", emit)
        if self._overload:
            self._overload = False
            await self._warn("overloaded", emit)
        self.maybe_tick(emit)                              # catch up if a hop is already waiting

    async def _publish(self, d: dict, seq: int, t0: float, t1: float, end_samples: int, started: float, emit: Emit,
                       tail: bool = False) -> None:
        """One verdict through the stabiliser to this client and the live feed (same path for ticks and the tail)."""
        self.last_job_s = _now() - started
        self.last_lag_s = max(0.0, (self._received - end_samples) / SR)
        self.ticks += 1
        self._scored_end = max(self._scored_end, end_samples)
        msg = self.verdict_message(d, seq, t0, t1)
        if tail:                                 # the final flush verdict; absent on ordinary ticks (bit-identical)
            msg["tail"] = True
        msg["stable"] = self.stab.observe(d, t0, t1)
        pa = self.stab.personal_alert
        if pa is not None:                       # opt-in only; absent otherwise so the message is bit-identical
            msg["personal_alert"] = pa
        live.HUB.on_tick(self, d, msg["stable"], self.ticks, pa, tail=tail)
        await emit(msg)

    # --- graceful end ---------------------------------------------------------------------------------------------
    def flush_budget_s(self) -> float:
        return min(float(self.p.get("final_flush_s", FINAL_FLUSH_S)), limits.analyze_timeout_s())

    def _tail_window(self) -> "tuple[np.ndarray | None, str]":
        """The last window up to the end of received audio, or why there is nothing worth scoring."""
        new = self._received - self._scored_end
        if self.ring is None or self.closed:
            return None, "closed"
        if new <= 0:
            return None, "no_new_audio"
        if new < int(FINAL_MIN_NEW_S * SR):
            return None, "covered"
        x = self.ring.last(self.p["window_s"])
        tail = x[-min(new, len(x)):]
        f = int(0.03 * SR)
        n = len(tail) // f
        if n == 0:
            return None, "covered"
        rms = np.sqrt(np.mean(np.square(tail[:n * f].reshape(n, f), dtype=np.float64), axis=1))
        if int(np.count_nonzero(rms >= VOICED_RMS)) * f < int(FINAL_MIN_VOICED_S * SR):
            return None, "silence"
        return x, ""

    async def finish(self, emit: Emit) -> str:
        """Graceful end: score the unscored tail once, BEFORE the caller wipes. Returns the outcome:
        scored | covered | no_new_audio | silence | timeout | failed | closed. Never raises (except cancellation)."""
        self._finishing = True
        loop = asyncio.get_running_loop()
        budget = self.flush_budget_s()
        deadline = loop.time() + budget
        task = self._task
        if task is not None and not task.done():           # let the in-flight tick land (it is a real verdict)
            await asyncio.wait({task}, timeout=max(0.0, deadline - loop.time()))
            if not task.done():
                log.warning("final tail skipped: in-flight analysis exceeded the %.1f s flush budget", budget)
                return "timeout"
        x, why = self._tail_window()
        if x is None:
            return why
        end = self._received
        start = end - len(x)
        self.seq += 1
        seq = self.seq
        started = _now()
        fut = loop.run_in_executor(_EXEC, _analyze_window, x)
        fut.add_done_callback(lambda f: f.cancelled() or f.exception())
        del x
        left = deadline - loop.time()
        try:
            if left <= 0:
                raise asyncio.TimeoutError
            d = await asyncio.wait_for(asyncio.shield(fut), left)
        except asyncio.TimeoutError:
            log.warning("final tail skipped: analysis exceeded the %.1f s flush budget", budget)
            return "timeout"
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            limits._log_failure("final tail analysis", e)
            return "failed"
        if self.closed:                                    # panic / DELETE while flushing: drop it
            return "closed"
        await self._publish(d, seq, start / SR, end / SR, end, started, emit, tail=True)
        return "scored"

    async def _warn(self, code: str, emit: Emit) -> None:
        t = _now()
        if self.closed or t - self._last_warn.get(code, -1e9) < WARN_MIN_GAP_S:
            return
        self._last_warn[code] = t
        await emit({"type": "warn", "code": code})

    def verdict_message(self, d: dict, seq: int, t0: float, t1: float) -> dict:
        conf = float(d.get("confidence", 0.0))
        capped = self.side == "mix" and conf > MIX_CONF_CAP
        if capped:
            conf = MIX_CONF_CAP
        degraded = [t["name"] for t in d.get("tells", []) if not t.get("applicable", True) and t.get("name") != "ai_denial"]
        return {"type": "verdict", "seq": seq, "t": round(t1, 2), "window": [round(t0, 2), round(t1, 2)],
                "tier": d.get("tier"), "p_ai": d.get("p_ai"), "p_scam": d.get("p_scam"),
                "confidence": round(conf, 3), "confidence_capped": capped, "headline": d.get("headline", ""),
                "degraded": degraded, "lag_s": round(self.last_lag_s, 2), "side": self.side,
                "dropped_ms": self.dropped_ms, "verdict": self.client_verdict(d, conf, capped)}

    @staticmethod
    def client_verdict(d: dict, conf: float, capped: bool) -> dict:
        """The full per-window verdict for THIS session's own client (additive; same shape as /analyze and the live feed),
        so a companion app never has to read the global /live/events feed, which carries every session. On side=mix
        the confidence cap is applied here too, so `scores` never claims more than the top-level field."""
        v = dict(d)
        if capped:
            v["confidence"] = round(conf, 3)
            sc = v.get("scores")
            if isinstance(sc, dict):
                sc = dict(sc)
                sc["confidence"] = min(int(sc.get("confidence") or 0), int(round(MIX_CONF_CAP * 100)))
                if sc.get("confidence_label") == "high":
                    sc["confidence_label"] = "medium"
                v["scores"] = sc
        return v

    def lag_report(self) -> dict:
        return {"lag_s": round(self.last_lag_s, 2), "last_job_s": round(self.last_job_s, 2),
                "skipped_ticks": self.skipped_ticks, "dropped_ms": self.dropped_ms, "inflight": self._inflight}


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8", "replace")).hexdigest()


class Registry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}
        self._tokens: dict[str, tuple[str, float]] = {}     # sha256(token) -> (session id, expiry)

    def _reap(self) -> None:
        t = _now()
        for h, (sid, exp) in list(self._tokens.items()):
            if exp <= t:
                del self._tokens[h]
                s = self._sessions.get(sid)
                if s is not None and s.state == "pending":
                    s.close("token_expired")
                    del self._sessions[sid]

    def create(self) -> tuple[Session, str]:
        p = params()
        with self._lock:
            self._reap()
            if len(self._sessions) >= p["max_sessions"]:
                raise Full()
            sid = secrets.token_urlsafe(16)
            token = secrets.token_urlsafe(32)               # 256 random bits
            s = Session(sid, p)
            self._sessions[sid] = s
            self._tokens[_digest(token)] = (sid, _now() + p["token_ttl_s"])
            return s, token

    def redeem(self, token: str) -> Session | None:
        """Single use: the token is consumed whether or not it was still valid."""
        with self._lock:
            ent = self._tokens.pop(_digest(token), None)
            if ent is None:
                return None
            sid, exp = ent
            s = self._sessions.get(sid)
            if s is None or s.state != "pending" or exp <= _now():
                if s is not None and s.state == "pending":
                    s.close("token_expired")
                    del self._sessions[sid]
                return None
            return s

    def discard(self, sid: str) -> None:
        with self._lock:
            self._sessions.pop(sid, None)

    def close(self, sid: str, reason: str) -> bool:
        with self._lock:
            s = self._sessions.pop(sid, None)
        if s is None:
            return False
        s.close(reason)
        return True

    def panic(self) -> int:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._tokens.clear()
        for s in sessions:
            s.close("panic")
        return len(sessions)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)


REGISTRY = Registry()
