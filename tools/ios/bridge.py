#!/usr/bin/env python3
"""Doublespeak iPhone bridge: carries the phone's microphone audio over the USB cable to the LOCAL engine and the
engine's answers back to the phone.

    python3 tools/ios/bridge.py --token K7QM-4TXD            # token is shown on the phone's connection screen
    python3 tools/ios/bridge.py --token K7QM-4TXD --direct   # no iproxy: the app is the iOS Simulator (shares this Mac's loopback)

Why it is the other way round: an iPhone cannot reach this Mac's localhost. The app runs a tiny WebSocket SERVER on the
PHONE's loopback only (port 8765). `iproxy` (libimobiledevice, usbmuxd) forwards this Mac's 127.0.0.1:8765 to that port
over the USB cable, and this bridge connects to it as the CLIENT. No LAN, no Wi-Fi, no cloud: iproxy is never started
with -n (network devices), and the engine URL must be loopback.

Flow
  phone  <- {"type":"auth","token":...}            this bridge, first message (the phone refuses a wrong token)
  phone  -> {"type":"ready"}
  phone  -> {"type":"started"} + binary PCM16 16 kHz mono 100 ms frames   (the user tapped Start listening)
  engine <- POST /session (allowed Origin), WS /ws/stream hello {side:"mix", source:"iphone"}, frames as they arrive
  engine -> GET /live/events (SSE) verdict ticks (verdict + stable)  -> phone {"type":"tick",...}
  phone  -> {"type":"dismiss"}  -> engine WS dismiss + POST /live/dismiss
  phone  -> {"type":"stopped"}  -> engine stop; the engine wipes its buffer. Nothing is recorded here or on the phone.

It is passive: it never speaks to the caller. Needs the `websockets` package (services/api/requirements.txt).
"""
from __future__ import annotations

import argparse
import asyncio
import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from urllib.parse import urlparse

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
PHONE_PORT = 8765
CONSENT = ("Doublespeak will listen to this call through your iPhone's microphone (speaker mode). The audio travels "
           "over the USB cable to THIS computer only and is analysed in memory: nothing is recorded, stored or sent "
           "anywhere else. It never speaks to the caller. Tell the other person if your state requires it.")
PHONE_MAX_TEXT = 4096                     # the phone only sends tiny control messages


# ---------------------------------------------------------------------------------------------- pure helpers
def is_loopback_url(url: str) -> bool:
    try:
        u = urlparse(url)
    except ValueError:
        return False
    return u.scheme in ("http", "https") and (u.hostname or "") in LOOPBACK


def normalize_token(t: str) -> str:
    return "".join(ch for ch in t.upper() if ch.isalnum())


def tick_message(ev: dict) -> dict:
    """Engine /live/events verdict event -> the phone's tick message (same fields, unchanged)."""
    return {"type": "tick", "tick": ev.get("tick", 0), "elapsed_s": ev.get("elapsed_s", 0),
            "verdict": ev.get("verdict") or {}, "stable": ev.get("stable") or {}}


def tick_from_ws_verdict(m: dict) -> dict:
    """Fallback when the SSE feed is unavailable: the thin WS verdict (no transcript/tells) still has `stable`."""
    return {"type": "tick", "tick": m.get("seq", 0), "elapsed_s": m.get("t", 0),
            "verdict": {k: m.get(k) for k in ("tier", "p_ai", "p_scam", "confidence", "headline")},
            "stable": m.get("stable") or {}}


def status_line(msg: dict) -> str:
    st, v = msg.get("stable") or {}, msg.get("verdict") or {}
    sc = v.get("scores") or {}
    return (f"LISTENING | {st.get('tier', '?')} | alert {st.get('alert', 'none')} | scam {sc.get('scam', '-')} "
            f"| ai voice {sc.get('ai_voice', '-')} | how sure {sc.get('confidence_label', '-')}")


def loud(lines: list[str]) -> None:
    bar = "!" * 78
    print("\n".join([bar, *("!!  " + ln for ln in lines), bar]), file=sys.stderr, flush=True)


def say(msg: str) -> None:
    print(msg, flush=True)


def create_session(base: str, origin: str) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # a loopback call never uses a proxy
    req = urllib.request.Request(base.rstrip("/") + "/session", method="POST", data=b"{}",
                                 headers={"Origin": origin, "Content-Type": "application/json"})
    with opener.open(req, timeout=10) as r:
        return json.loads(r.read())


def post_dismiss(base: str, origin: str) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(base.rstrip("/") + "/live/dismiss", method="POST", data=b"{}",
                                 headers={"Origin": origin, "Content-Type": "application/json"})
    opener.open(req, timeout=5).read()


