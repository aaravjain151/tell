#!/usr/bin/env python3
"""Golden eval. Transcript cases from eval/golden.jsonl (+ synthetic audio pairs).

    python3 eval/run_eval.py            # summary
    python3 eval/run_eval.py --verbose  # every miss with the tells that fired

Target: transcript 4-tier accuracy >= 0.85; synthetic audio human-vs-TTS >= 0.90.
Transcript-only cases have no acoustic evidence, so "ai_undisclosed" relies on script tells alone;
that's the hard part of this eval and the reason the number isn't 1.0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("LLM_PROVIDER", "stub")

from tell import pipeline  # noqa: E402
from tests.synth import make_call, to_wav_bytes  # noqa: E402

TARGET_TRANSCRIPT = 0.85
TARGET_AUDIO = 0.90


def run_transcripts(verbose: bool) -> float:
    cases = [json.loads(l) for l in (HERE / "golden.jsonl").read_text().splitlines() if l.strip()]
    hits, conf = 0, Counter()
    for c in cases:
        v = pipeline.analyze(None, c["transcript"])
        got = v.tier
        # transcript-only: an "unsure" on a human/ai case counts half (we'd rather say unsure than wrong)
        ok = got == c["expected"]
        hits += 1 if ok else (0.5 if got == "unsure" and c["expected"] != "scam" else 0)
        conf[(c["expected"], got)] += 1
        if verbose and not ok:
            fired = [f"{t.name}={t.score:.2f}" for t in v.tells if t.applicable and t.score >= 0.5]
            print(f"MISS {c['id']}: expected {c['expected']}, got {got} (p_ai {v.p_ai:.2f}, p_scam {v.p_scam:.2f}, conf {v.confidence:.2f})\n     {fired}")
    acc = hits / len(cases)
    print(f"transcript eval: {acc:.2f} over {len(cases)} cases (target {TARGET_TRANSCRIPT})")
    for (exp, got), n in sorted(conf.items()):
        if exp != got:
            print(f"   {exp} → {got}: {n}")
    return acc


def run_audio(verbose: bool) -> float:
    n, hits = 0, 0
    for seed in range(12):
        for kind in ("human", "tts"):
            for pb in (False, True):
                v = pipeline.analyze(to_wav_bytes(make_call(kind, seed=seed, phone_band=pb)), None)
                want_ai = kind == "tts"
                ok = (v.p_ai >= 0.6) == want_ai
                n += 1
                hits += ok
                if verbose and not ok:
                    print(f"MISS audio seed={seed} {kind} phone={pb}: p_ai {v.p_ai:.2f}")
    acc = hits / n
    print(f"synthetic audio eval: {acc:.2f} over {n} clips (target {TARGET_AUDIO})")
    return acc


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    t = run_transcripts(a.verbose)
    au = run_audio(a.verbose)
    ok = t >= TARGET_TRANSCRIPT and au >= TARGET_AUDIO
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
