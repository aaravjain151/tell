"""Hardening for the localhost API surface. Changes no analysis result; only decides who may call and how much.

Threat: the API listens on localhost, so (a) any web page the user has open can try to POST to it or read from it,
(b) DNS rebinding can make a hostile hostname resolve to 127.0.0.1, (c) a huge upload or many parallel analyses
can wedge a laptop mid-demo, (d) any other local process can connect to loopback without a browser at all, so every
route except PUBLIC_PATHS needs the per-install API token (api_token.py; docs/THREAT-MODEL.md). Everything is
configured by env vars (see .env.example) and read at call time.

CORS tradeoff: a page opened from file:// sends `Origin: null`. `null` is also what sandboxed iframes and some
redirects send, so any site can forge it. It is therefore refused unless listed explicitly in TELL_CORS_ORIGINS.
Anyone who opens apps/web/index.html from file:// must set TELL_CORS_ORIGINS=http://localhost:5173,null
(or, better, use `make web` and open http://localhost:5173). Requests that carry a disallowed Origin are rejected
outright (403), not just left without CORS headers, because CORS alone does not stop a simple cross-site POST from
being executed by the server.
"""
from __future__ import annotations

import asyncio
import json
import logging
import traceback
import weakref
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from fastapi import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import api_token, env as _env

log = logging.getLogger("tell.limits")

DEFAULT_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000")
DEFAULT_HOSTS = ("localhost", "127.0.0.1", "::1", "testserver")
MAX_TRANSCRIPT_CHARS = 20_000
QUEUE_WAIT_S = 20.0
MAX_WAITING = 3          # requests allowed to queue behind the running analysis; more get an immediate 503
_FORM_SLACK = 1 << 20    # multipart overhead + transcript on top of the audio limit
_SMALL_BODY = 1 << 20    # every other POST route


def _csv(name: str, default: tuple[str, ...]) -> list[str]:
    raw = _env.get(name)
    if raw is None or not raw.strip():
        return list(default)
    return [p.strip() for p in raw.split(",") if p.strip()]


def _float(name: str, default: float) -> float:
    try:
        v = float(_env.get(name, ""))
        return v if v > 0 else default
    except ValueError:
        return default


def allowed_origins() -> list[str]:
    return _csv("TELL_CORS_ORIGINS", DEFAULT_ORIGINS)


def allowed_hosts() -> set[str]:
    extra = [h.lower() for h in _csv("TELL_ALLOWED_HOSTS", ())]
    return {h.lower() for h in DEFAULT_HOSTS} | set(extra)


def max_upload_bytes() -> int:
    return int(_float("TELL_MAX_UPLOAD_MB", 25) * 1024 * 1024)


def max_audio_s() -> float:
    return _float("TELL_MAX_AUDIO_S", 180)


def analyze_timeout_s() -> float:
    return _float("TELL_ANALYZE_TIMEOUT_S", 60)


def _host_only(value: str) -> str:
    v = value.strip().lower()
    if v.startswith("["):                      # [::1]:8000
        return v[1:v.find("]")] if "]" in v else v
    if v.count(":") == 1:                      # host:port
        return v.split(":", 1)[0]
    return v


def handshake_allowed(host_header: str, origin: str | None) -> bool:
    """Same Host/Origin rules as GuardMiddleware, for WebSocket handshakes (the middleware only sees http scopes).
    A missing Origin is accepted (non-browser local tools); a browser always sends one."""
    if _host_only(host_header) not in allowed_hosts():
        return False
    return origin is None or origin in allowed_origins()


async def _reply(send: Send, status: int, detail: str, headers: list[tuple[bytes, bytes]] | None = None) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                            *(headers or [])]})
    await send({"type": "http.response.body", "body": body})


PUBLIC_PATHS = frozenset({"/health", "/ready", "/thresholds"})   # readable without the API token; no call content
QUERY_TOKEN_PATHS = frozenset({"/live/events"})                 # EventSource cannot set headers: ?token= only here


def companion_allow() -> bool:
    """TELL_COMPANION_ALLOW=1: emergency escape (OFF by default). A request that carries an ALLOWED browser Origin
    passes without the API token, i.e. the pre-token behaviour for pages and companions that cannot be paired.
    Any local process can forge an Origin header, so this reopens the hole the token closes. Never on by default."""
    return _env.get("TELL_COMPANION_ALLOW") == "1"


def needs_token(method: str, path: str, hdrs: dict[str, str]) -> bool:
    if path in PUBLIC_PATHS:
        return False
    if method == "OPTIONS" and "access-control-request-method" in hdrs:   # CORS preflight carries no data
        return False
    return True


class GuardMiddleware:
    """Outermost: Host allow-list (DNS rebinding), Origin allow-list (cross-site callers) and the per-install API
    token (other local processes; tell/api_token.py). Every route except PUBLIC_PATHS needs the token, deny by default."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        hdrs = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if _host_only(hdrs.get("host", "")) not in allowed_hosts():
            await _reply(send, 400, "host not allowed")
            return
        origin = hdrs.get("origin")
        if origin is not None and origin not in allowed_origins():
            await _reply(send, 403, "origin not allowed")
            return
        path = scope.get("path", "")
        presented = api_token.from_headers(hdrs)
        if path in QUERY_TOKEN_PATHS and scope.get("query_string"):
            q_token, rest = api_token.split_query(scope["query_string"])
            scope["query_string"] = rest          # in place: uvicorn's access log reads this same dict, so no token in logs
            presented = presented or q_token
        if needs_token(scope.get("method", "GET"), path, hdrs) and not api_token.matches(presented):
            if not (companion_allow() and origin is not None):
                extra = [(b"www-authenticate", b'Bearer realm="tell"')]
                if origin is not None:                 # allowed page: let it READ the 401 and show "pair this page"
                    extra += [(b"access-control-allow-origin", origin.encode("latin-1")), (b"vary", b"Origin")]
                await _reply(send, 401, "API token required: see make pair-url", extra)
                return
        await self.app(scope, receive, send)


class _TooLarge(BaseException):
    """BaseException on purpose: FastAPI's body parsing wraps every `Exception` into a 400 and would swallow this."""


