"""Final flush on a graceful end: the unscored tail gets ONE last analysis through the same stabiliser, emitted (WS and
SSE) before `final` / `ended`. Kill, panic and heartbeat timeout never flush. Fake scorer: the decisive evidence is ONLY
in the loud tail audio, so without the flush the call never reaches red."""
import io
import threading
import time
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tell import live, pipeline, session as sm
from tell.main import app
from tests.test_live import drain, vd
from tests.conftest import AUTH

ORIGIN = {"Origin": "http://localhost:5173"}
SR = 16_000
QUIET, LOUD = 300, 6000                      # int16 amplitudes: friendly part vs the incriminating tail


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("TELL_WARMUP", "0")
    monkeypatch.setenv("TELL_STREAM_WINDOW_S", "10")
    monkeypatch.setenv("TELL_STREAM_HOP_S", "3")
    monkeypatch.setenv("TELL_STREAM_RING_S", "30")
    for k in ("TELL_CORS_ORIGINS", "TELL_ALLOWED_HOSTS", "TELL_ANALYZE_TIMEOUT_S", "TELL_STREAM_FINAL_S",
              "TELL_STREAM_HEARTBEAT_S"):
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


def _last_second_peak(wav: bytes) -> int:
    with wave.open(io.BytesIO(wav)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return int(np.abs(x[-SR:]).max()) if len(x) else 0


SCAM = vd("scam", 0.95, ["urgency", "payment_rails", "credential_ask"])


@pytest.fixture
def scorer(monkeypatch):
    """Human unless the window ENDS in loud audio. Records every call; `delay` slows the decisive one."""
    st = {"calls": 0, "delay": 0.0}

    def fake(a, t, **kw):
        st["calls"] += 1
        if _last_second_peak(a) >= LOUD // 2:
            time.sleep(st["delay"])
            return _R(SCAM)
        return _R(vd("human"))
    monkeypatch.setattr(pipeline, "analyze", fake)
    return st


def tone(seconds, amp):
    return np.full(int(seconds * SR), amp, dtype="<i2").tobytes()


def send(ws, data, frame_s=0.5):
    n = int(frame_s * SR) * 2
    for i in range(0, len(data), n):
        ws.send_bytes(data[i:i + n])


def open_ws(c):
    info = c.post("/session", headers=ORIGIN).json()
    ws = c.websocket_connect("/ws/stream", headers=ORIGIN).__enter__()
    ws.send_json({"type": "hello", "token": info["token"], "sample_rate": 16000, "format": "pcm_s16le", "side": "far"})
    assert ws.receive_json() == {"type": "ready"}
    return ws, sm.REGISTRY._sessions[info["session_id"]]


def until(ws, kind, limit=40):
    seen = []
    for _ in range(limit):
        m = ws.receive_json()
        seen.append(m)
        if m["type"] == kind:
            return seen
    raise AssertionError(seen)


def friendly_part(ws):
    """9 s of quiet audio -> exactly three human ticks (t = 3, 6, 9)."""
    send(ws, tone(9, QUIET))
    vs = [m for m in until(ws, "verdict") + until(ws, "verdict") + until(ws, "verdict") if m["type"] == "verdict"]
    assert [v["t"] for v in vs] == [3.0, 6.0, 9.0] and all(v["stable"]["alert"] == "none" for v in vs)
    return vs


def test_decisive_tail_is_scored_before_final_and_sse_ended(scorer):
    with TestClient(app, headers=AUTH) as c:
        sub = live.HUB.subscribe()
        ws, s = open_ws(c)
        friendly_part(ws)
        send(ws, tone(2.5, LOUD))                        # the incriminating tail: not enough for another tick
        ws.send_json({"type": "ping"})
        until(ws, "pong")
        assert scorer["calls"] == 3 and s.ticks == 3      # nothing scored the tail yet
        ws.send_json({"type": "stop"})
        seen = until(ws, "final")
        ws.__exit__(None, None, None)
    kinds = [m["type"] for m in seen]
    assert kinds[-2:] == ["verdict", "final"]
    tail, final = seen[-2], seen[-1]
    assert tail["tail"] is True and tail["tier"] == "scam" and tail["window"] == [1.5, 11.5]
    assert tail["stable"]["alert"] == "red"               # the stable state reflects the tail
    assert final == {"type": "final", "ticks": 4, "reason": "stop", "tail": "scored"}
    assert scorer["calls"] == 4                           # exactly ONE extra analysis
    assert s.ring.wiped and s.stab.last is None           # wiped afterwards, as before
    evs = drain(sub)
    order = [(e["type"], e.get("tail", False)) for e in evs if e["type"] in ("verdict", "ended")]
    assert order == [("verdict", False)] * 3 + [("verdict", True), ("ended", False)]
    sse_tail = next(e for e in evs if e.get("tail"))
    assert sse_tail["stable"]["alert"] == "red" and sse_tail["tick"] == 4
    assert all("tail" not in e for e in evs if e["type"] == "verdict" and e is not sse_tail)


def test_clean_close_also_flushes_to_the_live_feed(scorer):
    with TestClient(app, headers=AUTH) as c:
        sub = live.HUB.subscribe()
        ws, s = open_ws(c)
        friendly_part(ws)
        send(ws, tone(2.5, LOUD))
        ws.close(1000)                                   # clean close, no stop message
        deadline = time.time() + 3
        while not s.closed and time.time() < deadline:   # (TestClient's __exit__ would CANCEL the handler; a real
            time.sleep(0.02)                             #  server lets it run, so close first and wait)
        ws.__exit__(None, None, None)
        assert s.closed and s.ring.wiped
    evs = drain(sub)
    order = [(e["type"], e.get("tail", False)) for e in evs if e["type"] in ("verdict", "ended")]
    assert order[-2:] == [("verdict", True), ("ended", False)]
    assert next(e for e in evs if e.get("tail"))["stable"]["alert"] == "red"


@pytest.mark.parametrize("how", ["kill", "panic"])
def test_no_tail_analysis_on_kill_or_panic(scorer, how):
    with TestClient(app, headers=AUTH) as c:
        sub = live.HUB.subscribe()
        ws, s = open_ws(c)
        friendly_part(ws)
        send(ws, tone(2.5, LOUD))
        ws.send_json({"type": "ping"})
        until(ws, "pong")
        if how == "kill":
            ws.send_json({"type": "kill"})
        else:
            assert c.post("/panic").json()["wiped"] == 1
        seen = until(ws, "final")
        ws.__exit__(None, None, None)
    assert seen[-1] == {"type": "final", "ticks": 3, "reason": how}
    assert not any(m["type"] == "verdict" for m in seen) and scorer["calls"] == 3
    assert not any(e.get("tail") for e in drain(sub))


def test_no_tail_analysis_on_heartbeat_timeout(scorer, monkeypatch):
    monkeypatch.setenv("TELL_STREAM_HEARTBEAT_S", "0.5")
    with TestClient(app, headers=AUTH) as c:
        ws, s = open_ws(c)
        send(ws, tone(2.5, LOUD))
        seen = until(ws, "error")
        assert seen[-1]["code"] == "heartbeat_timeout"
        ws.__exit__(None, None, None)
    assert scorer["calls"] == 0 and s.ring.wiped


@pytest.mark.parametrize("extra_s, why", [(0, "no_new_audio"), (1.0, "covered")])
def test_no_duplicate_analysis_when_tail_already_covered(scorer, extra_s, why):
    with TestClient(app, headers=AUTH) as c:
        ws, s = open_ws(c)
        friendly_part(ws)
        if extra_s:
            send(ws, tone(extra_s, LOUD))
        ws.send_json({"type": "stop"})
        seen = until(ws, "final")
        ws.__exit__(None, None, None)
    assert seen[-1] == {"type": "final", "ticks": 3, "reason": "stop", "tail": why}
    assert scorer["calls"] == 3 and not any(m["type"] == "verdict" for m in seen)


def test_silent_tail_is_skipped(scorer):
    with TestClient(app, headers=AUTH) as c:
        ws, s = open_ws(c)
        friendly_part(ws)
        send(ws, tone(2.5, 0))
        ws.send_json({"type": "stop"})
        seen = until(ws, "final")
        ws.__exit__(None, None, None)
    assert seen[-1]["tail"] == "silence" and scorer["calls"] == 3


@pytest.mark.parametrize("env", ["TELL_STREAM_FINAL_S", "TELL_ANALYZE_TIMEOUT_S"])
def test_flush_respects_the_time_budget(scorer, monkeypatch, env):
    monkeypatch.setenv(env, "0.3")                       # either knob bounds the flush (the budget is their minimum)
    scorer["delay"] = 1.5
    with TestClient(app, headers=AUTH) as c:
        sub = live.HUB.subscribe()
        ws, s = open_ws(c)
        friendly_part(ws)
        send(ws, tone(2.5, LOUD))
        ws.send_json({"type": "stop"})
        t0 = time.monotonic()
        seen = until(ws, "final")
        took = time.monotonic() - t0
        ws.__exit__(None, None, None)
        time.sleep(1.6)                                  # let the abandoned worker finish before the next test
    assert seen[-1] == {"type": "final", "ticks": 3, "reason": "stop", "tail": "timeout"}
    assert took < 1.2 and not any(m["type"] == "verdict" for m in seen)
    assert not any(e.get("tail") for e in drain(sub)) and s.ring.wiped


def test_inflight_tick_lands_on_stop_then_tail_is_not_reanalysed(monkeypatch):
    gate = threading.Event()
    calls = []

    def slow(a, t, **kw):
        calls.append(1)
        gate.wait(5)
        return _R(vd("human"))
    monkeypatch.setattr(pipeline, "analyze", slow)
    with TestClient(app, headers=AUTH) as c:
        ws, s = open_ws(c)
        send(ws, tone(4, QUIET))                         # tick at 3 s in flight; 1 s after it is "covered"
        deadline = time.time() + 3
        while not s.inflight and time.time() < deadline:
            time.sleep(0.01)
        assert s.inflight
        ws.send_json({"type": "stop"})
        time.sleep(0.2)
        gate.set()
        seen = until(ws, "final")
        ws.__exit__(None, None, None)
    assert [m["type"] for m in seen][-2:] == ["verdict", "final"]
    assert "tail" not in seen[-2] and seen[-2]["t"] == 3.0
    assert seen[-1] == {"type": "final", "ticks": 1, "reason": "stop", "tail": "covered"} and len(calls) == 1


def test_flush_budget_is_min_of_both_knobs(monkeypatch):
    monkeypatch.setenv("TELL_STREAM_FINAL_S", "4")
    monkeypatch.setenv("TELL_ANALYZE_TIMEOUT_S", "2")
    assert sm.Session("x", sm.params()).flush_budget_s() == 2.0
    monkeypatch.setenv("TELL_ANALYZE_TIMEOUT_S", "60")
    assert sm.Session("x", sm.params()).flush_budget_s() == 4.0
    monkeypatch.delenv("TELL_STREAM_FINAL_S")
    assert sm.params()["final_flush_s"] == sm.FINAL_FLUSH_S


def test_page_stop_ends_the_live_session_and_needs_the_token():
    with TestClient(app, headers=AUTH) as c:
        ws, s = open_ws(c)
        send(ws, tone(2, QUIET))
        assert TestClient(app).post("/live/stop", headers=ORIGIN).status_code == 401      # no token, no stop
        r = c.post("/live/stop", headers=ORIGIN)
        assert r.status_code == 200 and r.json() == {"stopped": 1}
        fin = until(ws, "final")[-1]
        assert fin["reason"] == "stopped" and "tail" not in fin                         # wiped at once, no extra analysis
        assert s.closed and s.close_reason == "stopped" and sm.REGISTRY.count() == 0
        ws.__exit__(None, None, None)
        assert c.post("/live/stop", headers=ORIGIN).json() == {"stopped": 0}            # nothing live: harmless
