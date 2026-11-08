#!/usr/bin/env python3
"""Tables from out-of-fold learned scores + the engine's own components (docs/LEARNED-TELLS.md). Run with -I.

  python -I training/learned_tells/report.py <oof.json> <family> [W_LEARNED] [scripts_oof.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import data as D  # noqa: E402
from evaluate import GENS, _auc, auc_ci  # noqa: E402

P_AI = 0.60
POS_GATE = 0.5


def tpr_at_matched_fa(s_h, s_f, fa_allowed):
    """Threshold = the lowest cut at which at most `fa_allowed` held-out humans are flagged; TPR at that cut."""
    s_h = np.sort(s_h[np.isfinite(s_h)])[::-1]
    t = s_h[fa_allowed] if fa_allowed < len(s_h) else -np.inf
    return float(np.mean(s_f > t)), int(np.sum(s_h > t)), float(t)


def domain(r):
    if r["label"] == 1:
        return r["generator"]
    return {"librispeech": "libri", "sanath": "sanath", "sanath raw m4a": "sanath", "phone memo": "friends"}[r["note"]]


def engines(cond, learned_p=None, W=0.0):
    d = D.load(cond)
    out = {"current": d.fused(), "fixed": d.fused(breath_w=0.0, pella="all")}
    if learned_p is not None:
        out["fixed+learned"] = d.fused(breath_w=0.0, pella="all", extra=learned_p, extra_w=W)
        pos = np.where(learned_p >= POS_GATE, learned_p, np.nan)          # positive-only: votes only when it leans AI
        out["fixed+learned(pos-only)"] = d.fused(breath_w=0.0, pella="all", extra=pos, extra_w=W)
        out["learned alone"] = learned_p
    out["pella_all alone"] = d.pella_all()
    return out


def cell(scores, lab, mask_h, mask_f, fa_cur):
    sh, sf = scores[mask_h], scores[mask_f]
    ok_h, ok_f = np.isfinite(sh), np.isfinite(sf)
    sh, sf = sh[ok_h], sf[ok_f]
    a, lo, hi = auc_ci(np.concatenate([sh, sf]), np.r_[np.zeros(len(sh)), np.ones(len(sf))], n_boot=500)
    tpr, fa, _ = tpr_at_matched_fa(sh, sf, fa_cur)
    return {"auc": a, "lo": lo, "hi": hi, "tpr_matched": tpr, "fa_matched": fa, "n_h": len(sh), "n_f": len(sf),
            "fa06": int(np.sum(sh >= P_AI)), "tpr06": float(np.mean(sf >= P_AI))}


def main():
    oof = json.load(open(sys.argv[1]))
    fam = sys.argv[2]
    W = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0
    rows = D.sources()
    lab = np.array([r["label"] for r in rows])
    gen = np.array([r["generator"] for r in rows])
    role = np.array([r["role"] for r in rows])
    dom = np.array([domain(r) for r in rows])
    hum = (lab == 0) & (role == "train")
    lines = [f"family={fam}  W_LEARNED={W}", "",
             "| scenario | condition | engine | n human / n AI | AUC [95% CI] | TPR at matched FA (FA) | FA at 0.60 | TPR at 0.60 |",
             "|---|---|---|---|---|---|---|---|"]
    summary = {}
    for sc in ["seen"] + [f"no_{g}" for g in GENS]:
        for cond in C.EVAL_CONDS:
            key = f"{fam}|{sc}|{cond}"
            if key not in oof:
                continue
            lp = D.sigmoid(np.array(oof[key], dtype=float))
            eng = engines(cond, lp, W)
            fakes = (lab == 1) & (role == "train") & ((gen == sc[3:]) if sc != "seen" else True)
            fa_cur = int(np.sum(eng["current"][hum] >= P_AI))
            for name, s in eng.items():
                c = cell(s, lab, hum, fakes, fa_cur)
                summary[(sc, cond, name)] = c
                lines.append(f"| {sc} | {cond} | {name} | {c['n_h']} / {c['n_f']} | {c['auc']:.3f} [{c['lo']:.2f}, {c['hi']:.2f}] | "
                             f"{c['tpr_matched']:.2f} ({c['fa_matched']}) | {c['fa06']} | {c['tpr06']:.2f} |")
    # humans by domain, seen scenario, at 0.60
    lines += ["", "Human false alarms at p_ai >= 0.60 by speaker domain (each clip scored by a model that never saw its speaker group):", "",
              "| condition | engine | " + " | ".join(f"{d} (n)" for d in ("libri", "sanath", "friends")) + " | max p_ai friends |", "|---|---|---|---|---|---|"]
    for cond in C.EVAL_CONDS:
        key = f"{fam}|seen|{cond}"
        if key not in oof:
            continue
        eng = engines(cond, D.sigmoid(np.array(oof[key], dtype=float)), W)
        for name in ("current", "fixed", "fixed+learned", "fixed+learned(pos-only)"):
            s = eng[name]
            cells = [f"{int(np.sum(s[hum & (dom == d)] >= P_AI))}/{int(np.sum(hum & (dom == d)))}" for d in ("libri", "sanath", "friends")]
            lines.append(f"| {cond} | {name} | " + " | ".join(cells) + f" | {np.nanmax(s[hum & (dom == 'friends')]):.2f} |")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