class BodyLimitMiddleware:
    """Counts request-body bytes as they stream in and stops at the limit, so an endless upload is never buffered."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return
        if scope["path"] == "/analyze":
            limit = max_upload_bytes() + _FORM_SLACK
            msg = f"audio too large: limit is {max_upload_bytes() // (1024 * 1024)} MB"
        elif scope["path"].startswith(("/blocklist", "/feedback")):
            limit, msg = 8192, "request body too large"
        else:
            limit, msg = _SMALL_BODY, "request body too large"
        declared = dict(scope["headers"]).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            await _reply(send, 413, msg)
            return
        seen = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal seen
            m = await receive()
            if m["type"] == "http.request":
                seen += len(m.get("body", b""))
                if seen > limit:
                    raise _TooLarge()
            return m

        async def tracking_send(m: Message) -> None:
            nonlocal started
            if m["type"] == "http.response.start":
                started = True
            await send(m)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _TooLarge:
            if started:
                raise
            await _reply(send, 413, msg)


def install(app: Any) -> None:
    """Wire CORS, Host/Origin guards, body limit and the generic error handler onto the app (last added = outermost)."""
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins(), allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Content-Type", "Authorization", "X-Tell-Token"], allow_credentials=False)
    app.add_middleware(GuardMiddleware)

    from fastapi.responses import JSONResponse

    async def _unhandled(request: Any, exc: Exception) -> Any:
        _log_failure("request", exc)
        return JSONResponse({"detail": "internal error"}, status_code=500)

    app.add_exception_handler(Exception, _unhandled)


def _log_failure(what: str, exc: BaseException) -> None:
    """Log class + stack frames only: exception messages can echo transcript or audio content."""
    frames = "".join(traceback.format_tb(exc.__traceback__)) if exc.__traceback__ else ""
    log.error("%s failed: %s\n%s", what, type(exc).__name__, frames)


# --- concurrency: one analysis at a time, short queue, never on the event loop -------------------------------------

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analyze")
_gates: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()
_waiting = 0


def _gate() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    g = _gates.get(loop)
    if g is None:
        g = _gates[loop] = asyncio.Semaphore(1)
    return g


def _busy() -> HTTPException:
    return HTTPException(503, "another analysis is running; try again in a few seconds",
                         headers={"Retry-After": "10"})


def _checked(fn: Callable[..., Any], data: bytes | None, transcript: str | None) -> Any:
    """Runs in the worker thread: duration cap after decode, then the real analysis."""
    if data:
        from . import audio as audio_mod
        cap = max_audio_s()
        try:
            _x, _sr, dur_ms = audio_mod.decode(data)
        except audio_mod.AudioTooLong:
            raise HTTPException(413, f"audio too long: limit is {cap:g} s") from None
        if dur_ms / 1000 > cap:
            raise HTTPException(413, f"audio too long: limit is {cap:g} s")
    return fn(data, transcript)


async def run_analysis(fn: Callable[[bytes | None, str | None], Any], data: bytes | None, transcript: str | None) -> Any:
    """Gate, thread, time-limit and sanitise one analysis. AudioDecodeError passes through for the route to map to 415."""
    global _waiting
    from .audio import AudioDecodeError
    if transcript is not None and len(transcript) > MAX_TRANSCRIPT_CHARS:
        raise HTTPException(413, f"transcript too long: limit is {MAX_TRANSCRIPT_CHARS} characters")
    gate = _gate()
    if gate.locked():
        if _waiting >= MAX_WAITING:
            raise _busy()
        _waiting += 1
        try:
            await asyncio.wait_for(gate.acquire(), QUEUE_WAIT_S)
        except asyncio.TimeoutError:
            raise _busy() from None
        finally:
            _waiting -= 1
    else:
        await gate.acquire()
    loop = asyncio.get_running_loop()
    try:
        fut = loop.run_in_executor(_executor, _checked, fn, data, transcript)
    except BaseException:
        gate.release()
        raise

    def _done(f: "asyncio.Future[Any]") -> None:   # the gate frees only when the thread really ends
        if not f.cancelled():
            f.exception()                          # mark retrieved (we may have stopped waiting)
        gate.release()

    fut.add_done_callback(_done)
    try:
        return await asyncio.wait_for(asyncio.shield(fut), analyze_timeout_s())
    except asyncio.TimeoutError:
        raise HTTPException(504, f"analysis timed out after {analyze_timeout_s():g} s; "
                                 "it may still be finishing in the background") from None
    except (HTTPException, AudioDecodeError):
        raise
    except (EOFError, __import__("wave").Error):
        raise AudioDecodeError("could not decode audio") from None
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        _log_failure("analysis", e)
        raise HTTPException(500, "analysis failed") from None
