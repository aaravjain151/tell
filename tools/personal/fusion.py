#!/usr/bin/env python3
"""SHADOW ONLY: a small logistic regression over the full tell vector vs the hand-tuned fusion (p_ai). Not wired in anywhere.

    python3 tools/personal/fusion.py CLIPS.json [--boot 2000] [--seed 3]
    python3 tools/personal/fusion.py data/finetune/pairs/fusion_rows.json --groups     # several human speakers (2026-11-08)

Task: AI voice (1) vs human voice (0). Features per clip: every Tell score (inapplicable -> 0.5) + every shadow feature (missing ->
training median). Model: L2-regularised logistic regression (numpy IRLS), standardised on the training fold.

Protocols (pooled held-out predictions, then AUC and EER with a percentile bootstrap that resamples whole clips = both conditions together):
  leave-one-engine-out : hold out one TTS engine; the human clips are split into the same number of folds BY SCRIPT so no human
                         clip is both trained and tested, and the engines' clips of a held-out human script are excluded from training.
  leave-one-script-out : hold out every clip (all engines + human) of one script.
  leave-one-speaker-out: NOT POSSIBLE. There is ONE human speaker (and the owner's recordings folder is empty), so a held-out human
                         speaker does not exist. Engines stand in as the "speaker" axis for the AI side only.
                         (2026-11-08: rows from finetune/qwen_pairs.py carry a speaker `group` - Sanath, 4 estimated friend
                         speakers, 40 LibriSpeech speakers - and --groups runs leave-one-speaker-group-out; see group_protocols.)
WARNING: one human speaker, ~39 clips. A learned model can win simply by learning that speaker's microphone and room. Nothing here
supports wiring it in.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np


def vectors(rows: list[dict]) -> tuple[np.ndarray, list[str]]:
    tn = sorted({t["name"] for r in rows for t in r["tells"]})
    sh = sorted({k for r in rows for k in r["shadow"]})
    X = np.full((len(rows), len(tn) + len(sh)), np.nan)
    for i, r in enumerate(rows):
        for t in r["tells"]:
            X[i, tn.index(t["name"])] = t["score"] if t["applicable"] else 0.5
        for k, v in r["shadow"].items():
            X[i, len(tn) + sh.index(k)] = np.nan if v is None else v
    names = [f"tell:{n}" for n in tn] + [f"shadow:{n}" for n in sh]
    X[:, : len(tn)] = np.where(np.isnan(X[:, : len(tn)]), 0.5, X[:, : len(tn)])
    return X, names


def fit(X: np.ndarray, y: np.ndarray, lam: float = 3.0, iters: int = 30) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    med = np.nanmedian(X, axis=0)
    med = np.where(np.isnan(med), 0.0, med)
    Xf = np.where(np.isnan(X), med, X)
    mu, sd = Xf.mean(0), Xf.std(0)
    sd = np.where(sd < 1e-9, 1.0, sd)
    Z = np.c_[np.ones(len(Xf)), (Xf - mu) / sd]
    w = np.zeros(Z.shape[1])
    R = lam * np.eye(Z.shape[1])
    R[0, 0] = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Z @ w, -30, 30)))
        g = Z.T @ (p - y) + R @ w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + R + 1e-6 * np.eye(Z.shape[1])
        w = w - np.linalg.solve(H, g)
    return w, med, mu, sd


def predict(model, X: np.ndarray) -> np.ndarray:
    w, med, mu, sd = model
    Xf = np.where(np.isnan(X), med, X)
    return 1 / (1 + np.exp(-np.clip(np.c_[np.ones(len(Xf)), (Xf - mu) / sd] @ w, -30, 30)))


def auc(s: np.ndarray, y: np.ndarray) -> float:
    a, h = s[y == 1], s[y == 0]
    if a.size == 0 or h.size == 0:
        return math.nan
    d = a[:, None] - h[None, :]
    return float(((d > 0) + 0.5 * (d == 0)).mean())


def eer(s: np.ndarray, y: np.ndarray) -> float:
    """Equal error rate: the threshold where miss rate (AI scored below) and false-alarm rate (human at/above) are closest."""
    a, h = s[y == 1], s[y == 0]
    if a.size == 0 or h.size == 0:
        return math.nan
    gaps = [(abs((a < t).mean() - (h >= t).mean()), ((a < t).mean() + (h >= t).mean()) / 2) for t in np.unique(s)]
    return float(min(gaps)[1])


def cv(rows: list[dict], X: np.ndarray, y: np.ndarray, folds: list[tuple[np.ndarray, np.ndarray]]) -> np.ndarray:
    pred = np.full(len(rows), np.nan)
    for tr, te in folds:
        pred[te] = predict(fit(X[tr], y[tr]), X[te])
    return pred


def boot(rows, y, hand, learned, n, seed):
    keys = sorted({(r["engine"], r["name"]) for r in rows})
    idx = {k: [i for i, r in enumerate(rows) if (r["engine"], r["name"]) == k] for k in keys}
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        pick = [idx[keys[j]] for j in rng.integers(len(keys), size=len(keys))]
        ii = np.array([i for g in pick for i in g])
        if y[ii].min() == y[ii].max():
            continue
        out.append((auc(hand[ii], y[ii]), auc(learned[ii], y[ii]), eer(hand[ii], y[ii]), eer(learned[ii], y[ii])))
    o = np.array(out)
    return o


def ci(v: np.ndarray) -> str:
    return f"[{np.percentile(v, 2.5):.2f}, {np.percentile(v, 97.5):.2f}]"


def _unit(r: dict) -> tuple:
    return (r["engine"], r.get("group", ""), r["name"])


def group_protocols(rows: list[dict], X: np.ndarray, y: np.ndarray, hand: np.ndarray, n_boot: int, seed: int) -> None:
    """Rows carry a speaker `group` (several human speakers: finetune/qwen_pairs.py fusion-rows). The Qwen clones of Sanath share
    his group, so holding his group out also holds out every clone of his voice (and, since no other Qwen clip exists, the engine).

    leave-one-speaker-group-out: one fold per group (Sanath + his clones / each friend cluster / each LibriSpeech speaker / each
                                 Gradium voice). Every condition of a clip is in the same fold.
    speaker-groups + Sanath by script: 5 folds; non-Sanath groups round-robin by group, Sanath real + clone by SCRIPT (both
                                 versions of a script together), i.e. his voice is seen but never the held-out script.
    Bootstrap resamples whole clips (all conditions together)."""
    groups = sorted({r["group"] for r in rows})
    protos = {"leave-one-speaker-group-out": [(np.array([i for i, r in enumerate(rows) if r["group"] != g]),
                                               np.array([i for i, r in enumerate(rows) if r["group"] == g])) for g in groups]}
    others = [g for g in groups if g != "sanath"]
    scripts = sorted({r["name"] for r in rows if r["group"] == "sanath"})
    fold = {("g", g): k % 5 for k, g in enumerate(others)} | {("s", s): k % 5 for k, s in enumerate(scripts)}
    fo = np.array([fold[("s", r["name"])] if r["group"] == "sanath" else fold[("g", r["group"])] for r in rows])
    protos["groups + Sanath by script (5-fold)"] = [(np.where(fo != k)[0], np.where(fo == k)[0]) for k in range(5)]
    subsets = {
        "Qwen clone vs Sanath (paired)": lambda r: r["group"] == "sanath",
        "Qwen clone vs all humans": lambda r: r["engine"] in ("qwen3tts", "human"),
        "all AI vs all humans": lambda r: True,
    }
    conds = sorted({r["cond"] for r in rows})
    print("| protocol | subset | condition | n AI / human clips | hand-tuned p_ai AUC [95% CI] | learned LR AUC [95% CI] | learned - hand [95% CI] |")
    print("|---|---|---|---|---|---|---|")
    rng = np.random.default_rng(seed)
    for pname, fl in protos.items():
        pred = cv(rows, X, y, fl)
        for sname, sf in subsets.items():
            for cond in ["all"] + conds:
                ii = np.array([i for i, r in enumerate(rows) if sf(r) and (cond == "all" or r["cond"] == cond) and np.isfinite(pred[i])])
                yy, hh, ll = y[ii], hand[ii], pred[ii]
                units = [_unit(rows[i]) for i in ii]
                keys = sorted(set(units))
                idx = {k: [j for j, u in enumerate(units) if u == k] for k in keys}
                o = []
                for _ in range(n_boot):
                    jj = np.array([j for kk in rng.integers(len(keys), size=len(keys)) for j in idx[keys[kk]]])
                    if yy[jj].min() != yy[jj].max():
                        o.append((auc(hh[jj], yy[jj]), auc(ll[jj], yy[jj])))
                o = np.array(o)
                n1 = len({u for u, t in zip(units, yy) if t == 1})
                n0 = len({u for u, t in zip(units, yy) if t == 0})
                print(f"| {pname} | {sname} | {cond} | {n1} / {n0} | {auc(hh, yy):.2f} {ci(o[:, 0])} | {auc(ll, yy):.2f} {ci(o[:, 1])} | "
                      f"{auc(ll, yy) - auc(hh, yy):+.2f} {ci(o[:, 1] - o[:, 0])} |")
        # false alarms of the learned model at the cut that matches the hand-tuned fusion's own 0.60 false-alarm count is not
        # comparable; report both at 0.5/0.60 on humans and the catch on the clones, per condition
        for cond in conds:
            hm = np.array([i for i, r in enumerate(rows) if r["cond"] == cond and not r["is_ai"] and np.isfinite(pred[i])])
            qm = np.array([i for i, r in enumerate(rows) if r["cond"] == cond and r["engine"] == "qwen3tts" and np.isfinite(pred[i])])
            print(f"<!-- {pname} {cond}: humans flagged hand p_ai>=0.60 {int((hand[hm] >= 0.6).sum())}/{len(hm)}, learned>=0.5 "
                  f"{int((pred[hm] >= 0.5).sum())}/{len(hm)}; Qwen caught hand {int((hand[qm] >= 0.6).sum())}/{len(qm)}, learned "
                  f"{int((pred[qm] >= 0.5).sum())}/{len(qm)} -->")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("clips")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--groups", action="store_true", help="rows carry a speaker `group` (several human speakers): run the group protocols")
    a = ap.parse_args()
    rows = json.loads(Path(a.clips).read_text())
    X, names = vectors(rows)
    keep = ~np.all(np.isnan(X), axis=0)                  # drop features that are n/a on every clip (call-level persistence)
    X, names = X[:, keep], [n for n, k in zip(names, keep) if k]
    y = np.array([1 if r["is_ai"] else 0 for r in rows])
    hand = np.array([r["p_ai"] for r in rows])
    if a.groups:
        print(f"n rows={len(rows)} (AI {int(y.sum())}, human {int((1 - y).sum())}); groups={len({r['group'] for r in rows})}; features={len(names)}")
        group_protocols(rows, X, y, hand, a.boot, a.seed)
        w, _, _, _ = fit(X, y)
        top = np.argsort(-np.abs(w[1:]))[:8]
        print("\nlargest standardised weights (fit on ALL rows, interpretation only): " +
              ", ".join(f"{names[i]} {w[1 + i]:+.2f}" for i in top))
        return 0
    engines = sorted({r["engine"] for r in rows if r["is_ai"]})
    scripts = sorted({r["name"] for r in rows})
    human_scripts = sorted({r["name"] for r in rows if not r["is_ai"]})
    print("**WARNING: one human speaker, tiny n. A learned model can win by learning that speaker's mic/room. Shadow only; not wired in.**")
    print(f"n clips={len(rows)} (AI {int(y.sum())}, human {int((1 - y).sum())}); engines={engines}; features={len(names)}; "
          f"human clips come from {len({r['speaker'] for r in rows if not r['is_ai']})} speaker(s)\n")
    print("| protocol | folds | model | AUC [95% CI] | EER [95% CI] |")
    print("|---|---|---|---|---|")
    protos = {}
    # leave-one-engine-out, human split by script round-robin
    folds = []
    for k, e in enumerate(engines):
        held_scripts = set(human_scripts[k::len(engines)])
        te = np.array([i for i, r in enumerate(rows) if r["engine"] == e or (not r["is_ai"] and r["name"] in held_scripts)])
        tr = np.array([i for i, r in enumerate(rows) if r["engine"] != e and r["name"] not in held_scripts])
        folds.append((tr, te))
    # engines with a single clip pair (owner_qwen) have few humans; fine. Human clips left in no fold are skipped.
    protos["leave-one-engine-out"] = folds
    protos["leave-one-script-out"] = [(np.array([i for i, r in enumerate(rows) if r["name"] != s]),
                                       np.array([i for i, r in enumerate(rows) if r["name"] == s])) for s in scripts]
    for pname, fl in protos.items():
        pred = cv(rows, X, y, fl)
        ok = ~np.isnan(pred)
        rr = [rows[i] for i in np.where(ok)[0]]
        yy, hh, ll = y[ok], hand[ok], pred[ok]
        o = boot(rr, yy, hh, ll, a.boot, a.seed)
        for tag, s, ia, ie in (("hand-tuned p_ai", hh, 0, 2), ("learned LR", ll, 1, 3)):
            print(f"| {pname} | {len(fl)} | {tag} | {auc(s, yy):.2f} {ci(o[:, ia])} | {eer(s, yy):.2f} {ci(o[:, ie])} |")
        d = o[:, 1] - o[:, 0]
        print(f"| {pname} | | AUC difference (learned - hand) | {np.mean(d):+.2f} {ci(d)} | |")
        wins = (d > 0).mean()
        print(f"<!-- P(learned > hand | bootstrap) = {wins:.2f}; n_eval={int(ok.sum())} -->")
    # top coefficients on the full data, for interpretation only
    w, _, _, _ = fit(X, y)
    top = np.argsort(-np.abs(w[1:]))[:6]
    print("\nlargest standardised weights (fit on ALL clips, interpretation only): " +
          ", ".join(f"{names[i]} {w[1 + i]:+.2f}" for i in top))
    print("**WARNING: one human speaker, tiny n; not evidence of generalisation.**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
