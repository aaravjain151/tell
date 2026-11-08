#!/usr/bin/env python3
"""Shadow-layer report: every shadow feature per clip per condition, distribution per class and AI-vs-human AUC.

    python3 tools/shadow_report.py DIR [--conditions clean,opus8k] [--pipeline] [--boot 2000]

DIR holds labelled WAVs: DIR/<engine>/<name>[.<condition>].wav (AI) and DIR/human/**/<name>[.<condition>].wav (human), the
layout of data/calls and of tools/redteam/degrade.py outputs. Class = human if "human" is in the path, else AI.

By default only the signal features run (numpy, no models, nothing leaves the machine). --pipeline runs the full local
pipeline per clip. Persistence features still read n/a per clip (the neural voters score at most 3 windows per analysis, and
persistence needs >= 3 over a CALL); they are only meaningful across live-stream ticks (live.StableTracker accumulates them).

AUC = P(random AI clip's value > random human clip's value), ties half (rank / Mann-Whitney). 0.5 = no separation; below 0.5 means
LOWER values look AI. The 95% interval is a percentile bootstrap that resamples clips within each class (default 2000 draws, fixed seed).

WARNING: ONE human speaker and tiny n. Any separation here may simply be that speaker's microphone and room (speaker identity),
not "human vs AI". Nothing printed here supports a claim of generalisation, and none of it is used by the scorer.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))
sys.path.insert(0, str(ROOT / "tools" / "redteam"))
os.environ.setdefault("LLM_PROVIDER", "stub")
os.environ.setdefault("TELL_STT", "whisper")

from tell import audio as audio_mod  # noqa: E402
from tell.signals import shadow  # noqa: E402

WARNING = ("**WARNING: one human speaker and tiny n. Any separation below may be speaker identity (that person's mic and room), "
           "not human-vs-AI. Sanity check only; no claim of generalisation; none of this is used by the scorer.**")


def condition_of(stem: str, known: list[str]) -> tuple[str, str]:
    for c in known:
        if stem.endswith("." + c):
            return c, stem[: -len(c) - 1]
    return "clean", stem


def auc(ai: np.ndarray, hu: np.ndarray) -> float:
    if ai.size == 0 or hu.size == 0:
        return math.nan
    d = ai[:, None] - hu[None, :]
    return float(((d > 0) + 0.5 * (d == 0)).mean())


def boot_ci(ai: np.ndarray, hu: np.ndarray, n: int, seed: int = 0) -> tuple[float, float]:
    if ai.size < 2 or hu.size < 2:
        return math.nan, math.nan
    rng = np.random.default_rng(seed)
    v = [auc(rng.choice(ai, ai.size), rng.choice(hu, hu.size)) for _ in range(n)]
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


def _fmt(x: float, nd: int = 2) -> str:
    return "n/a" if x is None or not math.isfinite(x) else f"{x:.{nd}f}"


def features_for(path: Path, use_pipeline: bool) -> dict[str, float | None]:
    data = path.read_bytes()
    if use_pipeline:
        from tell import pipeline
        v = pipeline.analyze(data, None)
        sh = (v.egress.get("context") or {}).get("shadow") or {}
    else:
        x, _, _ = audio_mod.decode(data)
        sh = shadow.compute_all(x, None)
    return {k: d["value"] for k, d in sh.items() if k != "error" and not (not use_pipeline and k.startswith("persist_"))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir")
    ap.add_argument("--conditions", help="comma list, e.g. clean,opus8k (default: every condition found)")
    ap.add_argument("--pipeline", action="store_true")
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()

    import degrade
    known = list(degrade.CONDITIONS)
    root = Path(a.dir)
    want = set(a.conditions.split(",")) if a.conditions else None
    rows: dict[str, list[tuple[str, str, dict]]] = {}
    for wav in sorted(root.rglob("*.wav")):
        rel = wav.relative_to(root)
        cond, _ = condition_of(wav.stem, known)
        if want and cond not in want:
            continue
        label = "human" if "human" in rel.parts[:-1] else "ai"
        engine = "human" if label == "human" else (rel.parts[0] if len(rel.parts) > 1 else "other")
        rows.setdefault(cond, []).append((label, engine, features_for(wav, a.pipeline)))
    if not rows:
        print(f"no .wav clips under {root}")
        return 1
    print(WARNING + "\n")
    order = sorted(rows, key=lambda c: (c != "clean", c != "opus8k", c))
    for cond in order:
        recs = rows[cond]
        n_ai, n_hu = sum(r[0] == "ai" for r in recs), sum(r[0] == "human" for r in recs)
        engines = sorted({r[1] for r in recs if r[0] == "ai"})
        print(f"### Condition `{cond}` · AI n={n_ai} ({', '.join(engines)}) · human n={n_hu}\n")
        print("| Feature | AI mean ± std (n) | Human mean ± std (n) | AUC (AI > human) | 95% CI | Reads |")
        print("|---|---|---|---|---|---|")
        names = sorted({k for r in recs for k in r[2]})
        for k in names:
            ai = np.array([r[2][k] for r in recs if r[0] == "ai" and r[2].get(k) is not None], float)
            hu = np.array([r[2][k] for r in recs if r[0] == "human" and r[2].get(k) is not None], float)
            if ai.size == 0 and hu.size == 0:
                continue
            A = auc(ai, hu)
            lo, hi = boot_ci(ai, hu, a.boot)
            reads = ""
            if math.isfinite(lo):
                reads = "interval spans 0.5" if lo <= 0.5 <= hi else ("higher = AI" if A > 0.5 else "lower = AI")
            ms = lambda v: f"{v.mean():.3g} ± {v.std():.2g} ({v.size})" if v.size else "- (0)"
            print(f"| {k} | {ms(ai)} | {ms(hu)} | {_fmt(A)} | [{_fmt(lo)}, {_fmt(hi)}] | {reads} |")
        print()
    print(WARNING)
    return 0


if __name__ == "__main__":
    sys.exit(main())
