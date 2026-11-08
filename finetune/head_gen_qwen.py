#!/usr/bin/env python3
"""Synthesise the Qwen3-TTS clones listed in data/finetune/qwen_jobs.json. LOCAL ONLY, no paid API.

Run with the voice-talk venv (it has qwen_tts):
  /Users/aarav/Downloads/voice-talk/.venv/bin/python finetune/head_gen_qwen.py [--model DIR] [--limit N] [--shard i/n]

Zero-shot cloning from one short reference wav + its exact words (same call as tools/redteam/engines.py qwen3tts and
voice-talk). One clone prompt is built per reference and reused. Resumable: existing outputs are skipped.
Only consented references are ever listed (LibriSpeech CC BY 4.0 speakers, voice-talk demo voices with consent.json).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf

FT = Path(__file__).resolve().parent.parent / "data" / "finetune"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="/Users/aarav/Downloads/voice-talk/models/Qwen3-TTS-12Hz-0.6B-Base")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--device", default="")
    a = ap.parse_args()
    import torch
    from qwen_tts import Qwen3TTSModel
    dev = a.device or ("mps" if torch.backends.mps.is_available() else "cpu")
    model = Qwen3TTSModel.from_pretrained(a.model, dtype=torch.bfloat16 if dev != "cpu" else torch.float32, attn_implementation="sdpa", device_map=dev)
    jobs = json.loads((FT / "qwen_jobs.json").read_text())
    prompts: dict[str, object] = {}
    done = t0 = 0
    t0 = time.time()
    for j in jobs:
        out = Path(j["out"])
        if out.exists():
            continue
        if a.limit and done >= a.limit:
            break
        key = j["ref_wav"]
        if key not in prompts:
            prompts[key] = model.create_voice_clone_prompt(ref_audio=key, ref_text=j["ref_text"])
        max_new = int(min(1800, 24 + 4.2 * len(j["text"])))
        try:
            wavs, sr = model.generate_voice_clone(text=j["text"], language="English", voice_clone_prompt=prompts[key], max_new_tokens=max_new)
        except Exception as e:  # noqa: BLE001
            print("FAIL", j["id"], repr(e)[:100], flush=True)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(out, np.clip(np.asarray(wavs[0], dtype=np.float32), -1, 1), int(sr), subtype="PCM_16")
        done += 1
        if done % 10 == 0:
            print(f"{done} done, {(time.time() - t0) / done:.1f}s/clip", flush=True)
    print("finished", done, "in", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
