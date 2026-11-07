#!/usr/bin/env python3
"""Record the *human* side of the red-team set (T-012), and speaker->mic replays of any clip.

    python3 tools/redteam/capture.py devices                          # list mics (macOS avfoundation)
    python3 tools/redteam/capture.py human --speaker sanath [--free]   # read each script into the mic
    python3 tools/redteam/capture.py import memo.m4a --script scam_irs --speaker sanath
    python3 tools/redteam/capture.py replay [--match 'ai__gradium__*']  # play clips out loud, re-record

Writes the wild-eval naming (services/api/skills.md) into data/calls/ (gitignored):
    human__<speaker>__<script>.wav + .txt      human reading the same script as ai__<engine>__<script>.wav
    human__<speaker>__free_<topic>.wav         unscripted, no .txt
    <stem>.replayed.wav + .txt                 what the live demo hears (phone speaker -> laptop mic)
Then `tools/redteam/degrade.sh data/calls` for opus-8k and `run_eval.py --wild data/calls` for the table.

Needs ffmpeg. No network, no credits. Only record people who agreed to it, only their own voice.
"""
from __future__ import annotations

import argparse
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CALLS = ROOT / "data" / "calls"
SCRIPTS = HERE / "scripts"
SAMPLE_RATE = 16_000
MIN_SECONDS = 6.0  # acoustics need >= 4 s, breath tells >= 5 s

# Read speech is more regular than real conversation; these keep the human FPR honest.
FREE_PROMPTS = {
    "free_weekend": "Tell us what you did last weekend. Don't plan it, just talk for ~20 seconds.",
    "free_voicemail": "Leave a voicemail for a friend asking them to call you back about dinner.",
    "free_directions": "Explain how to get from your home to the nearest grocery store.",
}


def need(tool: str) -> str:
    """Path of a required binary, or exit with an install hint."""
    exe = shutil.which(tool)
    if not exe:
        sys.exit(f"`{tool}` not found on PATH (macOS: brew install ffmpeg)")
    return exe


def slug(s: str) -> str:
    """Filename-safe token without '__' (the field separator)."""
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "anon"


def mic_args(device: str | None) -> list[str]:
    """ffmpeg input args for the default (or given) microphone."""
    system = platform.system()
    if system == "Darwin":
        return ["-f", "avfoundation", "-i", device or ":0"]
    if system == "Linux":
        return ["-f", "pulse", "-i", device or "default"]
    sys.exit("recording is wired for macOS/Linux; elsewhere record a file and use `import`")


