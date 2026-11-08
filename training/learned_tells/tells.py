#!/usr/bin/env python3
"""'What gives an AI voice away': the ranked, standardised weights of the interpretable logistic regression (L2 and L1),
with a per-condition survival check. Run with -I.

Survives(cond) = the feature's own clip-level AUC (all AI vs all humans, train clips) in that condition is on the same side of
0.5 as its weight and at least 0.55 / at most 0.45. Weights come from the model fitted on all training clips and conditions.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import data as D  # noqa: E402
import evaluate as E  # noqa: E402
from meaning import MEANING  # noqa: E402


def clip_medians(cond):
    d = D.load(cond)
    M = np.full((d.n_clips, d.X.shape[1]), np.nan)
    for i, w in enumerate(d.win_of):
        if len(w):
            with np.errstate(all="ignore"):
                M[i] = np.nanmedian(d.X[w], axis=0)
    return M, d.names


def main():
    rows = D.sources()
    lab = np.array([r["label"] for r in rows])
    role = np.array([r["role"] for r in rows])
    m2, _ = E.fit_final("interp_l2")
    m1, _ = E.fit_final("interp_l1")
    names = D.load("clean").names
    feats = [names[j] for j in m2.feat_idx]
    c2, c1 = m2.m.coef_[0], m1.m.coef_[0]
    surv = {}
    for cond in C.EVAL_CONDS:
        M, _ = clip_medians(cond)
        for k, j in enumerate(m2.feat_idx):
            ok = (role == "train") & np.isfinite(M[:, j])
            surv[(cond, feats[k])] = E._auc(M[ok, j], lab[ok])
    print(f"interp L2 C={m2.C}  L1 C={m1.C}")
    print("| rank | tell | direction (toward AI) | weight L2 | weight L1 | AUC clean / opus8k / g711 / replay | survives phone+replay | what it measures |")
    print("|---|---|---|---|---|---|---|---|")
    for rank, k in enumerate(np.argsort(-np.abs(c2)), 1):
        f = feats[k]
        what, hi, lo = MEANING[f]
        sgn = np.sign(c2[k])
        aucs = [surv[(c, f)] for c in C.EVAL_CONDS]
        ok = [(a - 0.5) * sgn >= 0.05 for a in aucs]
        verdict = "yes" if all(ok) else ("phone only" if ok[1] and ok[2] and not ok[3] else ("clean only" if ok[0] and not any(ok[1:]) else "partly" if any(ok) else "no (works only jointly)"))
        print(f"| {rank} | {f} | {hi if sgn > 0 else lo} | {c2[k]:+.2f} | {c1[k]:+.2f} | " + " / ".join(f"{a:.2f}" for a in aucs) + f" | {verdict} | {what} |")


if __name__ == "__main__":
    main()
