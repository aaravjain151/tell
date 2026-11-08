#!/usr/bin/env python3
"""Demo preflight for Tell (HACK1984, Sunday 11:00). Stdlib only, read-only, loopback only.

    python3 scripts/demo_preflight.py                       # from the repo root
    python3 scripts/demo_preflight.py --repo ~/Downloads/tell --video ~/Desktop/tell-demo.mov
    python3 scripts/demo_preflight.py --no-session          # skip the listener dry run

Prints a green/amber/red checklist with the fix for each problem. Exit code 1 if anything is red.

What it touches: GET /health, GET /ready, GET the page, POST /session + DELETE /session/<id> (a dry run of what
tools/macos/listen.py does first; no audio is sent), GET on the voice-talk page and Ollama's /api/tags, and local
read-only commands (system_profiler, osascript 'get volume settings', networksetup -getairportpower, adb devices,
lsof, pgrep, df). It never opens .env, never changes a setting and never talks to a non-loopback host.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # a loopback call must never use a proxy

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
results: list[tuple[str, str, str, str]] = []      # (status, name, detail, fix)


def add(status: str, name: str, detail: str, fix: str = "") -> None:
    results.append((status, name, detail, fix))


def loopback(url: str) -> str:
    host = urlparse(url).hostname or ""
    if host not in LOOPBACK:
        raise SystemExit(f"refusing non-loopback URL: {url}")
    return url.rstrip("/")


def http(method: str, url: str, headers: dict | None = None, data: bytes | None = None, timeout: float = 5.0):
    req = urllib.request.Request(loopback(url), method=method, data=data, headers=headers or {})
    with OPENER.open(req, timeout=timeout) as r:
        return r.status, r.read()


def get_json(url: str, timeout: float = 5.0) -> dict:
    _, body = http("GET", url, timeout=timeout)
    return json.loads(body)


def run(cmd: list[str], timeout: float = 15.0) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


# --------------------------------------------------------------------------------------------------- checks
def check_engine(api: str) -> None:
    try:
        h = get_json(api + "/health")
    except Exception as e:  # noqa: BLE001 - any failure is a red line
        add(FAIL, "Engine /health", f"no answer from {api} ({type(e).__name__})",
            "make demo   (or make api), wait for 'API http://localhost:8000/health', run this again")
        return
    e, n = h.get("egress", {}), h.get("os_network", {})
    nums = (e.get("caller_audio_bytes_sent"), e.get("bytes_sent_external"), n.get("os_check"), n.get("os_outbound_count"))
    if h.get("ok") and nums == (0, 0, "ok", 0):
        add(PASS, "Engine /health", "ok · caller audio sent 0 · external bytes 0 · os_check ok · os outbound 0")
    else:
        add(FAIL, "Engine /health", f"ok={h.get('ok')} caller_audio={nums[0]} external={nums[1]} os_check={nums[2]} "
            f"os_outbound={nums[3]} seen={n.get('os_outbound_seen')}",
            "Do not claim 0 bytes. Restart the engine (Ctrl-C make demo; make demo) and check what os_outbound_seen lists")
    if h.get("offline_models") is True:
        add(PASS, "Offline model mode", "offline_models true (make demo)")
    else:
        add(WARN, "Offline model mode", "offline_models false: the engine was started with make api, not make demo",
            "Ctrl-C the engine, start `make demo` (forces offline model loads). Not fatal: loads are cache-only anyway")


def check_ready(api: str) -> None:
    try:
        r = get_json(api + "/ready", timeout=10)
    except Exception as e:  # noqa: BLE001
        add(FAIL, "Engine /ready", f"no answer ({type(e).__name__})", "Start the engine first (make demo)")
        return
    comps = r.get("components", {})
    p, llm, stt = comps.get("pellav2", {}), comps.get("llm", {}), comps.get("stt", {})
    if p.get("status") == "ready":
        add(PASS, "Pellav2 voice check", p.get("detail", ""))
    else:
        add(FAIL, "Pellav2 voice check", f"{p.get('status')}: {p.get('detail')}",
            "If 'cached but not loaded yet': replay one clip (python3 tools/macos/listen.py --file "
            "data/calls/qwen3tts/casual_clone.wav --i-understand), then rerun. If 'off'/'not cached': make models "
            "(online, once). Never go on stage saying Pellav2 is on when it is not")
    if llm.get("status") == "ready":
        add(PASS, "Local LLM (Ollama)", llm.get("detail", ""))
    else:
        add(FAIL, "Local LLM (Ollama)", f"{llm.get('status')}: {llm.get('detail')}",
            "ollama serve &   then  ollama run llama3.2:3b 'hi'  to load it; rerun")
    if stt.get("status") == "ready":
        add(PASS, "Speech to text (Whisper)", stt.get("detail", ""))
    else:
        add(FAIL, "Speech to text (Whisper)", f"{stt.get('status')}: {stt.get('detail')}",
            "make models (online, once); restart make demo")
    degraded = r.get("degraded") or []
    if r.get("ready") and not degraded:
        add(PASS, "Engine ready, nothing degraded", f"thresholds {r.get('thresholds_version')}")
    else:
        add(FAIL, "Engine ready, nothing degraded", f"ready={r.get('ready')} degraded={degraded}",
            "Read the components above; fix the one listed; restart make demo")
    pp = r.get("privacy_posture", {})
    on = [k for k, v in pp.items() if v]
    if not on:
        add(PASS, "Privacy switches", "debug_save off, no cloud LLM, no Gradium key")
    elif on == ["gradium_key_set"]:
        add(WARN, "Privacy switches", "gradium_key_set true: the menu bar privacy row may say a setting could send data",
            "For the stage run start the engine without GRADIUM_API_KEY in the environment, or be ready to say: "
            "'the Gradium key is only for the optional spoken verdict, which we do not click'")
    else:
        add(FAIL, "Privacy switches", f"on: {on}",
            "Turn off TELL_DEBUG_SAVE and LLM_PROVIDER=anthropic for the demo; restart the engine")


def check_ports() -> None:
    out = run(["lsof", "-nP", "-iTCP:8000", "-sTCP:LISTEN"])
    pids = sorted({ln.split()[1] for ln in out.splitlines()[1:] if ln.strip()})
    cmds = []
    for pid in pids:
        cmds.append(run(["ps", "-o", "command=", "-p", pid]).strip()[:110])
    if len(pids) <= 1:
        add(PASS, "One engine on :8000", cmds[0] if cmds else "nothing listening (see /health)")
    else:
        add(WARN, "One engine on :8000", f"{len(pids)} processes listen on :8000: " + " || ".join(cmds),
            "Old engines (doublespeak.main:app) are still running. Quit them all (kill <pid>) and start one `make demo`")


def check_page(web: str) -> None:
    try:
        _, body = http("GET", web + "/")
    except Exception as e:  # noqa: BLE001
        add(FAIL, "Page :5173", f"no answer from {web} ({type(e).__name__})",
            "make demo serves it; or `make web`. Then open Chrome at http://127.0.0.1:5173")
        return
    m = re.search(rb"<title>([^<]*)</title>", body, re.I)
    title = m.group(1).decode("utf-8", "replace").strip() if m else ""
    if title == "Tell":
        add(PASS, "Page :5173", "title 'Tell'")
    else:
        add(FAIL, "Page :5173", f"title is {title!r}, not 'Tell'",
            "Something else owns :5173 (old build or another server). Stop it; `make web` from this repo")


def api_token() -> str:
    """The per-install engine token (same lookup as tell.api_token): env, env file path, then the default file."""
    if os.environ.get("TELL_API_TOKEN"):
        return os.environ["TELL_API_TOKEN"].strip()
    f = Path(os.environ.get("TELL_API_TOKEN_FILE") or Path.home() / "Library/Application Support/Tell/api_token")
    try:
        return f.read_text().strip()
    except OSError:
        return ""


def check_session(api: str, origin: str) -> None:
    tok = {"X-Tell-Token": api_token()} if api_token() else {}
    try:
        _, body = http("POST", api + "/session", data=b"{}",
                       headers={"Origin": origin, "Content-Type": "application/json", **tok})
        sid = json.loads(body)["session_id"]
    except urllib.error.HTTPError as e:
        hint = {401: "no engine token sent: the token file is missing or from another install (make pair-url makes one)",
                403: "the engine refused the Origin: start it with make demo (default origins include :5173)",
                429: "two live sessions are already open: a listener is running (menu bar app or listen.py). "
                     "Stop the extra one, wait about a minute, rerun"}.get(e.code, "read the engine log")
        add(FAIL, "Listener dry run", f"POST /session -> HTTP {e.code}", hint)
        return
    except Exception as e:  # noqa: BLE001
        add(FAIL, "Listener dry run", f"POST /session failed ({type(e).__name__})", "Start the engine (make demo)")
        return
    try:
        http("DELETE", api + f"/session/{sid}", headers=tok)
        add(PASS, "Listener dry run", "POST /session ok, session deleted again (no audio sent)")
    except Exception as e:  # noqa: BLE001
        add(WARN, "Listener dry run", f"session created but DELETE failed ({type(e).__name__}); it times out in ~60 s",
            "Wait a minute before starting the real listener")


def check_listeners(repo: Path) -> None:
    tap = repo / "tools/macos/tap_audio/.build/release/tap_audio"
    if os.access(tap, os.X_OK):
        add(PASS, "Audio tap built", str(tap.relative_to(repo)))
    else:
        add(FAIL, "Audio tap built", "tap_audio binary missing",
            "cd tools/macos/tap_audio && swift build -c release && cd -")
    procs = [ln for ln in run(["pgrep", "-fl", "tools/macos/listen.py"]).splitlines() if ln.strip()]
    bar = run(["pgrep", "-x", "Tell"]).strip()
    if bar:
        add(WARN, "Menu bar app", "Tell.app is running and starts its own --watch listener",
            "Quit Tell.app from its menu before the stage run (the script uses terminal listeners), or rehearse with it")
    if len(procs) <= 1:
        add(PASS, "Listener processes", f"{len(procs)} listen.py running" + (f": {procs[0][:90]}" if procs else ""))
    else:
        add(WARN, "Listener processes", f"{len(procs)} listen.py processes: " + " || ".join(p[:70] for p in procs),
            "Ctrl-C all but the one you need (each holds an engine session; max 2)")


def check_attacker(vt: str, ollama: str, vt_repo: Path) -> None:
    try:
        _, body = http("GET", vt + "/")
        ok = b"voice-talk" in body[:4000]
        add(PASS if ok else FAIL, "voice-talk attacker app", f"{vt} answers" + ("" if ok else " but is not voice-talk"),
            "" if ok else "cd ~/Downloads/voice-talk && git checkout attacker-demo && .venv/bin/python run.py")
    except Exception as e:  # noqa: BLE001
        add(FAIL, "voice-talk attacker app", f"no answer from {vt} ({type(e).__name__})",
            "cd ~/Downloads/voice-talk && git checkout attacker-demo && .venv/bin/python run.py   (http://127.0.0.1:8765)")
    try:
        tags = get_json(ollama + "/api/tags")
        names = {m.get("name", "") for m in tags.get("models", [])}
        need = {"qwen2.5:3b": "voice-talk chat model", "llama3.2:3b": "Tell scam-talk model"}
        missing = [f"{k} ({v})" for k, v in need.items() if not any(n.startswith(k) for n in names)]
        if missing:
            add(WARN, "Ollama models", "missing: " + ", ".join(missing), "ollama pull <model> (online, before the event)")
        else:
            add(PASS, "Ollama models", "qwen2.5:3b and llama3.2:3b present")
    except Exception as e:  # noqa: BLE001
        add(FAIL, "Ollama", f"no answer from {ollama} ({type(e).__name__})", "ollama serve &")
    for voice in ("sanath", "demo-say"):
        c = vt_repo / "voices" / voice / "consent.json"
        if c.exists():
            add(PASS, f"Attacker voice '{voice}'", "consent record present")
        else:
            add(WARN, f"Attacker voice '{voice}'", "no consent record: the voice-talk list will not show it",
                "Use the other voice, or import it with its consent record in voice-talk")


def check_audio() -> None:
    try:
        d = json.loads(run(["system_profiler", "SPAudioDataType", "-json"], timeout=30) or "{}")
        out = [i.get("_name", "?") for x in d.get("SPAudioDataType", []) for i in x.get("_items", [])
               if i.get("coreaudio_default_audio_output_device") == "spaudio_yes"]
    except json.JSONDecodeError:
        out = []
    dev = out[0] if out else "unknown"
    if "Speakers" in dev or "HDMI" in dev or "Display" in dev:
        add(PASS, "Audio output device", dev)
    else:
        add(WARN if dev == "unknown" else FAIL, "Audio output device", dev,
            "Menu bar > Sound > MacBook Pro Speakers (or the room's HDMI/PA). Disconnect AirPods and Bluetooth headsets")
    vs = run(["osascript", "-e", "get volume settings"])
    m = re.search(r"output volume:(\d+).*output muted:(true|false)", vs)
    if not m:
        add(WARN, "Volume", "could not read volume settings", "Check by ear: afplay /System/Library/Sounds/Glass.aiff")
    else:
        vol, muted = int(m.group(1)), m.group(2) == "true"
        if muted or vol < 50:
            add(FAIL, "Volume", f"output volume {vol}{' (muted)' if muted else ''}",
                "Unmute, set volume to about 75: osascript -e 'set volume output volume 75 without output muted'")
        else:
            add(PASS, "Volume", f"output volume {vol}, not muted")


def check_wifi() -> None:
    ports = run(["networksetup", "-listallhardwareports"])
    m = re.search(r"Hardware Port: (?:Wi-Fi|AirPort)\nDevice: (\w+)", ports)
    if not m:
        add(WARN, "Wi-Fi", "no Wi-Fi interface found", "")
        return
    state = run(["networksetup", "-getairportpower", m.group(1)]).strip()
    on = state.endswith("On")
    add(PASS, "Wi-Fi", f"{state} (needed ON for the Calls-on-Other-Devices call in demo 2; turned OFF on cue for "
        "the privacy proof)" if on else f"{state}: the iPhone call cannot reach the Mac with Wi-Fi off",
        "" if on else "Turn Wi-Fi on before demo 2 (menu bar > Wi-Fi), same network as the iPhone")


def check_phone() -> None:
    if not shutil.which("adb"):
        add(WARN, "Android phone (adb)", "adb not installed (only needed for the Android segment / plan B)",
            "brew install android-platform-tools")
        return
    devs = [ln.split() for ln in run(["adb", "devices"]).splitlines()[1:] if ln.strip()]
    if not devs:
        add(WARN, "Android phone (adb)", "no phone connected (only needed for the Android segment / plan B)",
            "Plug in the cable, accept USB debugging, `adb devices` must say device")
        return
    bad = [d for d in devs if len(d) < 2 or d[1] != "device"]
    if bad:
        add(FAIL, "Android phone (adb)", f"state {bad[0][1] if len(bad[0]) > 1 else '?'}",
            "Unlock the phone and accept 'Allow USB debugging'; re-plug the cable")
        return
    rev = run(["adb", "reverse", "--list"])
    if "tcp:8000" in rev:
        add(PASS, "Android phone (adb)", f"{devs[0][0]} connected, adb reverse tcp:8000 active")
    else:
        add(WARN, "Android phone (adb)", f"{devs[0][0]} connected but no adb reverse for 8000",
            "adb reverse tcp:8000 tcp:8000   (and start the engine with make api-android for the installed app)")


def check_disk(repo: Path) -> None:
    free = shutil.disk_usage(repo).free / 1e9
    if free >= 10:
        add(PASS, "Disk space", f"{free:.0f} GB free")
    elif free >= 3:
        add(WARN, "Disk space", f"{free:.1f} GB free (screen recording of the backup take needs a few GB)",
            "Empty the Trash / delete old build folders (/tmp/tell_dd)")
    else:
        add(FAIL, "Disk space", f"{free:.1f} GB free", "Free space now: models swap and recordings can fail")


def check_fallbacks(repo: Path, vt_repo: Path, video: Path | None) -> None:
    clips = [repo / "data/calls/qwen3tts/casual_clone.wav", repo / "data/calls/qwen3tts/scam_bank_otp.wav",
             repo / "data/calls/human/sanath"]
    missing = [str(c.relative_to(repo)) for c in clips if not c.exists()]
    if missing:
        add(FAIL, "Fallback clips", "missing: " + ", ".join(missing),
            "git checkout origin/data/sanath-voice-clips -- data/calls   (from the repo root)")
    else:
        add(PASS, "Fallback clips", "qwen3tts casual_clone + scam_bank_otp, human/sanath present")
    rec = sorted((vt_repo / "qa_out").glob("demo_escalating_scam_test_*/call.wav"))
    if rec:
        add(PASS, "Recorded attacker call", str(rec[-1]))
    else:
        add(WARN, "Recorded attacker call", "none in voice-talk/qa_out",
            "Do one attacker run with 'Save this test call' ticked (REHEARSAL round 1)")
    if video is None:
        add(WARN, "Backup demo video", "not given (--video PATH)", "Record it at rehearsal (FALLBACKS.md, step V)")
    elif video.exists():
        add(PASS, "Backup demo video", str(video))
    else:
        add(WARN, "Backup demo video", f"{video} not found", "Record it at rehearsal (FALLBACKS.md, step V)")


# --------------------------------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description="Tell demo preflight (read-only, loopback only)")
    ap.add_argument("--repo", type=Path, default=root, help="Tell checkout with data/ and the built tap (default: this one)")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--web", default="http://127.0.0.1:5173")
    ap.add_argument("--origin", default="http://localhost:5173", help="allowed UI origin for the session dry run")
    ap.add_argument("--voice-talk", default="http://127.0.0.1:8765")
    ap.add_argument("--voice-talk-repo", type=Path, default=Path.home() / "Downloads/voice-talk")
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--video", type=Path, default=None, help="path of the recorded backup demo video")
    ap.add_argument("--no-session", action="store_true", help="skip the POST/DELETE /session dry run")
    a = ap.parse_args(argv)
    repo = a.repo.expanduser().resolve()

    check_engine(a.api)
    check_ready(a.api)
    check_ports()
    check_page(a.web)
    if not a.no_session:
        check_session(a.api, a.origin)
    check_listeners(repo)
    check_attacker(a.voice_talk, a.ollama, a.voice_talk_repo.expanduser())
    check_audio()
    check_wifi()
    check_phone()
    check_disk(repo)
    check_fallbacks(repo, a.voice_talk_repo.expanduser(), a.video.expanduser() if a.video else None)

    tty = sys.stdout.isatty()
    col = {PASS: "\033[32m", WARN: "\033[33m", FAIL: "\033[31m"} if tty else {}
    reset = "\033[0m" if tty else ""
    mark = {PASS: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}
    print("Tell demo preflight\n")
    for status, name, detail, fix in results:
        print(f"{col.get(status, '')}{mark[status]}{reset} {name}: {detail}")
        if fix and status != PASS:
            print(f"       fix: {fix}")
    n = {s: sum(1 for r in results if r[0] == s) for s in (PASS, WARN, FAIL)}
    print(f"\n{n[PASS]} ok, {n[WARN]} warnings, {n[FAIL]} red. "
          + ("GO." if n[FAIL] == 0 else "NOT READY: fix every red line, then run again."))
    return 1 if n[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
