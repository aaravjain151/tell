"""tools/ios/bridge.py against a FAKE phone (a WebSocket server, like the app's) and a FAKE engine (the real wire shapes
of POST /session, WS /ws/stream, GET /live/events, POST /live/dismiss). No iproxy, no phone, no real engine."""
import asyncio
import importlib.util
import json
import socket
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("ios_bridge", ROOT / "tools" / "ios" / "bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

websockets = pytest.importorskip("websockets")
uvicorn = pytest.importorskip("uvicorn")
from fastapi import FastAPI, HTTPException, Request, WebSocket  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402

ORIGIN = "http://localhost:5173"
TOKEN = "K7QM-4TXD"
VERDICT = {"type": "verdict", "tick": 1, "elapsed_s": 5.0,
           "verdict": {"tier": "scam", "p_ai": 0.8, "p_scam": 0.9, "confidence": 0.6, "transcript": "read me the code",
                       "scores": {"scam": 90, "ai_voice": 80, "confidence": 60, "confidence_label": "medium",
                                  "voice_unresolved": False, "confidence_note": ""}},
           "stable": {"tier": "scam", "state": "latched", "alert": "red", "since_s": 1, "reasons": ["x"]}}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeEngine:
    def __init__(self, busy: bool = False, bad_origin: bool = False) -> None:
        self.busy, self.bad_origin = busy, bad_origin
        self.log: dict = {"origins": [], "hello": None, "frames": [], "dismiss_ws": 0, "dismiss_http": 0, "stopped": False,
                          "sessions": 0}
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
            return {"session_id": "s1", "token": "tok", "ws_path": "/ws/stream", "params": {}}

        @app.post("/live/dismiss")
        async def dismiss():
            log["dismiss_http"] += 1
            return {"dismissed": 1}

        @app.get("/live/events")
        async def events():
            async def gen():
                yield b'data: {"type":"state","active":true,"source":"iphone","elapsed_s":0,"listening":true}\n\n'
                for _ in range(200):
                    await asyncio.sleep(0.15)
                    if log["frames"]:
                        yield b"data: " + json.dumps(VERDICT).encode() + b"\n\n"
                        break
                for _ in range(200):
                    await asyncio.sleep(0.1)
                    if log["stopped"]:
                        yield b'data: {"type":"ended","reason":"stop"}\n\n'
                        return
            return StreamingResponse(gen(), media_type="text/event-stream")

        @app.websocket("/ws/stream")
        async def ws_stream(ws: WebSocket):
            await ws.accept()
            hello = json.loads(await ws.receive_text())
            log["hello"] = hello
            await ws.send_json({"type": "ready"})
            while True:
                msg = await ws.receive()
                if msg["type"] != "websocket.receive":
                    return
                if msg.get("bytes") is not None:
                    log["frames"].append(len(msg["bytes"]))
                else:
                    m = json.loads(msg["text"])
                    if m["type"] == "dismiss":
                        log["dismiss_ws"] += 1
                    elif m["type"] == "stop":
                        log["stopped"] = True
                        await ws.send_json({"type": "final", "ticks": 1, "reason": "stop"})
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


async def fake_phone(script, token_ok: bool = True):
    """A WebSocket server like the app's. `script(ws, inbox)` drives it after pairing. Returns (server, port, inbox)."""
    inbox: list = []
    port = free_port()

    async def handler(ws):
        first = json.loads(await ws.recv())
        inbox.append(first)
        if first.get("token") != TOKEN or not token_ok:
            await ws.close()
            return
        await ws.send(json.dumps({"type": "ready", "app": "ios", "v": 1}))
        await script(ws, inbox)

    srv = await websockets.serve(handler, "127.0.0.1", port)
    return srv, port, inbox


async def run_bridge(port, engine_url, stop_after, retry_s=0.2):
    b = bridge.Bridge(f"ws://127.0.0.1:{port}", engine_url, ORIGIN, TOKEN, retry_s=retry_s)
    stop = asyncio.Event()
    task = asyncio.ensure_future(b.run(stop))
    await asyncio.sleep(stop_after)
    stop.set()
    return b, await asyncio.wait_for(task, 10)


def test_full_flow_frames_ticks_dismiss_stop():
    frame = b"\x01\x00" * 1600
    got: list = []
    ran: list = []

    async def script(ws, inbox):
        if ran:                                            # the bridge reconnects after Stop; stay idle the second time
            await asyncio.sleep(2)
            return
        ran.append(1)
        await ws.send(json.dumps({"type": "started"}))
        await asyncio.sleep(1.0)
        for _ in range(3):
            await ws.send(frame)
        deadline = time.time() + 5
        while time.time() < deadline:                      # wait for the relayed tick
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), 0.5))
            except asyncio.TimeoutError:
                continue
            got.append(m)
            if m["type"] == "tick":
                break
        await ws.send(json.dumps({"type": "dismiss"}))
        await asyncio.sleep(0.5)
        await ws.send(json.dumps({"type": "stopped"}))
        await asyncio.sleep(0.8)

    async def go(engine):
        srv, port, inbox = await fake_phone(script)
        try:
            await run_bridge(port, engine.url, 4.5)
        finally:
            srv.close()
            await srv.wait_closed()
        return inbox

    with FakeEngine() as eng:
        inbox = asyncio.run(go(eng))
    assert inbox[0] == {"type": "auth", "token": TOKEN}
    assert set(eng.log["origins"]) == {ORIGIN}
    assert eng.log["hello"]["side"] == "mix" and eng.log["hello"]["source"] == "iphone"
    assert eng.log["hello"]["sample_rate"] == 16000 and eng.log["hello"]["format"] == "pcm_s16le"
    assert eng.log["frames"] == [3200, 3200, 3200]
    assert [m["type"] for m in got][:2] == ["engine", "tick"]
    assert got[0]["status"] == "up"
    tick = got[1]
    assert tick["stable"]["alert"] == "red" and tick["verdict"]["scores"]["confidence_label"] == "medium"
    assert eng.log["dismiss_ws"] == 1 and eng.log["dismiss_http"] == 1
    assert eng.log["stopped"] is True                       # the phone's Stop reached the engine (which wipes its ring)


