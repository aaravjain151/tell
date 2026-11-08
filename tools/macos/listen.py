#!/usr/bin/env python3
"""Doublespeak live listener: feeds a call's audio to the LOCAL API and shows the live verdict.

    python3 tools/macos/listen.py --now   [--process NAME]     start listening immediately (tap_audio --stream)
    python3 tools/macos/listen.py --watch [--call-process NAME ...]   arm by itself when a call app produces audio
    python3 tools/macos/listen.py --file call.wav               replay a file at real-time speed (demo / tests)

Privacy (same rules as the app): the audio is analysed in RAM on this machine only. Nothing is recorded or sent
anywhere; the API is on loopback and this tool REFUSES any non-loopback --url. It is passive: it never speaks to the
caller. Notifications use fixed wording and never contain what was said. It stops on Ctrl-C, when the call ends, or after
90 s of silence, and the API wipes its buffer when the stream closes.

--watch only arms for call apps (default: FaceTime, Phone, callservicesd, avconferenced, zoom.us, WhatsApp,
Microsoft Teams), matched by exact process name or bundle id. It never arms on music or browsers unless you list them
with --call-process. Needs the `websockets` package (installed with services/api/requirements.txt).
"""
from __future__ import annotations

import argparse
import array
import asyncio
import json
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
DEFAULT_TAP = ROOT / "tools" / "macos" / "tap_audio" / ".build" / "release" / "tap_audio"
DEFAULT_CALL_PROCESSES = ("FaceTime", "Phone", "callservicesd", "avconferenced", "zoom.us", "WhatsApp",
                          "Microsoft Teams")
CONSENT = ("Doublespeak will listen to this call. The audio is analysed in memory on THIS machine only: nothing is "
           "recorded and nothing is sent anywhere. It never speaks to the caller.")
FRAME_MS = 100
FRAME_BYTES = 16000 * FRAME_MS // 1000 * 2
SILENCE_PEAK = 40                      # int16 peak below this counts as silence
NOTIFY_TEXT = {"amber": "Possible scam call. Be careful with money and codes.",
               "red": "Likely scam call. Do not share money, codes or passwords."}
END_POLLS = 3                          # consecutive polls without the call app before we call the call over


# ---------------------------------------------------------------------------------------------- pure helpers
def is_loopback_url(url: str) -> bool:
    try:
        u = urlparse(url)
    except ValueError:
        return False
    return u.scheme in ("http", "https") and (u.hostname or "") in LOOPBACK


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--now", action="store_true", help="start listening immediately")
    mode.add_argument("--watch", action="store_true", help="arm automatically when a call app produces audio")
    mode.add_argument("--file", metavar="WAV", help="replay a file at real-time speed")
    ap.add_argument("--url", default="http://127.0.0.1:8000", help="API base URL (loopback only)")
    ap.add_argument("--origin", default="http://localhost:5173", help="an allowed UI origin (DOUBLESPEAK_CORS_ORIGINS)")
    ap.add_argument("--call-process", action="append", metavar="NAME", help="call app process name (repeatable); "
                    "replaces the default list")
    ap.add_argument("--process", metavar="NAME", help="with --now: tap only this app (default: system audio)")
    ap.add_argument("--tap-call-app-only", action="store_true",
                    help="--watch: tap only the detected call app instead of all system audio (can hear silence if the "
                         "call is rendered by another process)")
    ap.add_argument("--tap", default=str(DEFAULT_TAP), help="path to the tap_audio binary")
    ap.add_argument("--side", choices=("far", "near", "mix"), default="far")
    ap.add_argument("--silence-s", type=float, default=90.0, help="stop after this many seconds of silence")
    ap.add_argument("--poll-s", type=float, default=2.0, help="--watch: seconds between tap_audio --list polls")
    ap.add_argument("--speed", type=float, default=1.0, help="--file: 1 = real time")
    ap.add_argument("--sound", action="store_true", help="play a sound with notifications (off by default)")
    ap.add_argument("--no-notify", action="store_true", help="never show a macOS notification")
    ap.add_argument("--i-understand", action="store_true", help="accept the consent line non-interactively")
    a = ap.parse_args(argv)
    if a.speed <= 0 or a.silence_s <= 0 or a.poll_s <= 0:
        ap.error("--speed, --silence-s and --poll-s must be positive")
    a.call_process = list(a.call_process) if a.call_process else list(DEFAULT_CALL_PROCESSES)
    return a