def engine_up(base: str) -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        opener.open(base.rstrip("/") + "/health", timeout=3).read()
        return True
    except Exception:  # noqa: BLE001
        return False


class SSEThread(threading.Thread):
    """Reads GET /live/events and hands each JSON event to `emit` (called on the thread; use call_soon_threadsafe)."""

    def __init__(self, base: str, origin: str, emit, on_fail) -> None:
        super().__init__(daemon=True)
        u = urlparse(base)
        self.host, self.port, self.origin = u.hostname or "127.0.0.1", u.port or 80, origin
        self.emit, self.on_fail = emit, on_fail
        self.stop_flag = threading.Event()
        self.conn: http.client.HTTPConnection | None = None
        self.sock: socket.socket | None = None

    def run(self) -> None:
        try:
            self.conn = http.client.HTTPConnection(self.host, self.port, timeout=12)
            self.conn.request("GET", "/live/events", headers={"Origin": self.origin, "Accept": "text/event-stream"})
            self.sock = self.conn.sock
            r = self.conn.getresponse()
            if r.status != 200:
                self.on_fail(f"events feed answered {r.status}")
                return
            while not self.stop_flag.is_set():
                line = r.readline()
                if not line:
                    break
                if line.startswith(b"data: "):
                    try:
                        self.emit(json.loads(line[6:]))
                    except ValueError:
                        pass
        except Exception as e:  # noqa: BLE001 — a closing socket on stop is normal
            if not self.stop_flag.is_set():
                self.on_fail(str(e))
        finally:
            try:
                if self.conn is not None:
                    self.conn.close()
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        # Never conn.close() from here: it waits for the reader thread's lock. Shutting the socket unblocks the read.
        self.stop_flag.set()
        try:
            if self.sock is not None:
                self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


# ---------------------------------------------------------------------------------------------- the bridge
class Engine:
    """One engine session: POST /session, WS /ws/stream, SSE ticks. Closed (and the engine wipes its buffer) on stop."""

    def __init__(self, bridge: "Bridge") -> None:
        self.b = bridge
        self.ws = None
        self.sse: SSEThread | None = None
        self.tasks: list[asyncio.Task] = []
        self.sse_ok = False
        self.closed = False

    async def open(self) -> str | None:
        """Returns None when ready, else a short reason: busy | refused | down."""
        import websockets
        b = self.b
        loop = asyncio.get_running_loop()
        try:
            info = await loop.run_in_executor(None, create_session, b.engine_url, b.origin)
        except urllib.error.HTTPError as e:
            return "busy" if e.code == 429 else "refused" if e.code == 403 else "down"
        except Exception:  # noqa: BLE001
            return "down"
        u = urlparse(b.engine_url)
        ws_url = f"{'wss' if u.scheme == 'https' else 'ws'}://{u.netloc}{info['ws_path']}"
        try:
            self.ws = await websockets.connect(ws_url, additional_headers={"Origin": b.origin}, max_size=1 << 20, proxy=None)
            await self.ws.send(json.dumps({"type": "hello", "token": info["token"], "sample_rate": 16000,
                                           "format": "pcm_s16le", "side": "mix", "source": "iphone"}))
            first = json.loads(await asyncio.wait_for(self.ws.recv(), 10))
        except Exception:  # noqa: BLE001
            return "down"
        if first.get("type") != "ready":
            return "refused"
        self.sse = SSEThread(b.engine_url, b.origin, lambda ev: loop.call_soon_threadsafe(self._on_sse, ev), self._sse_failed)
        self.sse.start()
        self.tasks = [asyncio.ensure_future(self._reader()), asyncio.ensure_future(self._pinger())]
        return None

    def _sse_failed(self, why: str) -> None:
        self.sse_ok = False

    def _on_sse(self, ev: dict) -> None:
        if self.closed:
            return
        t = ev.get("type")
        if t == "verdict":
            self.sse_ok = True
            self.b.to_phone(tick_message(ev))
            say(status_line(tick_message(ev)))
        elif t == "ended":
            self.b.to_phone({"type": "ended", "reason": str(ev.get("reason", "ended"))})

    async def _reader(self) -> None:
        try:
            async for raw in self.ws:
                m = json.loads(raw)
                if m.get("type") == "verdict" and not self.sse_ok:
                    self.b.to_phone(tick_from_ws_verdict(m))
                elif m.get("type") == "error":
                    self.b.to_phone({"type": "engine", "status": "error", "detail": str(m.get("code", "error"))})
                    return
                elif m.get("type") == "warn":
                    say(f"LISTENING | engine {m.get('code')}")
                elif m.get("type") == "final":
                    return
        except Exception:  # noqa: BLE001
            if not self.closed:
                self.b.to_phone({"type": "engine", "status": "down", "detail": "The engine closed the connection."})

    async def _pinger(self) -> None:
        while not self.closed:
            await asyncio.sleep(5)
            try:
                await self.ws.send(json.dumps({"type": "ping"}))
            except Exception:  # noqa: BLE001
                return

    async def frame(self, data: bytes) -> None:
        if self.ws is not None and not self.closed:
            try:
                await self.ws.send(data)
            except Exception:  # noqa: BLE001
                pass

    async def dismiss(self) -> None:
        if self.ws is not None and not self.closed:
            try:
                await self.ws.send(json.dumps({"type": "dismiss"}))
            except Exception:  # noqa: BLE001
                pass
        try:
            await asyncio.get_running_loop().run_in_executor(None, post_dismiss, self.b.engine_url, self.b.origin)
        except Exception:  # noqa: BLE001
            pass

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.sse:
            self.sse.stop()
        if self.ws is not None:
            try:
                await self.ws.send(json.dumps({"type": "stop"}))
                await asyncio.wait_for(asyncio.shield(self.tasks[0]), 3) if self.tasks else None
            except Exception:  # noqa: BLE001
                pass
            try:
                await self.ws.close()
            except Exception:  # noqa: BLE001
                pass
        for t in self.tasks:
            t.cancel()


