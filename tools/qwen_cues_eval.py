#!/usr/bin/env python3
"""Evaluate the Qwen shadow layers (signals/shadow.py qwen_*) on real-vs-Qwen pairs, held out by SCRIPT.

    python3 tools/qwen_cues_eval.py WORK   # needs WORK/audio from tools/qwen_cues_prep.py

For each feature and condition (clean, opus8k, g711_mulaw8k, chain_replay_call, plus floor_matched = Qwen clip with the real
recording's own pause noise added at matched speech-to-noise ratio) prints:
  paired diff (qwen - real) with bootstrap 95% CI over scripts, Cohen dz, and leave-one-script-out results:
  direction is learned on the other 7 scripts, each held-out clip is z-scored against the training real clips, then
  AUC over the 16 held-out clips and paired win rate. Whole clips and 6 s windows (cluster bootstrap by script).
ONE speaker, ONE TTS engine, n = 8 scripts. These are descriptive numbers, not accuracy.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))
from tell.signals import shadow  # noqa: E402

SCRIPTS = ["casual_clone", "long_appointment", "long_checkin", "sales_disclosed", "sales_undisclosed", "scam_bank_otp",
           "scam_grandparent", "scam_irs"]
CONDS = ["clean", "opus8k", "g711_mulaw8k", "chain_replay_call", "floor_matched"]
FEATS = [k for k in shadow.FEATURES if k.startswith("qwen_")] + ["modulation_4_16_ratio"]
rng = np.random.default_rng(0)


def val(name, x):
    v = shadow.FEATURES[name](x)[0]
    return float(v) if np.isfinite(v) else np.nan


def floor_matched(q: np.ndarray, h: np.ndarray) -> np.ndarray:
    dbh = shadow._frame_db(h); mh = shadow._speech_mask(dbh)
    nz = np.concatenate([h[i * 160:i * 160 + 320] for i in np.where(~mh)[0]]) if (~mh).any() else np.zeros(16000)
    dbq = shadow._frame_db(q); mq = shadow._speech_mask(dbq)
    rms = lambda d, m: np.sqrt(np.mean(10 ** (d[m] / 10)))
    g = rms(dbq, mq) / rms(dbh, mh)
    reps = int(np.ceil(len(q) / len(nz)))
    n = np.tile(nz, reps)[:len(q)]
    n = np.roll(n, int(rng.integers(0, len(n))))
    return (q + g * n).astype(np.float32)


def auc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    return float(np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg]))


def loso(vh, vq, boot=2000):
    """vh, vq: arrays (n_scripts,) (or lists of arrays for windows). Returns (auc, ci, win_rate)."""
    n = len(vh)
    zs_h, zs_q = [], []
    for k in range(n):
        tr = [i for i in range(n) if i != k]
        th = np.concatenate([np.atleast_1d(vh[i]) for i in tr]); th = th[np.isfinite(th)]
        tq = np.concatenate([np.atleast_1d(vq[i]) for i in tr]); tq = tq[np.isfinite(tq)]
        sgn = 1.0 if tq.mean() > th.mean() else -1.0
        mu, sd = th.mean(), th.std() + 1e-9
        zs_h.append(sgn * (np.atleast_1d(vh[k]) - mu) / sd)
        zs_q.append(sgn * (np.atleast_1d(vq[k]) - mu) / sd)
    def stat(ix):
        ph = np.concatenate([zs_h[i][np.isfinite(zs_h[i])] for i in ix]); pq = np.concatenate([zs_q[i][np.isfinite(zs_q[i])] for i in ix])
        return auc(pq, ph) if len(ph) and len(pq) else np.nan
    a = stat(list(range(n)))
    bs = [stat(list(rng.integers(0, n, n))) for _ in range(boot if len(np.concatenate(zs_h)) < 100 else 300)]
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    wins = np.mean([np.nanmean(zs_q[i]) > np.nanmean(zs_h[i]) for i in range(n)])
    return a, (lo, hi), float(wins)


def main() -> int:
    work = Path(sys.argv[1]) / "audio"
    clean = {(c, s): np.load(work / f"{c}__{s}__clean.npy") for c in ("human", "qwen") for s in SCRIPTS}
    print(f"{'feature':26s} {'cond':18s} {'real':>8s} {'qwen':>8s} {'diff [95% CI over 8 scripts]':>30s} {'dz':>6s} | {'clip AUC [CI]':>20s} {'wins':>5s} | {'6s-window AUC [CI]':>22s}")
    for f in FEATS:
        for c in CONDS:
            H, Q, WH, WQ = [], [], [], []
            for s in SCRIPTS:
                h = clean[("human", s)] if c == "floor_matched" else np.load(work / f"human__{s}__{c}.npy")
                q = floor_matched(clean[("qwen", s)], clean[("human", s)]) if c == "floor_matched" else np.load(work / f"qwen__{s}__{c}.npy")
                H.append(val(f, h)); Q.append(val(f, q))
                WH.append(np.array([val(f, h[i:i + 96000]) for i in range(0, len(h) - 95999, 96000)]))
                WQ.append(np.array([val(f, q[i:i + 96000]) for i in range(0, len(q) - 95999, 96000)]))
            H, Q = np.array(H), np.array(Q)
            ok = np.isfinite(H) & np.isfinite(Q)
            d = (Q - H)[ok]
            if ok.sum() < 5:
                print(f"{f:26s} {c:18s} too few valid ({ok.sum()})"); continue
            bm = [rng.choice(d, len(d)).mean() for _ in range(5000)]
            lo, hi = np.percentile(bm, [2.5, 97.5])
            dz = d.mean() / d.std(ddof=1)
            a, ci, w = loso(np.where(ok, H, np.nan), np.where(ok, Q, np.nan))
            aw, ciw, _ = loso(WH, WQ)
            print(f"{f:26s} {c:18s} {np.nanmean(H):8.3g} {np.nanmean(Q):8.3g} {d.mean():+10.3g} [{lo:+8.3g},{hi:+8.3g}] {dz:+6.2f} | {a:5.2f} [{ci[0]:.2f},{ci[1]:.2f}] {w:5.2f} | {aw:5.2f} [{ciw[0]:.2f},{ciw[1]:.2f}] n={ok.sum()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
