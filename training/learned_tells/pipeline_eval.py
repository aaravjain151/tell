#!/usr/bin/env python3
"""Run the REAL pipeline (tell.pipeline.analyze, voice only: no transcript, STT off, LLM stub) on the pure test sets, per channel
condition, for one engine checkout. Used for the before/after table on files no model ever trained on. Run with -I.

  python -I training/learned_tells/pipeline_eval.py <services/api dir> <out.json> [TELL_LEARNED_TELLS value]

Test sets: the two owner Qwen files, the ElevenLabs lines (each line, and per-voice + all-lines concatenations, built in memory),
the Qwen3-TTS 1.7B takes, the voice-talk QA calls. Conditions: clean, opus8k, g711_mulaw8k, chain_replay_call (degrade.py).
"""
from __future__ import annotations

import io
import json
import os
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def wav_bytes(x: np.ndarray) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return b.getvalue()


def test_items():
    import common as C
    import degrade
    items = []
    for cid, p in C.OWNER.items():
        items.append((cid, "qwen (owner file)", degrade.read_wav(p)))
    el = {p.stem: degrade.read_wav(p) for p in sorted(C.VO.glob("*.EL.wav"))}
    for k, x in el.items():
        items.append((f"el_{k}", "elevenlabs line", x))
    gap = np.zeros(int(0.35 * 16000), np.float32)
    def cat(keys):
        parts = []
        for k in keys:
            parts += [el[k], gap]
        return np.concatenate(parts)
    meera = [k for k in el if "meera" in k]
    caller = [k for k in el if "caller" in k]
    items.append(("el_concat_meera", "elevenlabs concat", cat(meera)))
    items.append(("el_concat_caller", "elevenlabs concat", cat(caller)))
    items.append(("el_concat_all", "elevenlabs concat", cat(list(el))))
    for p in sorted(C.VO.glob("08_arjun.QWEN.take*.wav")) + [C.VO / "08_arjun.CLONE.wav"]:
        items.append((f"vo_{p.stem}", "qwen 1.7B", degrade.read_wav(p)))
    for d in sorted(C.QA.glob("*/call.wav")):
        items.append((f"qa_{d.parent.name}", "qwen qa call", degrade.read_wav(d)))
    return items


def main():
    api, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    if len(sys.argv) > 3:
        os.environ["TELL_LEARNED_TELLS"] = sys.argv[3]
    os.environ.setdefault("PELLA_MODEL", "Sadanie/pellav2-audio-deepfake-detector")
    os.environ.setdefault("HF_SPOOF_MODEL", "garystafford/wav2vec2-deepfake-voice-detector")
    os.environ["LLM_PROVIDER"] = "stub"
    os.environ["TELL_STT"] = "voicestudio"           # no local whisper: voice-only score
    os.environ["VOICESTUDIO_URL"] = "http://127.0.0.1:9"   # nothing listens there: STT fails closed, no transcript
    import common as C  # noqa: F401  (paths; also puts tools/redteam on sys.path)
    import degrade
    sys.path.insert(0, str(api))                      # AFTER common, so THIS checkout's `tell` wins
    from tell import pipeline
    print("engine:", pipeline.__file__, flush=True)
    res = []
    for cid, kind, x in test_items():
        for cond in ("clean", "opus8k", "g711_mulaw8k", "chain_replay_call"):
            y = x if cond == "clean" else degrade.CONDITIONS[cond][0](x)
            v = pipeline.analyze(wav_bytes(y), "")
            t = {tl.name: round(tl.score, 3) for tl in v.tells if tl.applicable}
            res.append({"id": cid, "kind": kind, "cond": cond, "dur": round(len(x) / 16000, 1), "p_ai": round(v.p_ai, 3),
                        "tier": v.tier, "pella": t.get("neural_pella"), "hf": t.get("neural_hf"), "learned": t.get("learned_tells"),
                        "band_limited": v.egress.get("context", {}).get("band_limited")})
            print(res[-1], flush=True)
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