class Bridge:
    def __init__(self, phone_url: str, engine_url: str, origin: str, token: str, retry_s: float = 1.5) -> None:
        self.phone_url, self.engine_url, self.origin = phone_url, engine_url, origin
        self.token, self.retry_s = token, retry_s
        self.phone = None
        self.engine: Engine | None = None
        self.paired = asyncio.Event()
        self.frames = 0

    def to_phone(self, msg: dict) -> None:
        if self.phone is not None:
            asyncio.ensure_future(self._send(msg))

    async def _send(self, msg: dict) -> None:
        try:
            await self.phone.send(json.dumps(msg, separators=(",", ":")))
        except Exception:  # noqa: BLE001
            pass

    async def run(self, stop: asyncio.Event) -> str:
        """Connect to the phone (retrying until it is there), relay until `stop`. Returns why it ended."""
        warned = False
        while not stop.is_set():
            try:
                reason = await self._session(stop)
            except (OSError, asyncio.TimeoutError):
                if not warned:
                    say("Waiting for the Doublespeak app on the phone: open it, keep it unlocked, check the cable.")
                    warned = True
                reason = "waiting"
            except Exception as e:  # noqa: BLE001 — websockets closed/handshake errors
                reason = f"disconnected: {type(e).__name__}"
            if reason == "bad_token":
                return reason
            if reason != "waiting":
                warned = False
                say(f"phone {reason}; reconnecting")
            await self._drop_engine()
            try:
                await asyncio.wait_for(stop.wait(), self.retry_s)
            except asyncio.TimeoutError:
                pass
        await self._drop_engine()
        return "interrupted"

    async def _session(self, stop: asyncio.Event) -> str:
        import websockets
        async with websockets.connect(self.phone_url, max_size=1 << 20, proxy=None, open_timeout=4,
                                      ping_interval=None) as ws:
            self.phone = ws
            try:
                await ws.send(json.dumps({"type": "auth", "token": self.token}))
                try:
                    first = json.loads(await asyncio.wait_for(ws.recv(), 6))
                except Exception:  # noqa: BLE001
                    loud(["The phone closed the connection right after the pairing code.",
                          "Check the code on the phone's connection screen, then run the command again."])
                    return "bad_token"
                if first.get("type") != "ready":
                    loud(["The phone did not accept the pairing code."])
                    return "bad_token"
                self.paired.set()
                say("Connected to the iPhone. On the phone, tap Start listening (call on speakerphone).")
                recv = asyncio.ensure_future(ws.recv())
                stopper = asyncio.ensure_future(stop.wait())
                try:
                    while True:
                        done, _ = await asyncio.wait({recv, stopper}, return_when=asyncio.FIRST_COMPLETED)
                        if stopper in done:
                            await self._send({"type": "ended", "reason": "bridge stopped"})
                            return "stopped"
                        msg = recv.result()
                        await self._on_phone(msg)
                        recv = asyncio.ensure_future(ws.recv())
                finally:
                    recv.cancel()
                    stopper.cancel()
            finally:
                self.phone = None
                self.paired.clear()

    async def _on_phone(self, msg) -> None:
        if isinstance(msg, bytes):
            self.frames += 1
            if self.engine is not None:
                await self.engine.frame(msg)
            return
        if len(msg) > PHONE_MAX_TEXT:
            return
        try:
            m = json.loads(msg)
        except ValueError:
            return
        kind = m.get("type") if isinstance(m, dict) else None
        if kind == "started":
            await self._drop_engine()
            eng = Engine(self)
            why = await eng.open()
            if why is not None:
                self.to_phone({"type": "engine", "status": why,
                               "detail": {"down": "The engine is not answering. Start it with make api.",
                                          "busy": "Another listening session is open.",
                                          "refused": "The engine refused this connection."}.get(why, why)})
                say(f"engine: {why}")
                await eng.close()
                return
            self.engine = eng
            self.to_phone({"type": "engine", "status": "up", "detail": ""})
            say("LISTENING | engine session open (side=mix, source=iphone)")
        elif kind == "stopped":
            await self._drop_engine()
            say("stopped by the phone; engine buffer wiped")
        elif kind == "dismiss":
            if self.engine is not None:
                await self.engine.dismiss()

    async def _drop_engine(self) -> None:
        e, self.engine = self.engine, None
        if e is not None:
            await e.close()


