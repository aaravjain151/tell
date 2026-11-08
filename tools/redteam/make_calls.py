#!/usr/bin/env python3
"""Generate attacker calls with Gradium, ElevenLabs and/or a local VoiceStudio for the demo and for tuning.

    python3 tools/redteam/make_calls.py --engine gradium|elevenlabs|voicestudio|qwen3tts|all [--voice <id|ref.wav>] [--voice-text '<exact words>'] [--only scam_grandparent] [--max 20]

Output: data/calls/<engine>/<script>.wav + .txt (gitignored). Engines and keys: tools/redteam/engines.py.
qwen3tts clones a consenting teammate from --voice data/ref/<name>.wav + --voice-text (slow on Mac: start it first).
`--engine all` skips engines that aren't usable (no key / app not running) and says why; voice ids then come from
GRADIUM_VOICE_ID / ELEVENLABS_VOICE_ID / VOICESTUDIO_VOICE / QWEN3TTS_REF (+ QWEN3TTS_REF_TEXT). --max caps clips PER ENGINE (credits are shared; paid engines get at most 2x --max).
Every engine only ever receives our script text.

Demo recipe: clone a teammate in Gradium Studio → pass --voice-id → generate `casual_clone` →
play it to Tell next to the teammate reading the same lines live. Keep --max small; credits are shared.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from engines import ENGINES, PAID, VOICE_ENV, load_env, unavailable_reason  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/calls")
    ap.add_argument("--engine", default="gradium", choices=[*ENGINES, "all"])
    ap.add_argument("--voice", "--voice-id", dest="voice", default="", help="voice/profile id (qwen3tts: path to ref .wav) for a single --engine; use the *_VOICE env vars with --engine all")
    ap.add_argument("--voice-text", default=os.environ.get("QWEN3TTS_REF_TEXT", ""), help="qwen3tts: the exact words spoken in the reference clip")
    ap.add_argument("--only", nargs="*", default=None, help="script names without .txt")
    ap.add_argument("--max", type=int, default=6, help="clips per engine (6 = one per script)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    load_env()
    engines = list(ENGINES) if a.engine == "all" else [a.engine]
    usable = []
    for e in engines:
        why = None if a.dry_run else unavailable_reason(e)
        if why:
            print(f"skip {e}: {why}", file=sys.stderr)
        else:
            usable.append(e)
    if not usable:
        return 2
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    scripts = sorted((HERE / "scripts").glob("*.txt"))
    if a.only:
        scripts = [s for s in scripts if s.stem in a.only]
    jobs = [(e, s) for e in usable for s in scripts[: a.max]]   # --max is per engine, so no engine is starved
    chars = sum(len(s.read_text()) for e, s in jobs if e in PAID)
    print(f"{len(jobs)} clip(s) across {usable}; ~{chars} characters to paid engines")
    made = 0
    for e, s in jobs:
        text = s.read_text().strip()
        (out / e).mkdir(parents=True, exist_ok=True)
        wav = out / e / f"{s.stem}.wav"
        voice = a.voice if len(usable) == 1 and a.voice else os.environ.get(VOICE_ENV[e], "")
        print(("DRY " if a.dry_run else "") + f"{e}:{s.stem} → {wav.relative_to(ROOT)}")
        if a.dry_run:
            continue
        try:
            ENGINES[e](text, wav, voice_id=voice, voice_text=a.voice_text)
        except Exception as err:  # noqa: BLE001
            print(f"  failed: {str(err)[:300]}", file=sys.stderr)
            continue
        (out / f"{wav.stem}.txt").write_text(text + "\n")
        made += 1
    print(f"made {made} clip(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
