"""tools/ios/bridge.py against a FAKE phone (a WebSocket server, like the app's) and a FAKE engine (the real wire shapes
of POST /session and WS /ws/stream). No iproxy, no phone, no real engine.

The bridge must use ONLY its own authenticated session: verdicts from that session's WS, dismiss on that WS. The global
/live/events feed and POST /live/dismiss (which see/affect every session) must never be touched."""
import asyncio
import http.server
import importlib.util
import json
import socket
import threading
import time
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("ios_bridge", ROOT / "tools" / "ios" / "bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

websockets = pytest.importorskip("websockets")
uvicorn = pytest.importorskip("uvicorn")
from fastapi import FastAPI, HTTPException, Request, WebSocket  # noqa: E402

ORIGIN = "http://localhost:5173"
TOKEN = "K7QM-4TXD"


def verdict_msg(seq, tag, alert="red"):
    return {"type": "verdict", "seq": seq, "t": 5.0, "tier": "scam", "p_ai": 0.8, "p_scam": 0.9, "confidence": 0.6,
            "verdict": {"tier": "scam", "transcript": f"words of {tag}",
                        "scores": {"scam": 90, "ai_voice": 80, "confidence": 60, "confidence_label": "medium"}},
            "stable": {"tier": "scam", "state": "latched", "alert": alert, "since_s": 1, "reasons": [tag]}}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeEngine:
    """`end_after` frames -> the server ends the session itself with final{reason} (panic / DELETE / max length)."""

    def __init__(self, busy=False, bad_origin=False, end_after=None, end_reason="panic") -> None:
        self.busy, self.bad_origin = busy, bad_origin
        self.log: dict = {"origins": [], "hellos": [], "frames": {}, "dismiss": {}, "stopped": [], "sessions": 0,
                          "live_events_hits": 0, "live_dismiss_hits": 0}
        app = FastAPI()
        log = self.log

        @app.get("/health")
        def health():
            return {"ok": True}

        @app.post("/session")
        async def session(request: Request):
            log["origins"].append(request.headers.get("origin"))
            if self.bad_origin:
                raise HTTPException(403, "origin not allowed")
            if self.busy:
                raise HTTPException(429, "too many live sessions")
            log["sessions"] += 1
            return {"session_id": f"s{log['sessions']}", "token": f"tok{log['sessions']}", "ws_path": "/ws/stream", "params": {}}

        @app.post("/live/dismiss")
        async def dismiss_all():
            log["live_dismiss_hits"] += 1
            return {"dismissed": 99}

        @app.get("/live/events")
        async def events():
            log["live_events_hits"] += 1
            raise HTTPException(500, "the bridge must not read the global feed")

        @app.websocket("/ws/stream")
        async def ws_stream(ws: WebSocket):
            await ws.accept()
            hello = json.loads(await ws.receive_text())
            log["hellos"].append(hello)
            tag = hello["token"]
            log["frames"][tag], log["dismiss"][tag] = 0, 0
            await ws.send_json({"type": "ready"})
            seq = 0
            while True:
                msg = await ws.receive()
                if msg["type"] != "websocket.receive":
                    return
                if msg.get("bytes") is not None:
                    log["frames"][tag] += 1
                    if end_after is not None and log["frames"][tag] >= end_after:
                        await ws.send_json({"type": "final", "ticks": seq, "reason": end_reason})
                        await ws.close()
                        return
                    seq += 1
                    await ws.send_json(verdict_msg(seq, tag))
                else:
                    m = json.loads(msg["text"])
                    if m["type"] == "dismiss":
                        log["dismiss"][tag] += 1
                    elif m["type"] == "stop":
                        log["stopped"].append(tag)
                        await ws.send_json({"type": "final", "ticks": seq, "reason": "stop"})
                        return

        self.port = free_port()
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="error"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                return self
            time.sleep(0.05)
        raise RuntimeError("fake engine did not start")

    def __exit__(self, *a):
        self.server.should_exit = True
        self.thread.join(5)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


async def fake_phone(script, once=True):
    """A WebSocket server like the app's. `script(ws, got)` drives it after pairing; `got` collects bridge messages."""
    inbox: list = []
    got: list = []
    ran: list = []
    port = free_port()

    async def handler(ws):
        first = json.loads(await ws.recv())
        inbox.append(first)
        if first.get("token") != TOKEN:
            await ws.close()
            return
        await ws.send(json.dumps({"type": "ready", "app": "ios", "v": 1}))
        if once and ran:                                   # the bridge reconnects after a stop; stay idle then
            await asyncio.sleep(3)
            return
        ran.append(1)
        await script(ws, got)

    srv = await websockets.serve(handler, "127.0.0.1", port)
    return srv, port, inbox, got


async def collect(ws, got, until, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            m = json.loads(await asyncio.wait_for(ws.recv(), 0.3))
        except asyncio.TimeoutError:
            continue
        got.append(m)
        if until(m):
            return m
    return None


async def run_bridge(port, engine_url, stop_after, retry_s=0.2):
    b = bridge.Bridge(f"ws://127.0.0.1:{port}", engine_url, ORIGIN, TOKEN, retry_s=retry_s)
    stop = asyncio.Event()
    task = asyncio.ensure_future(b.run(stop))
    await asyncio.sleep(stop_after)
    stop.set()
    return b, await asyncio.wait_for(task, 10)


FRAME = b"\x01\x00" * 1600


def test_full_flow_frames_ticks_dismiss_stop_over_its_own_session_only():
    async def script(ws, got):
        await ws.send(json.dumps({"type": "started"}))
        await collect(ws, got, lambda m: m["type"] == "engine")
        for _ in range(3):
            await ws.send(FRAME)
        await collect(ws, got, lambda m: m["type"] == "tick")
        await ws.send(json.dumps({"type": "dismiss"}))
        await asyncio.sleep(0.4)
        await ws.send(json.dumps({"type": "stopped"}))
        await asyncio.sleep(0.6)

    async def go(engine):
        srv, port, inbox, got = await fake_phone(script)
        try:
            await run_bridge(port, engine.url, 4.0)
        finally:
            srv.close()
            await srv.wait_closed()
        return inbox, got

    with FakeEngine() as eng:
        inbox, got = asyncio.run(go(eng))
    assert inbox[0] == {"type": "auth", "token": TOKEN}
    assert set(eng.log["origins"]) == {ORIGIN}
    h = eng.log["hellos"][0]
    assert h["side"] == "mix" and h["source"] == "iphone" and h["sample_rate"] == 16000 and h["format"] == "pcm_s16le"
    assert eng.log["frames"]["tok1"] == 3
    types = [m["type"] for m in got]
    assert types[0] == "engine" and got[0]["status"] == "up" and "tick" in types
    tick = next(m for m in got if m["type"] == "tick")
    assert tick["stable"]["alert"] == "red" and tick["verdict"]["scores"]["confidence_label"] == "medium"
    assert tick["verdict"]["transcript"] == "words of tok1" and tick["tick"] == 1
    assert eng.log["dismiss"]["tok1"] == 1
    assert eng.log["stopped"] == ["tok1"]                    # the phone's Stop reached the engine (it wipes its ring)
    assert eng.log["live_events_hits"] == 0 and eng.log["live_dismiss_hits"] == 0


def test_two_sessions_are_isolated_no_cross_talk_and_dismiss_is_scoped():
    """Phone A (via the bridge) and phone B (via a second bridge) share one engine: each sees only its own verdicts,
    and A's Dismiss reaches only A's session."""
    async def script_a(ws, got):
        await ws.send(json.dumps({"type": "started"}))
        await collect(ws, got, lambda m: m["type"] == "engine")
        await asyncio.sleep(0.4)                               # let B open its session too
        for _ in range(2):
            await ws.send(FRAME)
        await collect(ws, got, lambda m: m["type"] == "tick")
        await ws.send(json.dumps({"type": "dismiss"}))
        await asyncio.sleep(1.0)

    async def script_b(ws, got):
        await ws.send(json.dumps({"type": "started"}))
        await collect(ws, got, lambda m: m["type"] == "engine")
        for _ in range(2):
            await ws.send(FRAME)
        await collect(ws, got, lambda m: m["type"] == "tick")
        await asyncio.sleep(1.4)

    async def go(engine):
        sa, pa, _, got_a = await fake_phone(script_a)
        sb, pb, _, got_b = await fake_phone(script_b)
        try:
            await asyncio.gather(run_bridge(pa, engine.url, 3.5), run_bridge(pb, engine.url, 3.5))
        finally:
            sa.close()
            sb.close()
        return got_a, got_b

    with FakeEngine() as eng:
        got_a, got_b = asyncio.run(go(eng))
    ticks_a = [m for m in got_a if m["type"] == "tick"]
    ticks_b = [m for m in got_b if m["type"] == "tick"]
    assert ticks_a and ticks_b
    tag_a, tag_b = ticks_a[0]["stable"]["reasons"][0], ticks_b[0]["stable"]["reasons"][0]
    assert tag_a != tag_b
    assert all(m["stable"]["reasons"] == [tag_a] and tag_a in m["verdict"]["transcript"] for m in ticks_a)
    assert all(m["stable"]["reasons"] == [tag_b] and tag_b in m["verdict"]["transcript"] for m in ticks_b)
    assert eng.log["dismiss"][tag_a] == 1 and eng.log["dismiss"][tag_b] == 0
    assert eng.log["live_events_hits"] == 0 and eng.log["live_dismiss_hits"] == 0


@pytest.mark.parametrize("reason", ["panic", "deleted", "max_length"])
def test_server_initiated_end_is_forwarded_to_the_phone(reason):
    async def script(ws, got):
        await ws.send(json.dumps({"type": "started"}))
        await collect(ws, got, lambda m: m["type"] == "engine")
        for _ in range(2):
            await ws.send(FRAME)
        await collect(ws, got, lambda m: m["type"] == "ended")
        await ws.send(FRAME)                                   # late frames after the end are dropped, not crashing
        await asyncio.sleep(0.3)

    async def go(engine):
        srv, port, _, got = await fake_phone(script)
        try:
            b, _ = await run_bridge(port, engine.url, 2.5)
        finally:
            srv.close()
        return b, got

    with FakeEngine(end_after=2, end_reason=reason) as eng:
        b, got = asyncio.run(go(eng))
    ended = [m for m in got if m["type"] == "ended"]
    assert ended and ended[0]["reason"] == reason and ended[0]["detail"]
    assert b.engine is None                                    # the bridge forgot the dead session
    assert eng.log["frames"]["tok1"] == 2


def test_wrong_token_is_loud_and_stops():
    async def go():
        srv, port, _, _ = await fake_phone(lambda ws, got: asyncio.sleep(1))
        try:
            b = bridge.Bridge(f"ws://127.0.0.1:{port}", "http://127.0.0.1:1", ORIGIN, "WRONG-CODE", retry_s=0.1)
            return await asyncio.wait_for(b.run(asyncio.Event()), 10)
        finally:
            srv.close()

    assert asyncio.run(go()) == "bad_token"


def test_engine_busy_down_refused_are_reported_to_the_phone():
    results = {}

    async def go(engine_url, key):
        async def script(ws, got):
            await ws.send(json.dumps({"type": "started"}))
            await collect(ws, got, lambda m: m["type"] == "engine")

        srv, port, _, got = await fake_phone(script)
        try:
            await run_bridge(port, engine_url, 1.5)
        finally:
            srv.close()
        results[key] = got[0]

    with FakeEngine(busy=True) as e:
        asyncio.run(go(e.url, "busy"))
    with FakeEngine(bad_origin=True) as e:
        asyncio.run(go(e.url, "refused"))
    asyncio.run(go(f"http://127.0.0.1:{free_port()}", "down"))
    assert results["busy"]["status"] == "busy"
    assert results["refused"]["status"] == "refused"
    assert results["down"]["status"] == "down"


def test_phone_disconnect_closes_engine_session_and_bridge_reconnects():
    async def script(ws, got):
        await ws.send(json.dumps({"type": "started"}))
        await collect(ws, got, lambda m: m["type"] == "engine")
        await ws.send(FRAME)
        await asyncio.sleep(0.3)
        await ws.close()                                        # phone vanishes mid-session (cable pulled)

    async def go(engine):
        srv, port, inbox, _ = await fake_phone(script)
        try:
            await run_bridge(port, engine.url, 2.5)
        finally:
            srv.close()
        return inbox

    with FakeEngine() as eng:
        inbox = asyncio.run(go(eng))
    assert eng.log["stopped"] == ["tok1"]
    assert len([m for m in inbox if m.get("type") == "auth"]) >= 2


def test_waits_quietly_when_the_phone_app_is_not_there():
    async def go():
        b = bridge.Bridge(f"ws://127.0.0.1:{free_port()}", "http://127.0.0.1:1", ORIGIN, TOKEN, retry_s=0.1)
        stop = asyncio.Event()
        t = asyncio.ensure_future(b.run(stop))
        await asyncio.sleep(0.6)
        stop.set()
        return await asyncio.wait_for(t, 5)

    assert asyncio.run(go()) == "interrupted"


class _Redirector(http.server.BaseHTTPRequestHandler):
    target = ""

    def _go(self):
        self.send_response(302)
        self.send_header("Location", self.target)
        self.end_headers()

    do_GET = do_POST = _go

    def log_message(self, *a):
        pass


class _Counter(http.server.BaseHTTPRequestHandler):
    hits = 0

    def do_GET(self):
        type(self).hits += 1
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"session_id":"x","token":"t","ws_path":"/ws/stream"}')

    do_POST = do_GET

    def log_message(self, *a):
        pass


def test_redirects_are_never_followed_and_every_request_is_rechecked():
    target = http.server.HTTPServer(("127.0.0.1", 0), _Counter)
    _Redirector.target = f"http://127.0.0.1:{target.server_port}/session"
    redirector = http.server.HTTPServer(("127.0.0.1", 0), _Redirector)
    for srv in (target, redirector):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{redirector.server_port}"
        with pytest.raises(urllib.error.HTTPError) as e:
            bridge.create_session(base, ORIGIN)
        assert e.value.code == 302
        assert bridge.engine_up(base) is False
        assert _Counter.hits == 0                               # the redirect target was never contacted
    finally:
        target.shutdown()
        redirector.shutdown()
    for bad in ("http://192.168.1.5:8000", "http://example.com", "file:///etc/passwd"):
        with pytest.raises(bridge.NotLoopback):
            bridge._local(bad + "/session", b"{}", ORIGIN, 1)


def test_pure_helpers():
    assert bridge.is_loopback_url("http://127.0.0.1:8000") and bridge.is_loopback_url("http://localhost:8000")
    assert not bridge.is_loopback_url("http://192.168.1.5:8000") and not bridge.is_loopback_url("ws://127.0.0.1:8000")
    t = bridge.tick_from_ws_verdict(verdict_msg(3, "x"))
    assert t["type"] == "tick" and t["tick"] == 3 and t["verdict"]["transcript"] == "words of x"
    old = {"type": "verdict", "seq": 2, "t": 9.0, "tier": "human", "p_ai": 0.1, "p_scam": 0, "confidence": 0.5,
           "stable": {"tier": "human"}}                          # an engine without the additive `verdict` field
    t2 = bridge.tick_from_ws_verdict(old)
    assert t2["verdict"]["tier"] == "human" and t2["stable"] == {"tier": "human"}
    assert "scam 90" in bridge.status_line(t)
    src = (ROOT / "tools" / "ios" / "bridge.py").read_text()
    assert "live/events\"" not in src and "/live/dismiss\"" not in src and "post_dismiss" not in src


def test_missing_tools_and_no_device_are_loud(monkeypatch, capsys):
    monkeypatch.setattr(bridge.shutil, "which", lambda n: None)
    a = bridge.parse_args(["--token", "K7QM-4TXD", "--i-understand"])
    assert asyncio.run(bridge.amain(a)) == 2
    err = capsys.readouterr().err
    assert "MISSING: iproxy, idevice_id" in err and "brew install libimobiledevice" in err
    monkeypatch.setattr(bridge.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(bridge, "usb_devices", lambda: [])
    assert asyncio.run(bridge.amain(a)) == 2
    assert "NO iPhone FOUND" in capsys.readouterr().err


def test_refuses_non_loopback_engine_and_never_uses_network_iproxy(capsys):
    a = bridge.parse_args(["--token", "K7QM-4TXD", "--i-understand", "--url", "http://192.168.0.9:8000"])
    assert asyncio.run(bridge.amain(a)) == 2
    assert "loopback" in capsys.readouterr().err
    src = (ROOT / "tools" / "ios" / "bridge.py").read_text()
    assert '"-n"' not in src and "'-n'" not in src and "--network" not in src
    assert '"-s", "127.0.0.1"' in src