def parse_list(text: str) -> list[tuple[str, str]]:
    """`tap_audio --list` lines: name TAB bundle TAB pid N  ->  [(name, bundle)]."""
    out = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].strip():
            out.append((parts[0].strip(), parts[1].strip()))
    return out


def match_call(listing: list[tuple[str, str]], call_processes: list[str]) -> str | None:
    """The first call-app name (in --call-process order) producing audio. Exact, case-insensitive, name or bundle id."""
    for want in call_processes:
        w = want.lower()
        for name, bundle in listing:
            if name.lower() == w or bundle.lower() == w:
                return name
    return None


class WatchState:
    """Arm when a call app produces audio; call it over after END_POLLS polls without it (bridges silent gaps)."""

    def __init__(self, end_polls: int = END_POLLS) -> None:
        self.end_polls = end_polls
        self.armed: str | None = None
        self._missing = 0

    def update(self, matched: str | None) -> str | None:
        """-> 'arm' | 'stop' | None."""
        if self.armed is None:
            if matched is None:
                return None
            self.armed, self._missing = matched, 0
            return "arm"
        if matched is not None:
            self._missing = 0
            return None
        self._missing += 1
        if self._missing >= self.end_polls:
            self.armed = None
            return "stop"
        return None

    def disarm(self) -> None:
        self.armed, self._missing = None, 0


def notification_for(prev: str, new: str) -> str | None:
    """Fixed text, only when the stable alert CHANGES to amber or red."""
    return NOTIFY_TEXT.get(new) if new != prev and new in NOTIFY_TEXT else None


