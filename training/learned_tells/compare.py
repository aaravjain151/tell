#!/usr/bin/env python3
"""Compact comparison of model families from their out-of-fold files. Run with -I.

  python -I training/learned_tells/compare.py W fam1 fam2 ...
Per scenario x condition: AUC of the learned score alone, and for the fused engine (fixed = breath 0 + Pellav2 all windows):
TPR at p_ai >= 0.60 and human false alarms at 0.60 for fixed, fixed+learned and fixed+learned(pos-only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import data as D  # noqa: E402
from evaluate import GENS, _auc  # noqa: E402
from report import POS_GATE  # noqa: E402


def main():
    W = float(sys.argv[1])
    fams = sys.argv[2:]
    rows = D.sources()
    lab = np.array([r["label"] for r in rows])
    gen = np.array([r["generator"] for r in rows])
    role = np.array([r["role"] for r in rows])
    hum = (lab == 0) & (role == "train")
    print(f"W={W}  cells: AUC learned | fixed TPR/FA | +learned TPR/FA | +pos-only TPR/FA  (TPR, FA at p_ai >= 0.60)")
    for fam in fams:
        oof = json.load(open(C.LT / f"oof_L12_{fam}.json"))
        print(f"\n## {fam}")
        for sc in ["seen"] + [f"no_{g}" for g in GENS]:
            cells = []
            for cond in C.EVAL_CONDS:
                lp = D.sigmoid(np.array(oof[f"{fam}|{sc}|{cond}"], dtype=float))
                d = D.load(cond)
                fk = (lab == 1) & (role == "train") & ((gen == sc[3:]) if sc != "seen" else True)
                m = hum | fk
                fx = d.fused(breath_w=0.0, pella="all")
                fl = d.fused(breath_w=0.0, pella="all", extra=lp, extra_w=W)
                fp = d.fused(breath_w=0.0, pella="all", extra=np.where(lp >= POS_GATE, lp, np.nan), extra_w=W)
                t = lambda s: f"{np.mean(s[fk] >= 0.6):.2f}/{int(np.sum(s[hum] >= 0.6))}"
                cells.append(f"{cond[:6]}: {_auc(lp[m], lab[m]):.2f} | {t(fx)} | {t(fl)} | {t(fp)}")
            print(f"  {sc:11s} " + "   ".join(cells))


if __name__ == "__main__":
    main()
