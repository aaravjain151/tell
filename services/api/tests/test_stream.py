"""Streaming backend: auth handshake, ticks, wipes, backpressure, no disk, Host/Origin guard.
pipeline.analyze is monkeypatched to a fast fake except in the DEBUG_SAVE test."""
import builtins
import tempfile
import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from tests.conftest import AUTH
from starlette.websockets import WebSocketDisconnect

from tell import pipeline, session as sm
from tell.main import app
from tests.synth import make_call, to_wav_bytes

ORIGIN = {"Origin": "http://localhost:5173"}
SR = 16_000


class _V:
    def __init__(self, conf=0.9):
        self.conf = conf

    def to_dict(self):
        return {"tier": "human", "p_ai": 0.1, "p_scam": 0.0, "confidence": self.conf, "headline": "Sounds human",
                "tells": [{"name": "neural", "applicable": False}, {"name": "pause_regularity", "applicable": True}]}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("TELL_WARMUP", "0")
    for k in list(__import__("os").environ):
        if k.startswith("TELL_STREAM_") or k in ("TELL_CORS_ORIGINS", "TELL_ALLOWED_HOSTS",
                                                        "TELL_DEBUG_SAVE", "TELL_ANALYZE_TIMEOUT_S"):
            monkeypatch.delenv(k)
    monkeypatch.setattr(pipeline, "analyze", lambda a, t, **kw: _V())
    sm.REGISTRY.panic()
    yield
    sm.REGISTRY.panic()


_OPEN = []


@pytest.fixture
def client():
    with TestClient(app, headers=AUTH) as c:
        yield c
        for w in _OPEN:                      # a failing test must not leave a socket that hangs the portal
            try:
                w.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
        _OPEN.clear()