def peak(frame: bytes) -> int:
    a = array.array("h")
    a.frombytes(frame[: len(frame) // 2 * 2])
    if sys.byteorder == "big":
        a.byteswap()
    return max((abs(x) for x in a), default=0)


def status_line(m: dict, latency: float | None) -> str:
    st = m.get("stable") or {}
    lat = f" lat={latency:.1f}s" if latency is not None else ""
    return (f"LISTENING | {m.get('t', 0):6.1f}s  shown={st.get('tier', '?'):<14} {st.get('state', '?'):<9} "
            f"alert={st.get('alert', '?'):<5}| raw={m.get('tier')} p_scam={m.get('p_scam')} p_ai={m.get('p_ai')}{lat}")


def notify(text: str, sound: bool) -> None:
    if sys.platform != "darwin":
        return
    script = f'display notification "{text}" with title "Doublespeak"' + (' sound name "Ping"' if sound else "")
    try:
        subprocess.run(["osascript", "-e", script], timeout=5, check=False, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        pass


def say(msg: str) -> None:
    print(msg, flush=True)


def banner(on: bool, label: str = "") -> None:
    if on:
        say(f"\n=== LISTENING ({label}) | analysed in memory on this machine, nothing recorded or sent | Ctrl-C stops ===")
    else:
        say("=== NOT LISTENING ===")
    if sys.stdout.isatty():
        sys.stdout.write(f"\033]0;{'LISTENING - Doublespeak' if on else 'Doublespeak'}\007")
        sys.stdout.flush()


def consent(args: argparse.Namespace) -> bool:
    say(CONSENT)
    if args.i_understand:
        return True
    if not sys.stdin.isatty():
        say("Not accepted: pass --i-understand to confirm (no interactive terminal).")
        return False
    return input("Listen? [y/N] ").strip().lower() in ("y", "yes")


def list_producing(tap: str) -> list[tuple[str, str]]:
    try:
        r = subprocess.run([tap, "--list"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_list(r.stdout)


def create_session(base: str, origin: str) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # a loopback call must never use a proxy
    req = urllib.request.Request(base.rstrip("/") + "/session", method="POST", data=b"{}",
                                 headers={"Origin": origin, "Content-Type": "application/json"})
    with opener.open(req, timeout=10) as r:
        return json.loads(r.read())


# ---------------------------------------------------------------------------------------------- audio sources
def load_pcm16(path: str) -> bytes:
    sys.path.insert(0, str(ROOT / "services" / "api"))
    import numpy as np
    from doublespeak import audio
    x, _sr, _ms = audio.decode(Path(path).read_bytes())
    return (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()


async def file_frames(path: str, speed: float):
    pcm = await asyncio.get_running_loop().run_in_executor(None, load_pcm16, path)
    loop = asyncio.get_running_loop()
    t0, sent = loop.time(), 0
    for i in range(0, len(pcm), FRAME_BYTES):
        chunk = pcm[i:i + FRAME_BYTES]
        yield chunk
        sent += len(chunk)
        await asyncio.sleep(max(0.0, t0 + (sent / 2 / 16000) / speed - loop.time()))


async def tap_frames(tap: str, process: str | None):
    cmd = [tap, "--stream"] + (["--process", process] if process else [])
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        while True:
            try:
                chunk = await proc.stdout.readexactly(FRAME_BYTES)
            except asyncio.IncompleteReadError:
                return
            yield chunk
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()


# ---------------------------------------------------------------------------------------------- one live session
async def run_session(args: argparse.Namespace, frames, label: str, stop: asyncio.Event) -> str:
    """Stream `frames` to the API until they end, `stop` is set, or silence lasts too long. Returns the reason."""
    import websockets

    info = await asyncio.get_running_loop().run_in_executor(None, create_session, args.url, args.origin)
    u = urlparse(args.url)
    ws_url = f"{'wss' if u.scheme == 'https' else 'ws'}://{u.netloc}{info['ws_path']}"
    reason = "ended"
    async with websockets.connect(ws_url, additional_headers={"Origin": args.origin}, max_size=1 << 20,
                                  proxy=None) as ws:
        await ws.send(json.dumps({"type": "hello", "token": info["token"], "sample_rate": 16000,
                                  "format": "pcm_s16le", "side": args.side, "source": label}))
        first = json.loads(await ws.recv())
        if first.get("type") != "ready":
            return f"server refused: {first.get('code', first)}"
        banner(True, label)
        loop = asyncio.get_running_loop()
        t_start = loop.time()
        sent_at: list[float] = []                       # wall time at which each whole second of audio was sent
        state = {"alert": "none", "sent": 0}

        async def reader() -> None:
            async for raw in ws:
                m = json.loads(raw)
                if m.get("type") == "verdict":
                    end = m.get("window", [0, 0])[1]
                    idx = int(end) - 1
                    lat = loop.time() - sent_at[idx] if 0 <= idx < len(sent_at) else None
                    say(status_line(m, lat))
                    new = (m.get("stable") or {}).get("alert", "none")
                    text = notification_for(state["alert"], new)
                    state["alert"] = new
                    if text and not args.no_notify:
                        notify(text, args.sound)
                elif m.get("type") in ("warn", "error"):
                    say(f"LISTENING | {m.get('type')}: {m.get('code')}")
                    if m.get("type") == "error":
                        return
                elif m.get("type") == "final":
                    return

        rd = asyncio.ensure_future(reader())
        quiet_s = 0.0
        last_ping = loop.time()
        diag = {"t": loop.time(), "peak": 0.0, "warned": False}
        try:
            async for frame in frames:
                if stop.is_set():
                    reason = "interrupted"
                    break
                if rd.done():
                    reason = "server closed"
                    break
                await ws.send(frame)
                state["sent"] += len(frame)
                while len(sent_at) < state["sent"] // 32000:
                    sent_at.append(loop.time())
                pk = peak(frame)
                diag["peak"] = max(diag["peak"], pk)
                if loop.time() - diag["t"] >= 6:
                    if diag["peak"] < SILENCE_PEAK:
                        say("LISTENING | hearing SILENCE: the call audio is not reaching the tap "
                            "(is the call answered on this Mac and playing through its speakers?)")
                        diag["warned"] = True
                    elif diag["warned"]:
                        say("LISTENING | audio is arriving again")
                        diag["warned"] = False
                    diag["t"], diag["peak"] = loop.time(), 0.0
                quiet_s = quiet_s + FRAME_MS / 1000 if pk < SILENCE_PEAK else 0.0
                if quiet_s >= args.silence_s:
                    reason = "silence"
                    break
                if loop.time() - last_ping > 5:
                    last_ping = loop.time()
                    await ws.send(json.dumps({"type": "ping"}))
            else:
                reason = "call ended"
        finally:
            if not rd.done():
                try:
                    if reason == "call ended":
                        await asyncio.sleep(2.0)       # let the last tick finish
                    await ws.send(json.dumps({"type": "stop"}))
                    await asyncio.wait_for(rd, 8)
                except Exception:  # noqa: BLE001 — closing anyway; the server wipes on disconnect
                    rd.cancel()
            banner(False)
    return reason


# ---------------------------------------------------------------------------------------------- modes
async def main_async(args: argparse.Namespace) -> int:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass
    try:
        if args.file:
            r = await run_session(args, file_frames(args.file, args.speed), "file", stop)
            say(f"stopped: {r}")
            return 0
        if args.now:
            r = await run_session(args, tap_frames(args.tap, args.process), "tap", stop)
            say(f"stopped: {r}")
            return 0
        return await watch(args, stop)
    except OSError as e:
        say(f"cannot reach the API at {args.url}: {e}")
        return 1


async def watch(args: argparse.Namespace, stop: asyncio.Event) -> int:
    ws_state = WatchState()
    say(f"watching for a call (apps: {', '.join(args.call_process)}); not listening yet")
    task: asyncio.Task | None = None
    sess_stop = asyncio.Event()
    idle_said = False
    while not stop.is_set():
        loop = asyncio.get_running_loop()
        listing = await loop.run_in_executor(None, list_producing, args.tap)
        ev = ws_state.update(match_call(listing, args.call_process))
        if task is not None and task.done():
            try:
                say(f"stopped: {task.result()}")
            except Exception as e:  # noqa: BLE001
                say(f"stopped: {e}")
            task = None
            ws_state.disarm()                            # the session ended on its own (silence, server): re-arm later
        if ev == "arm" and task is None:
            say(f"call detected ({ws_state.armed}): arming")
            sess_stop = asyncio.Event()
            task = asyncio.ensure_future(run_session(args, tap_frames(args.tap, ws_state.armed if args.tap_call_app_only else None), "tap", sess_stop))
            idle_said = False
        elif ev == "stop" and task is not None:
            say("call ended: stopping")
            sess_stop.set()
        elif task is None and not idle_said:
            say("not listening (waiting for a call app)")
            idle_said = True
        try:
            await asyncio.wait_for(stop.wait(), args.poll_s)
        except asyncio.TimeoutError:
            pass
    if task is not None:
        sess_stop.set()
        try:
            await asyncio.wait_for(task, 12)
        except Exception:  # noqa: BLE001
            task.cancel()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not is_loopback_url(args.url):
        print("refusing: --url must be a loopback address (127.0.0.1, localhost or ::1). Caller audio never leaves "
              "this machine.", file=sys.stderr)
        return 2
    if not args.file and not Path(args.tap).exists():
        print(f"tap_audio not found at {args.tap}. Build it: cd tools/macos/tap_audio && swift build -c release",
              file=sys.stderr)
        return 2
    if args.file and not Path(args.file).exists():
        print(f"no such file: {args.file}", file=sys.stderr)
        return 2
    if not consent(args):
        return 1
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
