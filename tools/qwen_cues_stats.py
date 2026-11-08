#!/usr/bin/env python3
"""Paired statistics for WORK/features.csv: qwen - real per script, bootstrap 95% CI over scripts (n shown), per condition.

    python3 tools/qwen_cues_stats.py WORK [--out table.md]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PAIRS = ["casual_clone", "long_appointment", "long_checkin", "sales_disclosed", "sales_undisclosed",
         "scam_bank_otp", "scam_grandparent", "scam_irs"]
CONDS = ["clean", "opus8k", "g711_mulaw8k", "chain_replay_call"]
rng = np.random.default_rng(0)


def paired(df: pd.DataFrame, feat: str, cond: str):
    h = df[(df.cls == "human") & (df.cond == cond)].set_index("script")[feat]
    q = df[(df.cls == "qwen") & (df.cond == cond)].set_index("script")[feat]
    idx = [s for s in PAIRS if s in h.index and s in q.index and np.isfinite(h[s]) and np.isfinite(q[s])]
    d = np.array([q[s] - h[s] for s in idx])
    if len(d) < 4:
        return None
    bs = [rng.choice(d, len(d)).mean() for _ in range(5000)]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    dz = d.mean() / d.std(ddof=1) if d.std(ddof=1) > 0 else np.nan
    # bootstrap CI of dz
    bz = []
    for _ in range(3000):
        s = rng.choice(d, len(d))
        bz.append(s.mean() / s.std(ddof=1) if s.std(ddof=1) > 0 else np.nan)
    zlo, zhi = np.nanpercentile(bz, [2.5, 97.5])
    return dict(n=len(d), h=float(np.mean([h[s] for s in idx])), q=float(np.mean([q[s] for s in idx])), d=float(d.mean()),
                lo=float(lo), hi=float(hi), dz=float(dz), zlo=float(zlo), zhi=float(zhi), same_sign=int((np.sign(d) == np.sign(d.mean())).sum()),
                sig=bool(lo > 0 or hi < 0))


def main() -> int:
    work = Path(sys.argv[1])
    df = pd.read_csv(work / "features.csv")
    feats = [c for c in df.columns if c not in ("cls", "script", "cond")]
    lines = ["| feature | cond | n | real | qwen | diff (qwen-real) [95% CI] | dz | scripts same sign |", "|---|---|---|---|---|---|---|---|"]
    summ = {}
    for f in feats:
        for c in CONDS:
            r = paired(df, f, c)
            if r is None:
                continue
            summ[(f, c)] = r
            mark = "*" if r["sig"] else ""
            lines.append(f"| {f} | {c} | {r['n']} | {r['h']:.3g} | {r['q']:.3g} | {r['d']:+.3g} [{r['lo']:+.3g}, {r['hi']:+.3g}]{mark} | {r['dz']:+.2f} | {r['same_sign']}/{r['n']} |")
    (work / "paired_table.md").write_text("\n".join(lines))
    # compact: which features have CI excluding 0 per condition
    rows = []
    for f in feats:
        row = {"feature": f}
        for c in CONDS:
            r = summ.get((f, c))
            row[c] = "" if r is None else f"{r['dz']:+.1f}{'*' if r['sig'] else ''}({r['same_sign']}/{r['n']})"
        row["clean_diff"] = "" if ("%s" % f, "clean") not in summ else f"{summ[(f,'clean')]['h']:.3g}->{summ[(f,'clean')]['q']:.3g}"
        rows.append(row)
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200); pd.set_option("display.max_colwidth", 40)
    print(out.to_string(index=False))
    out.to_csv(work / "paired_compact.csv", index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
