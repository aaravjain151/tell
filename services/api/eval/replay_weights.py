#!/usr/bin/env python3
"""Replay the scorer's own fusion formula offline over per-clip tells dumped by `run_eval.py --wild DIR --dump FILE`.

    python3 eval/replay_weights.py tells.json                 # grid of (W_PELLA, W_HF, ACOUSTIC_SHARE) + leave-one-engine-out
    python3 eval/replay_weights.py tells.json --setting 6 0.3 0.8

Uses scorer._wmean and the same share formula (no re-implementation), so a replayed p_ai equals the shipped p_ai for the
same weights. Nothing here touches models or audio. n is tiny (one human speaker): this ranks settings, it proves nothing.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tell import thresholds as T  # noqa: E402
from tell.scorer import _wmean  # noqa: E402
from tell.types import Tell  # noqa: E402
from eval.metrics import auc  # noqa: E402


def p_ai(tells: list[dict], w_pella: float, w_hf: float, share: float, force_pella: float | None = None) -> float:
    ts = [Tell(t["name"], t["family"], t["score"] if (force_pella is None or t["name"] != "neural_pella") else force_pella,
               t["weight"], "", t["applicable"]) for t in tells]
    ts = [replace(t, weight=w_pella) if t.name == "neural_pella" else replace(t, weight=w_hf) if t.name == "neural_hf" else t for t in ts]
    a, s = _wmean([t for t in ts if t.family == "acoustic"]), _wmean([t for t in ts if t.family == "script"])
    if a is not None and s is not None:
        return share * a + (1 - share) * s
    return a if a is not None else s if s is not None else 0.5


def score(rows: dict[str, list[dict]], setting: tuple[float, float, float], force_pella: float | None = None) -> dict[str, list]:
    return {cond: [(r["label"], r["engine"], p_ai(r["tells"], *setting, force_pella)) for r in rs] for cond, rs in rows.items()}


def stress(rows: dict, setting: tuple[float, float, float]) -> str:
    """Single-point-of-failure check: humans if Pellav2 shouted 'synthetic' (1.0) on them; AI if Pellav2 said 'human' (0.0)."""
    hi = summarize(score(rows, setting, force_pella=1.0), 0.0)
    lo = summarize(score(rows, setting, force_pella=0.0), 0.0)
    return "  ".join(f"{c}: human max if Pella=1 {hi[c]['max_h']:.2f}, AI median if Pella=0 {sorted(p for l, e, p in score(rows, setting, 0.0)[c] if l == 'ai')[13]:.2f}" for c in sorted(hi))


def summarize(scored: dict[str, list], thr: float, engines: set[str] | None = None) -> dict:
    res = {}
    for cond, rs in scored.items():
        ai = [(e, p) for l, e, p in rs if l == "ai" and (engines is None or e in engines)]
        hu = [p for l, e, p in rs if l == "human"]
        a = [p for _, p in ai]
        res[cond] = {"auc": auc(a, hu), "caught": sum(p >= thr for p in a), "n": len(a), "fa": sum(p >= thr for p in hu),
                     "max_h": max(hu), "min_ai": min(a), "hum": hu}
    return res


def best_threshold_free_objective(res: dict) -> float:
    """Mean AUC over conditions; ties broken by the human-vs-AI gap so a wider margin wins."""
    return sum(r["auc"] for r in res.values()) / len(res)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--setting", nargs=3, type=float, action="append", metavar=("W_PELLA", "W_HF", "SHARE"), help="repeatable")
    ap.add_argument("--thr", type=float, default=T.P_AI_THRESHOLD)
    a = ap.parse_args()
    rows = json.loads(Path(a.dump).read_text())
    if a.setting:
        grid = [tuple(x) for x in a.setting]
    else:
        grid = list(itertools.product([1.6, 3.0, 4.0, 6.0, 8.0, 10.0], [1.4, 0.7, 0.3, 0.0], [0.6, 0.7, 0.8, 0.85, 0.9]))
    print(f"thr {a.thr} · W_PELLA W_HF SHARE | per condition: AUC caught/n FA maxHuman minAI")
    for g in grid:
        res = summarize(score(rows, g), a.thr)
        cells = "  ".join(f"{c}: {r['auc']:.2f} {r['caught']}/{r['n']} FA{r['fa']} h{r['max_h']:.2f} a{r['min_ai']:.2f}" for c, r in sorted(res.items()))
        print(f"{g[0]:5.1f} {g[1]:4.1f} {g[2]:4.2f} | {cells}")
    if a.setting:
        for g in grid:
            print(f"stress {g}:", stress(rows, g))
        return
    engines = sorted({e for rs in rows.values() for l, e in [(r["label"], r["engine"]) for r in rs] if l == "ai"})
    print("\nleave-one-engine-out: pick the grid setting with best mean AUC on the OTHER engines, score the held-out one")
    for held in engines:
        train = set(engines) - {held}
        best = max(grid, key=lambda g: best_threshold_free_objective(summarize(score(rows, g), a.thr, train)))
        r = summarize(score(rows, best), a.thr, {held})
        print(f"held {held:12} picked {best} -> " + "  ".join(f"{c}: AUC {x['auc']:.2f} caught {x['caught']}/{x['n']}" for c, x in sorted(r.items())))
    print("\nsame, but pick the setting that catches most TRAIN-engine clips at the shipping threshold with 0 humans flagged")
    for held in engines:
        train = set(engines) - {held}
        def obj(g):
            r = summarize(score(rows, g), a.thr, train)
            return -1 if any(x["fa"] for x in r.values()) else sum(x["caught"] for x in r.values())
        best = max(grid, key=obj)
        r = summarize(score(rows, best), a.thr, {held})
        print(f"held {held:12} picked {best} -> " + "  ".join(f"{c}: caught {x['caught']}/{x['n']}" for c, x in sorted(r.items())))


if __name__ == "__main__":
    main()
