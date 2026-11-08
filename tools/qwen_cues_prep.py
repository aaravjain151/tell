#!/usr/bin/env python3
"""Prep for the Qwen-vs-real cue study (docs/QWEN-CUES.md). READ-ONLY on data/calls and the owner files.

    python3 tools/qwen_cues_prep.py OUT_DIR [--calls /path/to/data/calls]

Loads every real (human/sanath) and Qwen3-TTS clip at 16 kHz mono, applies the degrade.py conditions (clean, opus8k,
g711_mulaw8k, chain_replay_call), word-times the CLEAN audio with the local faster-whisper model, and writes
OUT_DIR/audio/<cls>__<name>__<cond>.npy plus OUT_DIR/asr.json. The two owner files (Downloads/data_calls_qwen3tts_*.wav) are
included as cls=qwen name=owner_<script>. Nothing leaves the machine.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "redteam"))
import degrade  # noqa: E402

CONDS = {"clean": None, "opus8k": degrade.c_opus8k, "g711_mulaw8k": degrade.c_mulaw, "chain_replay_call": degrade.c_chain_replay}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--calls", default="data/calls")
    a = ap.parse_args()
    out = Path(a.out)
    (out / "audio").mkdir(parents=True, exist_ok=True)
    calls = Path(a.calls)
    items = []
    for p in sorted((calls / "human" / "sanath").glob("*.wav")):
        if p.stem.count(".") == 0:
            items.append(("human", p.stem, p))
    for p in sorted((calls / "qwen3tts").glob("*.wav")):
        if p.stem.count(".") == 0:
            items.append(("qwen", p.stem, p))
    for p in sorted(Path.home().joinpath("Downloads").glob("data_calls_qwen3tts_*.wav")):
        items.append(("qwen", "owner_" + p.stem.replace("data_calls_qwen3tts_", ""), p))
    from faster_whisper import WhisperModel
    wm = WhisperModel("small", device="cpu", compute_type="int8")
    asr = {}
    for cls, name, p in items:
        x = degrade.read_wav(p)
        for c, fn in CONDS.items():
            f = out / "audio" / f"{cls}__{name}__{c}.npy"
            if not f.exists():
                np.save(f, (x if fn is None else fn(x)).astype(np.float32))
        segs, _ = wm.transcribe(x, language="en", word_timestamps=True, beam_size=1, condition_on_previous_text=False)
        asr[f"{cls}__{name}"] = [[w.word.strip(), round(w.start, 3), round(w.end, 3)] for s in segs for w in s.words]
        print(cls, name, len(x) / 16000, len(asr[f"{cls}__{name}"]), flush=True)
    (out / "asr.json").write_text(json.dumps(asr))
    return 0


if __name__ == "__main__":
    sys.exit(main())
