#!/usr/bin/env python3
"""SHADOW ONLY: a small logistic regression over the full tell vector vs the hand-tuned fusion (p_ai). Not wired in anywhere.

    python3 tools/personal/fusion.py CLIPS.json [--boot 2000] [--seed 3]

Task: AI voice (1) vs human voice (0). Features per clip: every Tell score (inapplicable -> 0.5) + every shadow feature (missing ->
training median). Model: L2-regularised logistic regression (numpy IRLS), standardised on the training fold.

Protocols (pooled held-out predictions, then AUC and EER with a percentile bootstrap that resamples whole clips = both conditions together):
  leave-one-engine-out : hold out one TTS engine; the human clips are split into the same number of folds BY SCRIPT so no human
                         clip is both trained and tested, and the engines' clips of a held-out human script are excluded from training.
  leave-one-script-out : hold out every clip (all engines + human) of one script.
  leave-one-speaker-out: NOT POSSIBLE. There is ONE human speaker (and the owner's recordings folder is empty), so a held-out human
                         speaker does not exist. Engines stand in as the "speaker" axis for the AI side only.
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("clips")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args()
    rows = json.loads(Path(a.clips).read_text())
    X, names = vectors(rows)
    keep = ~np.all(np.isnan(X), axis=0)                  # drop features that are n/a on every clip (call-level persistence)
    X, names = X[:, keep], [n for n, k in zip(names, keep) if k]
    y = np.array([1 if r["is_ai"] else 0 for r in rows])
    hand = np.array([r["p_ai"] for r in rows])
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
