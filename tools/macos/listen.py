#!/usr/bin/env python3
"""Tell live listener: feeds a call's audio to the LOCAL API and shows the live verdict.

    python3 tools/macos/listen.py --now   [--process NAME]     start listening immediately (tap_audio --stream)
    python3 tools/macos/listen.py --watch [--call-process NAME ...]   arm by itself when a call app produces audio
    python3 tools/macos/listen.py --file call.wav               replay a file at real-time speed (demo / tests)

Privacy (same rules as the app): the audio is analysed in RAM on this machine only. Nothing is recorded or sent
anywhere; the API is on loopback and this tool REFUSES any non-loopback --url. It is passive: it never speaks to the
caller. Notifications use fixed wording and never contain what was said. It stops on Ctrl-C, when the call ends, or after
90 s of silence, and the API wipes its buffer when the stream closes.

Auth: the engine requires its per-install API token to create a session. This tool reads it from the engine's 0600
file (~/Library/Application Support/Tell/api_token, or TELL_API_TOKEN_FILE / TELL_API_TOKEN) and sends it as the
X-Tell-Token header; the error names the path when the file is missing (start the engine once to create it).

--watch only arms for call apps (default: FaceTime, Phone, callservicesd, avconferenced, zoom.us, WhatsApp,
Microsoft Teams), matched by exact process name or bundle id. It never arms on music or browsers unless you list them
with --call-process. OPT-IN labelled capture (OFF by default, for building real evaluation data): with
    --save-labeled DIR --label {human,ai,scam_human,scam_ai} --speaker NAME --consent-note TEXT
the 16 kHz PCM it analysed is written to DIR/<label>/<timestamp>.wav (0600) with a JSON sidecar (label, speaker, consent
note, date, source, raw scores per tick). All four flags are required, typed on the command line, never defaulted.
A loud SAVING AUDIO TO DISK banner shows and stays in the LISTENING line. Only record people who agreed.

Needs the `websockets` package (installed with services/api/requirements.txt).
"""
from __future__ import annotations

import argparse
import array
import asyncio
import datetime
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
DEFAULT_TAP = ROOT / "tools" / "macos" / "tap_audio" / ".build" / "release" / "tap_audio"
VERDICT_AUDIO_DIR = ROOT / "apps" / "web" / "verdict_audio"   # pre-rendered spoken verdicts (make verdict-audio)
DEFAULT_CALL_PROCESSES = ("FaceTime", "Phone", "callservicesd", "avconferenced", "zoom.us", "WhatsApp",
                          "Microsoft Teams")
CONSENT = ("Tell will listen to this call. The audio is analysed in memory on THIS machine only: nothing is "
           "recorded and nothing is sent anywhere. It never speaks to the caller.")
FRAME_MS = 100
FRAME_BYTES = 16000 * FRAME_MS // 1000 * 2
SILENCE_PEAK = 40                      # int16 peak below this counts as silence
NOTIFY_TEXT = {"amber": "Possible scam call. Be careful with money and codes.",
               "red": "Likely scam call. Do not share money, codes or passwords."}
LABELS = ("human", "ai", "scam_human", "scam_ai")
SAVE_BANNER = "!!! SAVING AUDIO TO DISK (labelled capture) !!!"
SAVE_TAG = " | SAVING AUDIO TO DISK"
NETWORK_FS = ("smbfs", "nfs", "afpfs", "webdav", "cifs", "ftp", "fuse", "osxfuse", "macfuse", "sshfs", "9p", "ncpfs", "davfs")
END_POLLS = 3                          # consecutive polls without the call app before we call the call over
STOP_WAIT_S = 12.0                     # after `stop`: the API's final flush is bounded at 6 s (+ an in-flight tick)


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
    ap.add_argument("--origin", default="http://localhost:5173", help="an allowed UI origin (TELL_CORS_ORIGINS)")
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
    ap.add_argument("--speak", action="store_true", help="speak the verdict aloud when the stable tier changes, using "
                    "the PRE-RENDERED local Gradium clips in apps/web/verdict_audio (run `make verdict-audio` first). "
                    "No network, no caller audio — it only plays a local file. Off by default.")
    ap.add_argument("--no-notify", action="store_true", help="never show a macOS notification")
    ap.add_argument("--save-labeled", metavar="DIR", help="OPT-IN: write the analysed audio + sidecar under DIR/<label>/ "
                    "(needs --label, --speaker, --consent-note)")
    ap.add_argument("--label", choices=LABELS, help="with --save-labeled: what the voice on this call really is")
    ap.add_argument("--speaker", metavar="NAME", help="with --save-labeled: who is speaking")
    ap.add_argument("--consent-note", metavar="TEXT", help="with --save-labeled: how/that the speaker consented")
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


