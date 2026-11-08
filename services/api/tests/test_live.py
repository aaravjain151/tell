"""Live feed: stabiliser wiring (fake scorer), SSE event schema and bounds, dismiss, wipe. No audio devices."""
import asyncio
import contextlib
import json
import queue as _q

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tell import live, pipeline, session as sm
from tell.main import app
from tell.stabiliser import POLICY_VERSION  # noqa: F401  (import check)

ORIGIN = {"Origin": "http://localhost:5173"}
SR = 16_000
WORDS = " ".join(["word"] * 30)


def vd(tier="human", p_scam=0.1, families=(), words=WORDS, disclosed=False):
    tells = [{"name": n, "family": "intent", "score": 0.9, "weight": 1.0, "evidence": "x", "applicable": True}
             for n in families]
    return {"tier": tier, "p_ai": 0.1, "p_scam": p_scam, "confidence": 0.8, "disclosed_ai": disclosed,
            "headline": tier, "advice": "", "tells": tells, "reasons": ["fixed sentence"], "transcript": words,
            "thresholds_version": "t", "egress": {}, "signature": "", "cost": {}, "model_notes": []}


# ----------------------------------------------------------------------- tracker: scripted tick sequences
def run(seq, hop=3.0, win=10.0):
    tr = live.StableTracker()
    out = []
    for i, d in enumerate(seq):
        t1 = (i + 1) * hop
        out.append(tr.observe(d, max(0.0, t1 - win), t1))
    return out


def test_friendly_call_turns_into_scam_alerts_within_a_few_ticks():
    seq = [vd("human")] * 12 + [vd("scam", 0.9, ["urgency"])] * 2 + [vd("scam", 0.95, ["urgency", "payment_rails"])] * 3
    out = run(seq)
    assert all(o["state"] in ("warming", "steady") and o["alert"] == "none" for o in out[:12])
    assert out[1]["state"] == "warming" and out[1]["tier"] == "warming_up"
    assert out[11]["state"] == "steady" and out[11]["tier"] == "human"
    first = next(i for i, o in enumerate(out) if o["alert"] != "none")
    assert 12 <= first <= 14                                  # within a few ticks of the turn
    assert out[-1]["alert"] == "red" and out[-1]["state"] == "latched" and out[-1]["tier"] == "scam"
    assert 1 <= len(out[-1]["reasons"]) <= 4 and all(isinstance(r, str) for r in out[-1]["reasons"])


def test_long_human_call_with_blips_never_alarms():
    seq = []
    for i in range(400):                                      # 20 minutes of ticks
        seq.append(vd("scam", 0.9) if i in (100, 250) else vd("unsure", 0.2) if i % 37 == 0 else vd("human"))
    out = run(seq)
    assert all(o["alert"] == "none" for o in out)
    assert all(o["state"] != "latched" for o in out)
    assert out[-1]["tier"] == "human" and out[-1]["state"] == "steady"


def test_red_stays_latched_until_dismissed_then_not_stale_relatch():
    tr = live.StableTracker()
    t = 0.0
    for d in [vd()] * 4 + [vd("scam", 0.9, ["urgency", "payment_rails"])] * 2:
        t += 3
        s = tr.observe(d, t - 10, t)
    assert s["alert"] == "red"
    for _ in range(10):
        t += 3
        s = tr.observe(vd(), t - 10, t)
        assert (s["alert"], s["state"]) == ("red", "latched")
    assert tr.dismiss() is True
    t += 3
    s = tr.observe(vd("scam", 0.9), t - 10, t)
    assert s["alert"] == "none"


def test_since_s_counts_from_last_change():
    out = run([vd()] * 8)
    steady = [o for o in out if o["state"] == "steady"]
    assert steady[0]["since_s"] == 0.0 and steady[-1]["since_s"] == 3.0 * (len(steady) - 1)


