#!/usr/bin/env python3
"""Effect of the engine fixes on the CURRENT fusion, no learning involved (so no fold is needed): breath weight 0 and
Pellav2 on all windows with a logit mean. Per condition: human false alarms at p_ai >= 0.60 by domain, catch rate by generator.

  python -I training/learned_tells/bugfix.py clean,opus8k,g711_mulaw8k,chain_replay_call
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data as D  # noqa: E402
from report import domain  # noqa: E402


def main(conds):
    rows = D.sources()
    dom = np.array([domain(r) for r in rows])
    role = np.array([r["role"] for r in rows])
    lab = np.array([r["label"] for r in rows])
    tr = role == "train"
    print("| condition | engine | FA libri | FA sanath | FA friends | max human p_ai | catch qwen | catch gradium | catch say | breath score human / AI |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for cond in conds:
        d = D.load(cond)
        b = d.cur[:, d.cur_names.index("breath_proxy")]
        variants = {"current (breath 1.2, Pellav2 3-window mean)": d.fused(),
                    "breath weight 0": d.fused(breath_w=0.0),
                    "Pellav2 all windows, logit mean": d.fused(pella="all"),
                    "both fixes": d.fused(breath_w=0.0, pella="all")}
        for name, s in variants.items():
            fa = [f"{int(np.sum(s[tr & (dom == k)] >= 0.6))}/{int(np.sum(tr & (dom == k)))}" for k in ("libri", "sanath", "friends")]
            ct = [f"{np.mean(s[tr & (dom == g)] >= 0.6):.2f}" for g in ("qwen", "gradium", "say")]
            mh = np.nanmax(s[tr & (lab == 0)])
            print(f"| {cond} | {name} | " + " | ".join(fa) + f" | {mh:.2f} | " + " | ".join(ct) +
                  f" | {np.nanmean(b[tr & (lab == 0)]):.2f} / {np.nanmean(b[tr & (lab == 1)]):.2f} |")


if __name__ == "__main__":
    main(sys.argv[1].split(","))