def status_line(m: dict, latency: float | None, saving: bool = False) -> str:
    st = m.get("stable") or {}
    lat = f" lat={latency:.1f}s" if latency is not None else ""
    return (f"LISTENING{SAVE_TAG if saving else ''} | {m.get('t', 0):6.1f}s  shown={st.get('tier', '?'):<14} {st.get('state', '?'):<9} "
            f"alert={st.get('alert', '?'):<5}| raw={m.get('tier')} p_scam={m.get('p_scam')} p_ai={m.get('p_ai')}{lat}")


TAIL_TEXT = {"scored": "last seconds scored", "covered": "last seconds already covered",
             "no_new_audio": "no unscored audio", "silence": "last seconds were silence",
             "timeout": "last seconds NOT scored (engine too slow)", "failed": "last seconds NOT scored (analysis failed)",
             "closed": "last seconds NOT scored (session wiped)"}


def final_line(final: dict, stable: dict | None) -> str:
    """One line after the session ends: the final stable answer and what happened to the unscored tail."""
    st = stable or {}
    tail = TAIL_TEXT.get(final.get("tail") or "", "tail not reported")
    return (f"FINAL | shown={st.get('tier', 'none')} {st.get('state', '-')} alert={st.get('alert', 'none')} | "
            f"{final.get('ticks', 0)} verdicts | {tail}")