def pcm(seconds, seed=0, kind="human"):
    x = make_call(kind, seconds=seconds, seed=seed)
    return (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()


def new_session(c, extra=None):
    r = c.post("/session", headers=ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()


def hello(ws, token, side="far", **kw):
    ws.send_json({"type": "hello", "token": token, "sample_rate": 16000, "format": "pcm_s16le", "side": side, **kw})


def open_ws(c, side="far"):
    info = new_session(c)
    ws = c.websocket_connect("/ws/stream", headers=ORIGIN).__enter__()
    _OPEN.append(ws)
    hello(ws, info["token"], side)
    assert ws.receive_json() == {"type": "ready"}
    return ws, info


def send_audio(ws, data, frame_s=0.5):
    n = int(frame_s * SR) * 2
    for i in range(0, len(data), n):
        ws.send_bytes(data[i:i + n])


def read_until(ws, pred, limit=60):
    seen = []
    for _ in range(limit):
        m = ws.receive_json()
        seen.append(m)
        if pred(m):
            return m, seen
    raise AssertionError(f"never saw the message; got {seen}")


def live_session(info):
    return sm.REGISTRY._sessions[info["session_id"]]


# ---------------------------------------------------------------- POST /session and handshake

def test_post_session_shape_and_token(client):
    info = new_session(client)
    assert set(info) == {"session_id", "token", "ws_path", "params"}
    assert info["ws_path"] == "/ws/stream" and "token" not in info["ws_path"]
    assert len(info["token"]) >= 43                      # 256 bits, urlsafe base64
    p = info["params"]
    assert (p["sample_rate"], p["format"], p["hop_s"], p["window_s"], p["ring_s"]) == (16000, "pcm_s16le", 3.0, 10.0, 30.0)
    assert new_session(client)["token"] != info["token"]


def test_handshake_ok_and_params(client):
    ws, info = open_ws(client, "near")
    assert live_session(info).side == "near"
    ws.send_json({"type": "stop"})
    m, _ = read_until(ws, lambda m: m["type"] == "final")
    assert m["ticks"] == 0 and m["reason"] == "stop"
    ws.__exit__(None, None, None)


@pytest.mark.parametrize("bad", ["", "nope", None, 5])
def test_bad_token_rejected(client, bad):
    new_session(client)
    with client.websocket_connect("/ws/stream", headers=ORIGIN) as ws:
        hello(ws, bad)
        assert ws.receive_json() == {"type": "error", "code": "auth_failed"}
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_reused_token_rejected(client):
    ws, info = open_ws(client)
    with client.websocket_connect("/ws/stream", headers=ORIGIN) as ws2:
        hello(ws2, info["token"])
        assert ws2.receive_json()["code"] == "auth_failed"
    ws.__exit__(None, None, None)


def test_expired_token_rejected(client, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(sm, "_now", lambda: clock[0])
    info = new_session(client)
    clock[0] += 61
    with client.websocket_connect("/ws/stream", headers=ORIGIN) as ws:
        hello(ws, info["token"])
        assert ws.receive_json()["code"] == "auth_failed"
    assert sm.REGISTRY.count() == 0                      # the pending session was reaped, not leaked


def test_unsupported_format_rejected(client):
    info = new_session(client)
    with client.websocket_connect("/ws/stream", headers=ORIGIN) as ws:
        hello(ws, info["token"], sample_rate=44100)
        assert ws.receive_json()["code"] == "unsupported_format"
    info = new_session(client)
    with client.websocket_connect("/ws/stream", headers=ORIGIN) as ws:
        hello(ws, info["token"], side="everyone")
        assert ws.receive_json()["code"] == "unsupported_format"


def test_audio_before_hello_rejected(client):
    info = new_session(client)
    with client.websocket_connect("/ws/stream", headers=ORIGIN) as ws:
        ws.send_bytes(pcm(0.5))
        assert ws.receive_json() == {"type": "error", "code": "hello_required"}
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    # the unused token stays valid for the proper client, and the rejected socket never created a ring
    assert live_session(info).ring is None


def test_non_hello_text_first_rejected(client):
    new_session(client)
    with client.websocket_connect("/ws/stream", headers=ORIGIN) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["code"] == "hello_required"


def test_unauthenticated_socket_closed_after_timeout(client, monkeypatch):
    monkeypatch.setenv("TELL_STREAM_HELLO_TIMEOUT_S", "0.2")
    with client.websocket_connect("/ws/stream", headers=ORIGIN) as ws:
        assert ws.receive_json() == {"type": "error", "code": "hello_timeout"}
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_max_sessions(client):
    new_session(client)
    new_session(client)
    r = client.post("/session", headers=ORIGIN)
    assert r.status_code == 429


# ---------------------------------------------------------------- Host / Origin guard

def test_session_requires_allowed_origin(client):
    assert client.post("/session", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/session", headers={"Origin": "null"}).status_code == 403
    assert client.post("/session").status_code == 403                      # no Origin at all
    assert client.post("/session", headers={**ORIGIN, "Host": "evil.example"}).status_code == 400
    assert client.post("/session", headers={**ORIGIN, "Host": "rebind.evil.example:8000"}).status_code == 400
    assert sm.REGISTRY.count() == 0
    assert client.post("/session", headers={"Origin": "http://127.0.0.1:8000", "Host": "127.0.0.1:8000"}).status_code == 200


def test_session_origin_from_env(client, monkeypatch):
    monkeypatch.setenv("TELL_CORS_ORIGINS", "http://localhost:9999")
    assert client.post("/session", headers=ORIGIN).status_code == 403
    assert client.post("/session", headers={"Origin": "http://localhost:9999"}).status_code == 200


def test_websocket_handshake_obeys_guard(client):
    info = new_session(client)
    for headers in ({"Origin": "https://evil.example"}, {"Origin": "null"}, {**ORIGIN, "Host": "evil.example"}):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/stream", headers=headers):
                pass
    assert live_session(info).state == "pending"                           # token untouched by refused handshakes


def test_cors_preflight_for_session(client):
    r = client.options("/session", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                                            "Access-Control-Request-Headers": "content-type"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:5173"


# ---------------------------------------------------------------- ticks

def test_tick_produces_raw_verdict(client):
    ws, info = open_ws(client, "far")
    send_audio(ws, pcm(7.0))
    v, seen = read_until(ws, lambda m: m["type"] == "verdict")
    assert v["type"] == "verdict" and v["seq"] == 1
    assert v["window"][0] == 0.0 and 3.0 <= v["t"] <= 7.0 and v["window"][1] == v["t"]
    assert v["tier"] == "human" and v["p_ai"] == 0.1 and v["p_scam"] == 0.0 and v["confidence"] == 0.9
    assert v["headline"] == "Sounds human" and v["degraded"] == ["neural"]
    assert v["side"] == "far" and v["confidence_capped"] is False and v["lag_s"] >= 0
    ws.send_json({"type": "stop"})
    f, _ = read_until(ws, lambda m: m["type"] == "final")
    assert f["ticks"] >= 1
    ws.__exit__(None, None, None)


def test_window_is_last_10_seconds(client, monkeypatch):
    seen = []
    monkeypatch.setattr(pipeline, "analyze", lambda a, t, **kw: seen.append(len(a)) or _V())
    ws, _ = open_ws(client)
    send_audio(ws, pcm(14.0), frame_s=1.0)
    read_until(ws, lambda m: m["type"] == "verdict" and m["t"] >= 12.0)
    assert all(n <= 44 + 10 * SR * 2 for n in seen)                         # 10 s of PCM16 + 44-byte WAV header
    assert max(seen) == 44 + 10 * SR * 2
    ws.__exit__(None, None, None)


def test_mix_side_caps_confidence_far_does_not(client):
    ws, _ = open_ws(client, "mix")
    send_audio(ws, pcm(4.0))
    v, _ = read_until(ws, lambda m: m["type"] == "verdict")
    assert v["side"] == "mix" and v["confidence"] == sm.MIX_CONF_CAP and v["confidence_capped"] is True
    assert v["p_ai"] == 0.1 and v["tier"] == "human"                        # nothing else is touched
    ws.__exit__(None, None, None)


def test_pipeline_error_is_reported_without_detail(client, monkeypatch):
    def boom(a, t, **kw):
        raise RuntimeError("secret transcript words")
    monkeypatch.setattr(pipeline, "analyze", boom)
    ws, _ = open_ws(client)
    send_audio(ws, pcm(4.0))
    m, _ = read_until(ws, lambda m: m["type"] == "error")
    assert m == {"type": "error", "code": "analysis_failed"}
    ws.__exit__(None, None, None)


# ---------------------------------------------------------------- wipes

def _assert_wiped(buf):
    assert buf is not None and not buf.any()


def test_stop_wipes_ring(client):
    ws, info = open_ws(client)
    s = live_session(info)
    send_audio(ws, pcm(2.0))
    ws.send_json({"type": "ping"})
    read_until(ws, lambda m: m["type"] == "pong")
    buf = s.ring._buf
    assert buf.any()
    ws.send_json({"type": "stop"})
    read_until(ws, lambda m: m["type"] == "final")
    _assert_wiped(buf)
    assert s.ring.wiped and sm.REGISTRY.count() == 0
    ws.__exit__(None, None, None)


def test_kill_wipes_ring(client):
    ws, info = open_ws(client)
    s = live_session(info)
    send_audio(ws, pcm(2.0))
    ws.send_json({"type": "ping"})
    read_until(ws, lambda m: m["type"] == "pong")
    buf = s.ring._buf
    ws.send_json({"type": "kill"})
    f, _ = read_until(ws, lambda m: m["type"] == "final")
    assert f["reason"] == "kill"
    _assert_wiped(buf)
    ws.__exit__(None, None, None)


def test_disconnect_wipes_ring(client):
    ws, info = open_ws(client)
    s = live_session(info)
    send_audio(ws, pcm(2.0))
    ws.send_json({"type": "ping"})
    read_until(ws, lambda m: m["type"] == "pong")
    buf = s.ring._buf
    ws.__exit__(None, None, None)
    deadline = time.time() + 3
    while not s.closed and time.time() < deadline:
        time.sleep(0.02)
    _assert_wiped(buf)


def test_panic_wipes_every_session(client):
    ws1, i1 = open_ws(client)
    ws2, i2 = open_ws(client)
    b1, b2 = live_session(i1), live_session(i2)
    for w in (ws1, ws2):
        send_audio(w, pcm(1.0))
        w.send_json({"type": "ping"})
        read_until(w, lambda m: m["type"] == "pong")
    bufs = [b1.ring._buf, b2.ring._buf]
    assert all(b.any() for b in bufs)
    assert client.post("/panic").json() == {"wiped": 2}
    for w in (ws1, ws2):
        f, _ = read_until(w, lambda m: m["type"] == "final")
        assert f["reason"] == "panic"
        w.__exit__(None, None, None)
    for b in bufs:
        _assert_wiped(b)


def test_panic_also_kills_pending_tokens(client):
    info = new_session(client)
    assert client.post("/panic").json() == {"wiped": 1}
    with client.websocket_connect("/ws/stream", headers=ORIGIN) as ws:
        hello(ws, info["token"])
        assert ws.receive_json()["code"] == "auth_failed"


def test_delete_session_wipes_and_404s(client):
    ws, info = open_ws(client)
    s = live_session(info)
    send_audio(ws, pcm(1.0))
    ws.send_json({"type": "ping"})
    read_until(ws, lambda m: m["type"] == "pong")
    buf = s.ring._buf
    assert client.delete(f"/session/{info['session_id']}").json() == {"deleted": True}
    f, _ = read_until(ws, lambda m: m["type"] == "final")
    assert f["reason"] == "deleted"
    _assert_wiped(buf)
    assert client.delete(f"/session/{info['session_id']}").status_code == 404
    ws.__exit__(None, None, None)


def test_heartbeat_timeout_wipes_ring(client, monkeypatch):
    monkeypatch.setenv("TELL_STREAM_HEARTBEAT_S", "0.3")
    ws, info = open_ws(client)
    s = live_session(info)
    send_audio(ws, pcm(1.0))
    buf = s.ring._buf
    m, _ = read_until(ws, lambda m: m["type"] == "error")
    assert m["code"] == "heartbeat_timeout"
    _assert_wiped(buf)
    ws.__exit__(None, None, None)


def test_ping_keeps_session_alive(client, monkeypatch):
    monkeypatch.setenv("TELL_STREAM_HEARTBEAT_S", "0.4")
    ws, info = open_ws(client)
    for _ in range(4):
        time.sleep(0.2)
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
    assert not live_session(info).closed
    ws.__exit__(None, None, None)


def test_max_session_length(client, monkeypatch):
    monkeypatch.setenv("TELL_STREAM_MAX_SESSION_S", "0.3")
    ws, info = open_ws(client)
    s = live_session(info)
    buf = s.ring._buf
    f, _ = read_until(ws, lambda m: m["type"] == "final")
    assert f["reason"] == "max_length"
    _assert_wiped(buf)
    ws.__exit__(None, None, None)


def test_wipe_discards_inflight_result(client, monkeypatch):
    gate = threading.Event()

    def slow(a, t, **kw):
        gate.wait(5)
        return _V()
    monkeypatch.setattr(pipeline, "analyze", slow)
    ws, info = open_ws(client)
    s = live_session(info)
    send_audio(ws, pcm(4.0))
    deadline = time.time() + 3
    while not s.inflight and time.time() < deadline:
        time.sleep(0.01)
    assert s.inflight
    ws.send_json({"type": "stop"})
    f, seen = read_until(ws, lambda m: m["type"] == "final")
    gate.set()
    time.sleep(0.2)
    assert s.ticks == 0 and not any(m["type"] == "verdict" for m in seen)
    ws.__exit__(None, None, None)


# ---------------------------------------------------------------- bounds and backpressure

def test_oversize_and_odd_frames_rejected(client):
    ws, _ = open_ws(client)
    ws.send_bytes(b"\0" * (sm.MAX_FRAME_BYTES + 2))
    assert ws.receive_json()["code"] == "frame_too_large"
    ws.__exit__(None, None, None)
    ws, _ = open_ws(client)
    ws.send_bytes(b"\0" * 321)
    assert ws.receive_json()["code"] == "bad_frame"
    ws.__exit__(None, None, None)


def test_oversize_text_and_junk_rejected(client):
    ws, _ = open_ws(client)
    ws.send_text("x" * 5000)
    assert ws.receive_json()["code"] == "bad_message"
    ws.__exit__(None, None, None)
    ws, _ = open_ws(client)
    ws.send_text("not json")
    assert ws.receive_json()["code"] == "bad_message"
    ws.__exit__(None, None, None)


def test_overload_drops_oldest_and_warns(client, monkeypatch):
    monkeypatch.setenv("TELL_STREAM_WINDOW_S", "2")
    monkeypatch.setenv("TELL_STREAM_HOP_S", "1")
    monkeypatch.setenv("TELL_STREAM_RING_S", "2")

    def slow(a, t, **kw):
        time.sleep(0.4)
        return _V()
    monkeypatch.setattr(pipeline, "analyze", slow)
    ws, info = open_ws(client)
    s = live_session(info)
    assert s.ring.capacity == 2 * SR
    send_audio(ws, pcm(12.0), frame_s=1.0)                 # a 12 s burst while the first 0.4 s analysis runs
    v2, seen = read_until(ws, lambda m: m["type"] == "verdict" and m["seq"] == 2)
    codes = [m["code"] for m in seen if m["type"] == "warn"]
    assert "lagging" in codes
    assert v2["dropped_ms"] >= 8000 and v2["window"][1] == 12.0
    lag = s.lag_report()
    assert lag["skipped_ticks"] >= 1 and lag["dropped_ms"] >= 8000
    ws.__exit__(None, None, None)


def test_overloaded_warning_sent(client, monkeypatch):
    monkeypatch.setenv("TELL_STREAM_WINDOW_S", "2")
    monkeypatch.setenv("TELL_STREAM_HOP_S", "1")
    monkeypatch.setenv("TELL_STREAM_RING_S", "2")
    monkeypatch.setattr(pipeline, "analyze", lambda a, t, **kw: (time.sleep(0.3), _V())[1])
    ws, _ = open_ws(client)
    send_audio(ws, pcm(8.0), frame_s=1.0)
    read_until(ws, lambda m: m["type"] == "warn" and m["code"] == "overloaded")
    ws.__exit__(None, None, None)


# ---------------------------------------------------------------- no disk

def test_no_file_is_created_during_a_session(client, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELL_DEBUG_SAVE", "1")
    writes = []
    real_open = builtins.open

    def spy_open(file, mode="r", *a, **k):
        if any(c in str(mode) for c in "wax+"):
            writes.append((str(file), mode))
        return real_open(file, mode, *a, **k)

    def deny(*a, **k):
        writes.append(("tempfile", a))
        raise AssertionError("tempfile used during a session")

    monkeypatch.setattr(builtins, "open", spy_open)
    for name in ("NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile", "mkstemp", "mkdtemp", "TemporaryDirectory"):
        monkeypatch.setattr(tempfile, name, deny)
    ws, _ = open_ws(client)
    send_audio(ws, pcm(7.0))
    read_until(ws, lambda m: m["type"] == "verdict")
    ws.send_json({"type": "stop"})
    read_until(ws, lambda m: m["type"] == "final")
    ws.__exit__(None, None, None)
    assert writes == []
    assert list(tmp_path.iterdir()) == []


def test_debug_save_is_ignored_by_real_pipeline(monkeypatch, tmp_path):
    """Control + treatment on the real pipeline: DEBUG_SAVE writes for /analyze but never for a stream tick."""
    monkeypatch.undo()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELL_DEBUG_SAVE", "1")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("TELL_STT", "whisper")
    wav = to_wav_bytes(make_call("human", seconds=4, seed=1))
    sm._analyze_window(make_call("human", seconds=4, seed=1))
    assert not (tmp_path / "data").exists(), "stream tick wrote debug audio"
    pipeline.analyze(wav, None)
    assert (tmp_path / "data" / "debug").is_dir(), "control failed: DEBUG_SAVE no longer writes for /analyze"
