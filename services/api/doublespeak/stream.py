"""Streaming routes: POST /session, WS /ws/stream, DELETE /session/{id}, POST /panic. Loopback only (see limits.py).

Auth that works from a browser (a WebSocket cannot send custom headers, and the token must never be in a URL):
  1. POST /session  (Origin must be an allowed UI origin)  ->  {session_id, token, ws_path, params}
  2. open WS /ws/stream; the FIRST message must be JSON
       {"type":"hello","token":...,"sample_rate":16000,"format":"pcm_s16le","side":"far|near|mix"}
     within 5 s. The token is random 256-bit, single-use and expires in 60 s.
  3. server -> {"type":"ready"}; then binary PCM16 mono 16 kHz frames (<= 128 KiB each), plus text control messages
     {"type":"ping"} (heartbeat; any message counts), {"type":"stop"}, {"type":"kill"}.
Server -> client: ready | verdict | warn(lagging|overloaded) | final{ticks,reason} | error{code} | pong.
Every end (stop, kill, heartbeat timeout, disconnect, max length, DELETE /session/{id}, POST /panic) wipes the ring.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request, WebSocket

from . import limits, session as sess_mod
from .session import MAX_TEXT_BYTES, REGISTRY, SIDES, Session

router = APIRouter()

WS_PATH = "/ws/stream"
CLOSE_BAD, CLOSE_AUTH, CLOSE_TIMEOUT, CLOSE_TOO_BIG = 4400, 4401, 4408, 1009


@router.post("/session")
async def create_session(request: Request) -> dict:
    origin = request.headers.get("origin")
    if origin is None or origin not in limits.allowed_origins():     # the guard already refused a *wrong* Origin
        raise HTTPException(403, "origin not allowed")
    try:
        s, token = REGISTRY.create()
    except sess_mod.Full:
        raise HTTPException(429, "too many live sessions") from None
    return {"session_id": s.id, "token": token, "ws_path": WS_PATH, "params": s.p}


@router.delete("/session/{sid}")
async def delete_session(sid: str) -> dict:
    if not REGISTRY.close(sid, "deleted"):
        raise HTTPException(404, "no such session")
    return {"deleted": True}


@router.post("/panic")
async def panic() -> dict:
    return {"wiped": REGISTRY.panic()}


class _Out:
    """Serialised sender; goes dead (silently) once the socket is gone."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.lock = asyncio.Lock()
        self.dead = False

    async def __call__(self, msg: dict) -> None:
        if self.dead:
            return
        async with self.lock:
            try:
                await asyncio.wait_for(self.ws.send_json(msg), 5.0)
            except Exception:  # noqa: BLE001 — client gone or too slow; the receive loop will notice
                self.dead = True


async def _fail(out: _Out, ws: WebSocket, code: str, close: int = CLOSE_BAD) -> None:
    await out({"type": "error", "code": code})
    try:
        await ws.close(code=close)
    except Exception:  # noqa: BLE001
        pass


def _parse(text: str) -> dict | None:
    if len(text.encode("utf-8", "replace")) > MAX_TEXT_BYTES:
        return None
    try:
        m = json.loads(text)
    except ValueError:
        return None
    return m if isinstance(m, dict) else None


async def _handshake(ws: WebSocket, out: _Out) -> Session | None:
    p = sess_mod.params()
    try:
        msg = await asyncio.wait_for(ws.receive(), p["hello_timeout_s"])
    except asyncio.TimeoutError:
        await _fail(out, ws, "hello_timeout", CLOSE_TIMEOUT)
        return None
    if msg["type"] != "websocket.receive":
        return None
    if msg.get("text") is None:                      # binary (audio) before a valid hello
        await _fail(out, ws, "hello_required", CLOSE_AUTH)
        return None
    hello = _parse(msg["text"])
    if hello is None or hello.get("type") != "hello":
        await _fail(out, ws, "hello_required", CLOSE_AUTH)
        return None
    token = hello.get("token")
    s = REGISTRY.redeem(token) if isinstance(token, str) and token else None
    if s is None:                                     # unknown, reused and expired tokens look identical
        await _fail(out, ws, "auth_failed", CLOSE_AUTH)
        return None
    if hello.get("sample_rate") != 16000 or hello.get("format") != "pcm_s16le" or hello.get("side") not in SIDES:
        REGISTRY.close(s.id, "bad_hello")
        await _fail(out, ws, "unsupported_format")
        return None
    s.activate(hello["side"])
    return s


@router.websocket(WS_PATH)
async def ws_stream(ws: WebSocket) -> None:
    # GuardMiddleware only sees http scopes, so the same Host/Origin rules are applied to the handshake here.
    if not limits.handshake_allowed(ws.headers.get("host", ""), ws.headers.get("origin")):
        await ws.close(code=1008)
        return
    await ws.accept()
    out = _Out(ws)
    s = None
    try:
        s = await _handshake(ws, out)
        if s is None:
            return
        await _serve(ws, out, s)
    finally:
        if s is not None:
            s.close(s.close_reason or "ended")
            s.cancel_job()
            REGISTRY.discard(s.id)


async def _serve(ws: WebSocket, out: _Out, s: Session) -> None:
    loop = asyncio.get_running_loop()
    wake = asyncio.Event()
    s.attach(loop, wake)
    await out({"type": "ready"})
    deadline = loop.time() + s.p["max_session_s"]
    wake_task = asyncio.ensure_future(wake.wait())
    recv: "asyncio.Future | None" = None
    reason = ""
    try:
        while not s.closed:
            left = deadline - loop.time()
            if left <= 0:
                reason = "max_length"
                break
            recv = asyncio.ensure_future(ws.receive())
            done, _ = await asyncio.wait({recv, wake_task}, timeout=min(s.p["heartbeat_s"], left),
                                         return_when=asyncio.FIRST_COMPLETED)
            if s.closed:                              # DELETE /session/{id} or POST /panic
                reason = s.close_reason
                break
            if recv not in done:
                if loop.time() >= deadline:
                    reason = "max_length"
                else:
                    reason = "heartbeat_timeout"
                    await out({"type": "error", "code": "heartbeat_timeout"})
                break
            msg = recv.result()
            recv = None
            if msg["type"] != "websocket.receive":    # disconnect
                reason = "disconnect"
                break
            data = msg.get("bytes")
            if data is not None:
                if len(data) > s.p["max_frame_bytes"]:
                    reason = "frame_too_large"
                    await _fail(out, ws, "frame_too_large", CLOSE_TOO_BIG)
                    return
                if len(data) % 2:
                    reason = "bad_frame"
                    await _fail(out, ws, "bad_frame")
                    return
                s.ingest(data)
                s.maybe_tick(out)
                continue
            m = _parse(msg.get("text") or "")
            kind = m.get("type") if m else None
            if kind == "ping":
                await out({"type": "pong"})
            elif kind in ("stop", "kill"):
                reason = kind
                break
            else:
                reason = "bad_message"
                await _fail(out, ws, "bad_message")
                return
    finally:
        if recv is not None and not recv.done():
            recv.cancel()
        wake_task.cancel()
        ticks = s.ticks
        s.close(reason or "ended")                    # wipe BEFORE telling the client, and drop any in-flight result
        s.cancel_job()
    if reason in ("stop", "kill", "max_length", "deleted", "panic"):
        await out({"type": "final", "ticks": ticks, "reason": reason})
    try:
        await ws.close()
    except Exception:  # noqa: BLE001
        pass
