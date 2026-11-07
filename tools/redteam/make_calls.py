#!/usr/bin/env python3
"""Generate attacker calls with Gradium TTS for the live demo and for tuning thresholds.

    python3 tools/redteam/make_calls.py --out data/calls [--voice-id <id>] [--only scam_grandparent] [--max 20]

Uses the Gradium CLI from the gradium-py README (`uvx gradium tts "text" --voice-id <id> -o out.wav`).
Needs GRADIUM_API_KEY in the environment (or .env) and `uv` on PATH. Each script produces
<name>.wav + <name>.txt so the UI can load the pair. Output dir is gitignored.

Demo recipe: clone a teammate in Gradium Studio → pass --voice-id → generate `casual_clone` →
play it to Tell next to the teammate reading the same lines live. Keep --max small; credits are shared.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/calls")
    ap.add_argument("--voice-id", default=os.environ.get("GRADIUM_VOICE_ID", ""))
    ap.add_argument("--only", nargs="*", default=None, help="script names without .txt")
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    load_env()
    if not os.environ.get("GRADIUM_API_KEY") and not a.dry_run:
        print("GRADIUM_API_KEY not set (put it in .env)", file=sys.stderr)
        return 2
    uvx = shutil.which("uvx")
    if not uvx and not a.dry_run:
        print("`uvx` not found — install uv: https://docs.astral.sh/uv/", file=sys.stderr)
        return 2
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    scripts = sorted((HERE / "scripts").glob("*.txt"))
    if a.only:
        scripts = [s for s in scripts if s.stem in a.only]
    made = 0
    for s in scripts[: a.max]:
        text = s.read_text().strip()
        wav = out / f"{s.stem}.wav"
        cmd = [uvx or "uvx", "gradium", "tts", text, "-o", str(wav)]
        if a.voice_id:
            cmd += ["--voice-id", a.voice_id]
        print(("DRY " if a.dry_run else "") + f"{s.stem} → {wav.relative_to(ROOT)}")
        if a.dry_run:
            continue
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            print(f"  failed: {(p.stderr or p.stdout)[:300]}", file=sys.stderr)
            continue
        (out / f"{s.stem}.txt").write_text(text + "\n")
        made += 1
    print(f"made {made} clip(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