# ---------------------------------------------------------------------------------------------- iproxy / device
def have_tools(direct: bool) -> list[str]:
    missing = []
    if not direct:
        for t in ("iproxy", "idevice_id"):
            if shutil.which(t) is None:
                missing.append(t)
    return missing


def usb_devices() -> list[str]:
    try:
        r = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def port_free(port: int) -> bool:
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def start_iproxy(port: int, udid: str) -> subprocess.Popen:
    # USB only: never -n (network devices). Listens on 127.0.0.1 only.
    return subprocess.Popen(["iproxy", "-u", udid, "-s", "127.0.0.1", f"{port}:{PHONE_PORT}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Doublespeak iPhone bridge (USB only).")
    ap.add_argument("--token", required=True, help="pairing code shown on the phone (XXXX-XXXX)")
    ap.add_argument("--url", default="http://127.0.0.1:8000", help="engine base URL (loopback only)")
    ap.add_argument("--origin", default="http://localhost:5173", help="an allowed UI origin (DOUBLESPEAK_CORS_ORIGINS)")
    ap.add_argument("--port", type=int, default=PHONE_PORT, help="local port for the phone (iproxy listens here)")
    ap.add_argument("--udid", help="which iPhone, when several are plugged in")
    ap.add_argument("--direct", action="store_true",
                    help="no iproxy: connect straight to 127.0.0.1:PORT (the iOS Simulator shares this Mac's loopback)")
    ap.add_argument("--i-understand", action="store_true", help="accept the consent line non-interactively")
    return ap.parse_args(argv)


async def amain(a: argparse.Namespace) -> int:
    if not is_loopback_url(a.url):
        loud([f"Refusing --url {a.url}: the engine must be on this computer (loopback)."])
        return 2
    say(CONSENT)
    if not a.i_understand:
        if not sys.stdin.isatty():
            loud(["Not a terminal: pass --i-understand to accept the line above."])
            return 2
        try:
            input("Press Enter to continue, Ctrl-C to cancel. ")
        except (EOFError, KeyboardInterrupt):
            return 1
    proc = None
    if not a.direct:
        missing = have_tools(False)
        if missing:
            loud([f"MISSING: {', '.join(missing)}. The iPhone is reached over USB with iproxy (usbmuxd).",
                  "Install it:  brew install libimobiledevice", "Then run this command again."])
            return 2
        devs = usb_devices()
        if a.udid and a.udid not in devs:
            devs = []
        if not devs:
            loud(["NO iPhone FOUND over USB.", "Plug it in with a cable, unlock it, tap Trust on the phone, then run again.",
                  "Check:  idevice_id -l   (it should print the phone's id)"])
            return 2
        udid = a.udid or devs[0]
        if not port_free(a.port):
            loud([f"Port {a.port} on this computer is already in use (another iproxy or bridge?).", "Stop it, then run again."])
            return 2
        proc = start_iproxy(a.port, udid)
        say(f"iproxy: 127.0.0.1:{a.port} -> iPhone {udid[:8]}... :{PHONE_PORT} over USB")
        await asyncio.sleep(0.6)
        if proc.poll() is not None:
            loud(["iproxy exited at once: " + (proc.stderr.read().decode(errors='replace').strip()[:200] or "no message")])
            return 2
    if not engine_up(a.url):
        loud([f"The engine is not answering at {a.url}.", "Start it:  make api   (the bridge keeps trying; start listening after it is up)"])
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass
    bridge = Bridge(f"ws://127.0.0.1:{a.port}", a.url, a.origin, a.token)
    try:
        reason = await bridge.run(stop)
    finally:
        if proc is not None:
            proc.terminate()
    say(f"bridge stopped: {reason}")
    return 2 if reason == "bad_token" else 0


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(amain(parse_args(argv)))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