def notify(text: str, sound: bool) -> None:
    if sys.platform != "darwin":
        return
    script = f'display notification "{text}" with title "Tell"' + (' sound name "Ping"' if sound else "")
    try:
        subprocess.run(["osascript", "-e", script], timeout=5, check=False, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        pass


def say(msg: str) -> None:
    print(msg, flush=True)


def play_verdict(tier: str, audio_dir: Path = VERDICT_AUDIO_DIR) -> bool:
    """Play the PRE-RENDERED local clip for `tier` with afplay. No network; it only reads a local file. Returns
    True if a file was found and playback was started. Never raises."""
    if sys.platform != "darwin" or not tier:
        return False
    wav = audio_dir / f"{tier}.wav"
    if not wav.is_file():
        return False
    try:
        subprocess.Popen(["afplay", str(wav)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def banner(on: bool, label: str = "", saving: bool = False) -> None:
    if on and saving:
        say(f"\n{SAVE_BANNER}")
        say(f"=== LISTENING ({label}){SAVE_TAG} | nothing is sent anywhere | Ctrl-C stops ===")
    elif on:
        say(f"\n=== LISTENING ({label}) | analysed in memory on this machine, nothing recorded or sent | Ctrl-C stops ===")
    else:
        say("=== NOT LISTENING ===")
    if sys.stdout.isatty():
        sys.stdout.write(f"\033]0;{'LISTENING - Tell' if on else 'Tell'}\007")
        sys.stdout.flush()


def consent(args: argparse.Namespace) -> bool:
    say(CONSENT)
    if args.save_labeled:
        say(f"{SAVE_BANNER}\nThis run WRITES the call audio to {args.save_labeled}/{args.label}/ for speaker "
            f"{args.speaker!r}. Consent noted: {args.consent_note!r}. Only record people who agreed.")
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


class TokenMissing(RuntimeError):
    pass


def api_token_path() -> Path:
    """Same place the engine writes it (services/api/tell/api_token.py): TELL_API_TOKEN_FILE, else per-user app support."""
    override = os.environ.get("TELL_API_TOKEN_FILE")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Tell" / "api_token"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "tell" / "api_token"


def load_api_token() -> str:
    """TELL_API_TOKEN, else the engine's 0600 token file. Never printed."""
    env = (os.environ.get("TELL_API_TOKEN") or "").strip()
    if env:
        return env
    p = api_token_path()
    try:
        tok = p.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        tok = ""
    if not tok:
        raise TokenMissing(f"no Tell API token at {p}. Start the engine once (make demo or make api) to create it, "
                           "then run this again.")
    return tok


def create_session(base: str, origin: str, api_token: str | None = None) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # a loopback call must never use a proxy
    headers = {"Origin": origin, "Content-Type": "application/json"}
    if api_token:
        headers["X-Tell-Token"] = api_token
    req = urllib.request.Request(base.rstrip("/") + "/session", method="POST", data=b"{}", headers=headers)
    with opener.open(req, timeout=10) as r:
        return json.loads(r.read())


# ---------------------------------------------------------------------------------------------- labelled capture
def network_mounts(mount_text: str) -> list[str]:
    """Mount points of network file systems from `mount` output ('src on /path (smbfs, ...)')."""
    out = []
    for line in mount_text.splitlines():
        if " on " not in line or "(" not in line:
            continue
        mp, _, rest = line.partition(" on ")[2].partition(" (")
        kinds = {k.strip().lower() for k in rest.rstrip(")").split(",")}
        if kinds & set(NETWORK_FS) or line.startswith("//"):
            out.append(mp)
    return out


def is_network_path(path: Path, mount_text: str | None = None) -> bool:
    if mount_text is None:
        try:
            mount_text = subprocess.run(["mount"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return True                                   # cannot tell: refuse rather than guess
    p = str(path.resolve())
    return any(p == m or p.startswith(m.rstrip("/") + "/") for m in network_mounts(mount_text))


def save_error(a: argparse.Namespace, mount_text: str | None = None) -> str | None:
    """None when capture is off or fully and validly requested; otherwise why we refuse. Never defaults anything."""
    given = [a.save_labeled, a.label, a.speaker, a.consent_note]
    if not any(x is not None for x in given):
        return None
    missing = [n for n, x in zip(("--save-labeled", "--label", "--speaker", "--consent-note"), given)
               if x is None or not str(x).strip()]
    if missing:
        return "labelled capture needs all of --save-labeled, --label, --speaker and --consent-note (missing: " + ", ".join(missing) + ")"
    if is_network_path(Path(a.save_labeled).expanduser(), mount_text):
        return "refusing: the save directory is on a network mount (or could not be checked). Use a local disk."
    return None


class LabeledSaver:
    """Writes the PCM that was analysed to DIR/<label>/<timestamp>.wav (0600) and a JSON sidecar. Nothing else."""

    def __init__(self, a: argparse.Namespace, source: str, now: datetime.datetime | None = None) -> None:
        self.a, self.source = a, source
        self.t0 = now or datetime.datetime.now().astimezone()
        d = Path(a.save_labeled).expanduser().resolve() / a.label
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        stem = self.t0.strftime("%Y%m%dT%H%M%S")
        self.wav_path = d / f"{stem}.wav"
        self.json_path = d / f"{stem}.json"
        fd = os.open(self.wav_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self._fh = os.fdopen(fd, "wb")
        self._w = wave.open(self._fh, "wb")
        self._w.setnchannels(1)
        self._w.setsampwidth(2)
        self._w.setframerate(16000)
        self.ticks: list[dict] = []
        self.bytes = 0

    def write(self, frame: bytes) -> None:
        self._w.writeframes(frame)
        self.bytes += len(frame)

    def tick(self, m: dict) -> None:
        row = {k: m.get(k) for k in ("t", "window", "tier", "p_ai", "p_scam") if k in m}
        if m.get("voice_windows") is not None:
            row["voice_windows"] = m["voice_windows"]
        self.ticks.append(row)

    def close(self) -> None:
        try:
            self._w.close()
        finally:
            self._fh.close()
        side = {"label": self.a.label, "speaker": self.a.speaker, "consent_note": self.a.consent_note,
                "date": self.t0.isoformat(timespec="seconds"), "source": self.source, "sample_rate": 16000,
                "seconds": round(self.bytes / 32000, 1), "wav": self.wav_path.name, "ticks": self.ticks}
        fd = os.open(self.json_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(side, f, indent=1)
        os.chmod(self.wav_path, 0o600)
        os.chmod(self.json_path, 0o600)


# ---------------------------------------------------------------------------------------------- audio sources
def load_pcm16(path: str) -> bytes:
    sys.path.insert(0, str(ROOT / "services" / "api"))
    import numpy as np
    from tell import audio
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

    info = await asyncio.get_running_loop().run_in_executor(None, create_session, args.url, args.origin,
                                                            getattr(args, "api_token", None))
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
        saver = LabeledSaver(args, label) if args.save_labeled else None
        saving = saver is not None
        banner(True, label, saving)
        loop = asyncio.get_running_loop()
        t_start = loop.time()
        sent_at: list[float] = []                       # wall time at which each whole second of audio was sent
        state = {"alert": "none", "sent": 0, "stable": None, "spoken": None}

        async def reader() -> None:
            async for raw in ws:
                m = json.loads(raw)
                if m.get("type") == "verdict":
                    end = m.get("window", [0, 0])[1]
                    idx = int(end) - 1
                    lat = loop.time() - sent_at[idx] if 0 <= idx < len(sent_at) else None
                    line = status_line(m, lat, saving)
                    say(line.replace("LISTENING", "LAST WORDS", 1) if m.get("tail") else line)
                    state["stable"] = m.get("stable")
                    if saver:
                        saver.tick(m)
                    new = (m.get("stable") or {}).get("alert", "none")
                    text = notification_for(state["alert"], new)
                    state["alert"] = new
                    if text and not args.no_notify:
                        notify(text, args.sound)
                    if args.speak:
                        stable_tier = (m.get("stable") or {}).get("tier")
                        if stable_tier and stable_tier != state.get("spoken") and play_verdict(stable_tier):
                            state["spoken"] = stable_tier
                elif m.get("type") in ("warn", "error"):
                    say(f"LISTENING | {m.get('type')}: {m.get('code')}")
                    if m.get("type") == "error":
                        return
                elif m.get("type") == "final":
                    say(final_line(m, state["stable"]))
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
                if saver:
                    saver.write(frame)
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
                    # stop is a graceful end: the API lets the in-flight tick land, scores the unscored tail once
                    # (bounded by its final_flush_s, 6 s by default) and only then sends `final`. Wait for it.
                    say("finishing: scoring the last seconds ...")
                    await ws.send(json.dumps({"type": "stop"}))
                    await asyncio.wait_for(rd, STOP_WAIT_S)
                except Exception:  # noqa: BLE001 — closing anyway; the server wipes on disconnect
                    rd.cancel()
                    say("FINAL | no final answer from the API in time (it wipes the session anyway)")
            banner(False)
            if saver:
                saver.close()
                say(f"saved {saver.wav_path} (+ .json sidecar, 0600)")
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
    except urllib.error.HTTPError as e:
        if e.code == 401:
            say(f"the engine refused the API token (401). It reads {api_token_path()}; restart the engine or unset a "
                "stale TELL_API_TOKEN.")
        else:
            say(f"the API at {args.url} answered {e.code}")
        return 1
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
            await asyncio.wait_for(task, STOP_WAIT_S + 4)
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
    err = save_error(args)
    if err:
        print(err, file=sys.stderr)
        return 2
    try:
        args.api_token = load_api_token()
    except TokenMissing as e:
        print(str(e), file=sys.stderr)
        return 2
    if not consent(args):
        return 1
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