# ----------------------------------------------------------------------- hub bounds
def test_subscriber_cap_and_drop_oldest():
    hub = live.Hub()
    qs = [hub.subscribe() for _ in range(live.MAX_SUBSCRIBERS)]
    assert all(q is not None for q in qs) and hub.subscribe() is None
    for i in range(live.QUEUE_MAX + 40):
        hub.publish({"type": "ended", "reason": str(i)})
    q = qs[0]
    assert q.qsize() == live.QUEUE_MAX
    first = q.get_nowait()
    assert first["reason"] == str(40)                          # the oldest 40 were dropped
    hub.unsubscribe(qs[1])
    assert hub.subscribe() is not None


def test_events_generator_frames_and_keepalive():
    async def go():
        hub = live.Hub()
        q = hub.subscribe()
        gen = live.events(q, hub, state_every=0.05)
        first = json.loads((await gen.__anext__())[6:])
        assert first == {"type": "state", "active": False, "source": "", "elapsed_s": 0.0, "listening": False}
        hub.publish({"type": "ended", "reason": "stop"})
        raw = await gen.__anext__()
        assert raw.startswith(b"data: ") and raw.endswith(b"\n\n")
        assert json.loads(raw[6:]) == {"type": "ended", "reason": "stop"}
        ka = json.loads((await gen.__anext__())[6:])           # nothing queued -> state keep-alive
        assert ka["type"] == "state"
        await gen.aclose()
        assert not hub.subs                                    # unsubscribed on close
    asyncio.run(go())


# ----------------------------------------------------------------------- end to end through the WS (fake scorer)
@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("TELL_WARMUP", "0")
    monkeypatch.setenv("TELL_STREAM_WINDOW_S", "10")
    monkeypatch.setenv("TELL_STREAM_HOP_S", "1")
    monkeypatch.setenv("TELL_STREAM_RING_S", "10")
    for k in ("TELL_CORS_ORIGINS", "TELL_ALLOWED_HOSTS", "TELL_ANALYZE_TIMEOUT_S"):
        monkeypatch.delenv(k, raising=False)
    sm.REGISTRY.panic()
    live.HUB.reset()
    yield
    sm.REGISTRY.panic()
    live.HUB.reset()


class _R:
    def __init__(self, d):
        self.d = d

    def to_dict(self):
        return self.d


def script(monkeypatch, ds):
    it = iter(ds)
    last = [ds[-1]]

    def fake(a, t, **kw):
        try:
            last[0] = next(it)
        except StopIteration:
            pass
        return _R(last[0])
    monkeypatch.setattr(pipeline, "analyze", fake)


def second():
    return (np.full(SR, 300)).astype("<i2").tobytes()


_OPEN = []


@contextlib.contextmanager
def tc():
    with TestClient(app) as c:
        try:
            yield c
        finally:
            for w in _OPEN:              # a failing test must not leave a socket that hangs the portal
                try:
                    w.__exit__(None, None, None)
                except Exception:  # noqa: BLE001
                    pass
            _OPEN.clear()


def open_ws(c, source="tap"):
    info = c.post("/session", headers=ORIGIN).json()
    ws = c.websocket_connect("/ws/stream", headers=ORIGIN).__enter__()
    _OPEN.append(ws)
    ws.send_json({"type": "hello", "token": info["token"], "sample_rate": 16000, "format": "pcm_s16le",
                  "side": "far", "source": source})
    assert ws.receive_json() == {"type": "ready"}
    return ws


def tick(ws):
    ws.send_bytes(second())
    while True:
        m = ws.receive_json()
        if m["type"] == "verdict":
            return m


def drain(q):
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except _q.Empty:
            return out
        except Exception:  # noqa: BLE001  asyncio.QueueEmpty
            return out


