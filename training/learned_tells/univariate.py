#!/usr/bin/env python3
"""One feature at a time: clip-level AUC (median of window values) human vs each generator, per condition. Run with -I."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
from evaluate import _auc  # noqa: E402


def main(conds=("clean", "opus8k", "g711_mulaw8k", "chain_replay_call")) -> None:
    rows = C.read_sources()
    lab = np.array([r["label"] for r in rows])
    gen = np.array([r["generator"] for r in rows])
    role = np.array([r["role"] for r in rows])
    for cond in conds:
        f = np.load(C.LT / f"feats_{cond}.npz")
        clip, X, names = f["clip"], f["X"], [str(s) for s in f["names"]]
        M = np.full((len(rows), len(names)), np.nan)
        for i in range(len(rows)):
            w = clip == i
            if w.any():
                with np.errstate(all="ignore"):
                    M[i] = np.nanmedian(X[w], axis=0)
        print(f"\n== {cond}: AUC (>0.5 = higher in AI) human(train) vs ...")
        print(f"{'feature':20s} " + " ".join(f"{g:>8s}" for g in ("qwen", "gradium", "say", "eleven")))
        h = (lab == 0) & (role == "train")
        for j, n in enumerate(names):
            cells = []
            for g in ("qwen", "gradium", "say", "elevenlabs"):
                m = h | ((gen == g) & (lab == 1))
                ok = m & np.isfinite(M[:, j])
                cells.append(_auc(M[ok, j], lab[ok]))
            print(f"{n:20s} " + " ".join(f"{c:8.2f}" for c in cells))


if __name__ == "__main__":
    main()