def test_wrong_token_is_loud_and_stops():
    async def script(ws, inbox):
        await asyncio.sleep(1)

    async def go():
        srv, port, inbox = await fake_phone(script, token_ok=False)
        try:
            b = bridge.Bridge(f"ws://127.0.0.1:{port}", "http://127.0.0.1:1", ORIGIN, "WRONG-CODE", retry_s=0.1)
            return await asyncio.wait_for(b.run(asyncio.Event()), 10)
        finally:
            srv.close()

    assert asyncio.run(go()) == "bad_token"


def test_engine_busy_and_down_and_refused_are_reported_to_the_phone():
    results = {}

    async def go(engine_url, key):
        got = []

        async def script(ws, inbox):
            await ws.send(json.dumps({"type": "started"}))
            m = json.loads(await asyncio.wait_for(ws.recv(), 5))
            got.append(m)
            await asyncio.sleep(0.2)

        srv, port, _ = await fake_phone(script)
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
    async def script(ws, inbox):
        await ws.send(json.dumps({"type": "started"}))
        await asyncio.sleep(0.6)
        await ws.send(b"\x00\x00" * 1600)
        await asyncio.sleep(0.3)
        await ws.close()                                     # phone vanishes mid-session (cable pulled)

    async def go(engine):
        srv, port, inbox = await fake_phone(script)
        try:
            await run_bridge(port, engine.url, 3.0)
        finally:
            srv.close()
        return inbox

    with FakeEngine() as eng:
        inbox = asyncio.run(go(eng))
    assert eng.log["stopped"] is True                        # engine told to stop (it wipes the ring)
    assert len([m for m in inbox if m.get("type") == "auth"]) >= 2      # it reconnected and paired again


def test_waits_quietly_when_the_phone_app_is_not_there():
    async def go():
        b = bridge.Bridge(f"ws://127.0.0.1:{free_port()}", "http://127.0.0.1:1", ORIGIN, TOKEN, retry_s=0.1)
        stop = asyncio.Event()
        t = asyncio.ensure_future(b.run(stop))
        await asyncio.sleep(0.6)
        stop.set()
        return await asyncio.wait_for(t, 5)

    assert asyncio.run(go()) == "interrupted"


def test_pure_helpers():
    assert bridge.is_loopback_url("http://127.0.0.1:8000")
    assert bridge.is_loopback_url("http://localhost:8000")
    assert not bridge.is_loopback_url("http://192.168.1.5:8000")
    assert not bridge.is_loopback_url("https://example.com")
    assert not bridge.is_loopback_url("ws://127.0.0.1:8000")
    t = bridge.tick_message(VERDICT)
    assert t["type"] == "tick" and t["stable"]["alert"] == "red" and t["verdict"]["transcript"] == "read me the code"
    assert bridge.tick_from_ws_verdict({"seq": 3, "t": 9.0, "tier": "human", "p_ai": 0.1, "p_scam": 0, "confidence": 0.5,
                                        "stable": {"tier": "human"}})["stable"] == {"tier": "human"}
    assert "scam 90" in bridge.status_line(t)


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