def start_recording(dst: Path, device: str | None) -> subprocess.Popen[bytes]:
    """Start ffmpeg writing 16 kHz mono PCM WAV from the mic."""
    cmd = [need("ffmpeg"), "-loglevel", "error", "-y", *mic_args(device),
           "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(dst)]
    return subprocess.Popen(cmd, stdin=subprocess.DEVNULL)


def stop_recording(p: subprocess.Popen[bytes]) -> None:
    """SIGINT lets ffmpeg finalize the WAV header."""
    p.send_signal(signal.SIGINT)
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()


def play(path: Path) -> None:
    """Play a clip through the speakers, blocking until done."""
    if shutil.which("afplay"):
        subprocess.run(["afplay", str(path)], check=False)
    else:
        subprocess.run([need("ffplay"), "-nodisp", "-autoexit", "-loglevel", "error", str(path)], check=False)


def write_script_txt(stem: str, script: str) -> None:
    """Same words as the AI clip, so script tells cancel in the wild eval."""
    src = SCRIPTS / f"{script}.txt"
    if src.exists():
        (CALLS / f"{stem}.txt").write_text(src.read_text().strip() + "\n")


def take(dst: Path, text: str, device: str | None) -> bool:
    """Interactive record/review loop for one prompt. True if a take was kept."""
    print(f"\n━━━ {dst.stem}\n{text}\n")
    while True:
        if input("Enter = start · s = skip › ").strip().lower() == "s":
            return False
        p = start_recording(dst, device)
        t0 = time.monotonic()
        input("● recording… Enter = stop › ")
        stop_recording(p)
        dur = time.monotonic() - t0
        warn = f"  ⚠ only {dur:.1f}s, aim for ≥ {MIN_SECONDS:.0f}s" if dur < MIN_SECONDS else ""
        choice = input(f"{dur:.1f}s{warn}\nEnter = keep · p = play back · r = redo › ").strip().lower()
        if choice == "p":
            play(dst)
            choice = input("Enter = keep · r = redo › ").strip().lower()
        if choice != "r":
            return True


def cmd_devices(_: argparse.Namespace) -> None:
    """List capture devices (macOS); pass the audio index as --device ':N'."""
    subprocess.run([need("ffmpeg"), "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""])


def cmd_human(a: argparse.Namespace) -> None:
    """Walk one speaker through every script, then optional unscripted prompts."""
    CALLS.mkdir(parents=True, exist_ok=True)
    scripts = sorted(SCRIPTS.glob("*.txt"))
    if a.only:
        scripts = [s for s in scripts if s.stem in a.only]
    prompts = [(s.stem, s.read_text().strip()) for s in scripts]
    if a.free:
        prompts += list(FREE_PROMPTS.items())
    speaker = slug(a.speaker)
    print(f"{len(prompts)} prompts for {speaker}. Read like you're on the phone: normal pace, don't perform, "
          "stumbles are fine. Mic ~30 cm away, quiet room, same setup every take.")
    for script, text in prompts:
        stem = f"human__{speaker}__{script}"
        if take(CALLS / f"{stem}.wav", text, a.device):
            write_script_txt(stem, script)
    print("\nnext: tools/redteam/degrade.sh data/calls && (cd services/api && python3 eval/run_eval.py --wild ../../data/calls)")


def cmd_import(a: argparse.Namespace) -> None:
    """Bring in a clip recorded elsewhere (phone voice memo) as human__<speaker>__<script>.wav."""
    CALLS.mkdir(parents=True, exist_ok=True)
    stem = f"human__{slug(a.speaker)}__{a.script}"
    subprocess.run([need("ffmpeg"), "-loglevel", "error", "-y", "-i", a.file, "-ac", "1",
                    "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(CALLS / f"{stem}.wav")], check=True)
    write_script_txt(stem, a.script)
    print(f"imported → data/calls/{stem}.wav")


def cmd_replay(a: argparse.Namespace) -> None:
    """Play each clean clip from the speakers and re-record it via the mic as <stem>.replayed.wav."""
    clips = [w for w in sorted(CALLS.glob(a.match)) if w.suffix == ".wav" and "." not in w.stem]
    print(f"replaying {len(clips)} clip(s). Speaker ~60% volume, room quiet, nobody talks.")
    input("Enter = go › ")
    for src in clips:
        dst = CALLS / f"{src.stem}.replayed.wav"
        p = start_recording(dst, a.device)
        time.sleep(0.4)
        play(src)
        time.sleep(0.6)
        stop_recording(p)
        txt = src.with_suffix(".txt")
        if txt.exists():
            shutil.copyfile(txt, CALLS / f"{src.stem}.replayed.txt")
        print(f"  {dst.name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("devices").set_defaults(fn=cmd_devices)

    h = sub.add_parser("human")
    h.add_argument("--speaker", required=True, help="first name; goes in the file name")
    h.add_argument("--only", nargs="*", help="script names without .txt")
    h.add_argument("--free", action="store_true", help="also record unscripted prompts")
    h.add_argument("--device", help="macOS ':N' from `devices`; Linux pulse source")
    h.set_defaults(fn=cmd_human)

    i = sub.add_parser("import")
    i.add_argument("file")
    i.add_argument("--script", required=True, help="script name (or free_<topic>)")
    i.add_argument("--speaker", required=True)
    i.set_defaults(fn=cmd_import)

    r = sub.add_parser("replay")
    r.add_argument("--match", default="*.wav", help="glob in data/calls, e.g. 'ai__gradium__*'")
    r.add_argument("--device")
    r.set_defaults(fn=cmd_replay)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