def test_ws_verdict_has_raw_and_stable_and_sse_schema(monkeypatch):
    script(monkeypatch, [vd("human")] * 3 + [vd("scam", 0.9, ["urgency", "payment_rails"])] * 4)
    with tc() as c:
        sub = live.HUB.subscribe()
        ws = open_ws(c, "tap")
        msgs = [tick(ws) for _ in range(9)]
        assert all("tier" in m and "p_scam" in m and set(m["stable"]) == {"tier", "state", "alert", "since_s", "reasons"}
                   for m in msgs)
        assert msgs[0]["stable"]["state"] == "warming" and msgs[0]["tier"] == "human"
        assert msgs[-1]["stable"]["alert"] == "red"
        ws.send_json({"type": "stop"})
        while ws.receive_json()["type"] != "final":
            pass
        ws.__exit__(None, None, None)
        evs = drain(sub)
        types = [e["type"] for e in evs]
        assert types[0] == "state" and evs[0]["active"] is True and evs[0]["source"] == "tap"
        assert types.count("verdict") == 9
        v = next(e for e in evs if e["type"] == "verdict")
        assert set(v) == {"type", "tick", "elapsed_s", "verdict", "stable"}
        assert v["verdict"]["tier"] == "human" and "transcript" in v["verdict"]
        assert [e["tick"] for e in evs if e["type"] == "verdict"] == list(range(1, 10))
        assert "ended" in types and evs[-1] == {"type": "state", "active": False, "source": "", "elapsed_s": 0.0,
                                                "listening": False}
        blob = json.dumps(evs)
        assert "token" not in blob and "session_id" not in blob


def test_dismiss_via_ws_and_http_and_wipe(monkeypatch):
    script(monkeypatch, [vd("human")] * 2 + [vd("scam", 0.95, ["urgency", "payment_rails"])] * 12)
    with tc() as c:
        ws = open_ws(c)
        for _ in range(5):
            m = tick(ws)
        assert m["stable"]["alert"] == "red"
        s = next(iter(live.HUB.sessions.values()))
        assert c.post("/live/dismiss").json() == {"dismissed": 1}
        assert c.post("/live/dismiss").json() == {"dismissed": 0}
        assert s.stab.last is not None
        ws.send_json({"type": "dismiss"})                       # idempotent, never an error
        m = tick(ws)                                            # the scorer keeps reporting fresh evidence: it may re-latch
        assert m["stable"]["state"] in ("latched", "escalated")
        ws.send_json({"type": "stop"})
        while ws.receive_json()["type"] != "final":
            pass
        ws.__exit__(None, None, None)
        assert live.HUB.sessions == {}
        assert s.stab.last is None and s.ring is not None and not s.ring.last(1).any()   # wiped


def test_dismiss_over_ws_clears_latch(monkeypatch):
    script(monkeypatch, [vd("scam", 0.95, ["urgency", "payment_rails"])] * 3 + [vd("human")] * 10)
    with tc() as c:
        ws = open_ws(c)
        for _ in range(3):
            m = tick(ws)
        assert m["stable"]["state"] == "latched"
        ws.send_json({"type": "dismiss"})
        m = tick(ws)
        assert m["stable"]["alert"] == "none" and m["stable"]["state"] != "latched"
        ws.send_json({"type": "kill"})
        ws.__exit__(None, None, None)


def test_sse_route_cap_and_origin(monkeypatch):
    with tc() as c:
        for _ in range(4):
            assert live.HUB.subscribe() is not None
        assert c.get("/live/events").status_code == 429
        live.HUB.reset()
        assert c.get("/live/events", headers={"Origin": "http://evil.example"}).status_code == 403
        assert c.get("/live/events", headers={"Host": "evil.example"}).status_code == 400
        assert c.post("/live/dismiss", headers={"Origin": "http://evil.example"}).status_code == 403


def test_sse_refuses_non_loopback_client():
    class R:
        class client:
            host = "192.168.1.5"
    with pytest.raises(Exception) as e:
        live._loopback_only(R())
    assert getattr(e.value, "status_code", None) == 403


def test_source_label_is_sanitised():
    assert live.clean_source("Tap<script>") == "tapscript"
    assert live.clean_source(5) == "stream" and live.clean_source("") == "stream"
    assert len(live.clean_source("x" * 99)) == 24
