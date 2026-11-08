#!/usr/bin/env python3
"""Call-level pause features stacked onto the learned_tells head, judged held out. Run with `python -I`.

  python -I training/learned_tells/pauses.py feats                 # LT_DIR/pauses_<cond>.npz from the audio_<cond>.npz caches
  python -I training/learned_tells/pauses.py stack [emb_l2_cal] [12]   # held-out head vs head+pauses -> table + pauses_stack.json
  python -I training/learned_tells/pauses.py export [emb_l2_cal] [12]  # add the "pauses" block to learned_tells.json, print SHA

Stacker: call logit = a * head_logit + sum_i b_i * z(pause_i) + c, a logistic regression per outer fold.
  * head_logit is the head's OUT-OF-FOLD call logit from evaluate.run_scenarios (the clip's speaker group, and in no_<gen>
    its generator, never seen by the head), so the stacker only ever sees honest head scores;
  * the stacker is fitted on the other groups' clips in the TRAINING channels only (evaluate.py's TRAIN_CONDS) and scored on
    the held-out group in the eval channels; chain_replay_call stays eval-only; in no_<gen> the stacker drops that generator too;
  * re-centred on humans like the head (_cal): 0 = the 99th percentile of the stacker's training-human logits;
  * metrics per scenario x channel: clip AUC (bootstrap CI), catch / human false alarms at logit >= 0.
Ship bar (same as the head): every held-out cell catches at least as much as the head alone, with no added false alarm.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import evaluate as E  # noqa: E402
import extract as X  # noqa: E402

from tell.signals import pauses as PZ  # noqa: E402

EVAL_ONLY = ["clean", "opus8k", "g711_mulaw8k", "chain_replay_call"]
CLIP = 5.0
CAL_Q = 99.0


def feats(conds: list[str] | None = None) -> None:
    """Pause features per clip per channel, aligned with sources.csv order."""
    for cond in conds or C.ALL_CONDS:
        path = C.LT / f"audio_{cond}.npz"
        if not path.exists():
            print("skip", cond, "(no audio cache)", flush=True)
            continue
        xs = X.load_audio(cond)
        F = np.array([[PZ.call_pause_features(x)[k] for k in PZ.PAUSE_FEATURES] for x in xs], dtype=np.float64)
        np.savez(C.LT / f"pauses_{cond}.npz", F=F, names=np.array(PZ.PAUSE_FEATURES))
        ok = np.isfinite(F[:, 0]).mean()
        print(cond, len(xs), "clips", f"{ok:.0%} measurable", flush=True)


def load_pauses(cond: str) -> np.ndarray:
    z = np.load(C.LT / f"pauses_{cond}.npz")
    if tuple(z["names"]) != PZ.PAUSE_FEATURES:
        raise SystemExit(f"pauses_{cond}.npz has other features; rerun `pauses.py feats`")
    return z["F"]


def logreg(Z: np.ndarray, y: np.ndarray, w: np.ndarray, l2: float = 1.0, iters: int = 50) -> tuple[np.ndarray, float]:
    """Weighted L2 logistic regression by Newton's method (intercept unpenalised). Same objective as sklearn C=1/l2 with
    weights normalised to mean 1; a handful of parameters, so no sklearn needed in the app's environment."""
    A = np.hstack([Z, np.ones((len(Z), 1))])
    beta = np.zeros(A.shape[1])
    pen = np.full(A.shape[1], l2)
    pen[-1] = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(A @ beta, -30, 30)))
        g = A.T @ (w * (p - y)) + pen * beta
        H = (A * (w * p * (1 - p))[:, None]).T @ A + np.diag(pen) + 1e-9 * np.eye(A.shape[1])
        step = np.linalg.solve(H, g)
        beta -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return beta[:-1], float(beta[-1])


class Stacker:
    """impute(median) -> standardise -> clip pause features; LR on [head_logit, z]; human-centred offset."""

    def fit(self, h: np.ndarray, P: np.ndarray, y: np.ndarray, w: np.ndarray) -> "Stacker":
        self.med = np.nan_to_num(np.nanmedian(P, axis=0))
        Pi = np.where(np.isfinite(P), P, self.med)
        self.mu, self.sd = Pi.mean(0), Pi.std(0) + 1e-9
        Z = self._z(h, P)
        self.coef, self.intercept = logreg(Z, y.astype(float), w / w.mean())
        lg = Z @ self.coef + self.intercept
        self.offset = float(np.percentile(lg[y == 0], CAL_Q)) if (y == 0).any() else 0.0
        return self

    def _z(self, h: np.ndarray, P: np.ndarray) -> np.ndarray:
        Pi = np.where(np.isfinite(P), P, self.med)
        return np.hstack([h[:, None], np.clip((Pi - self.mu) / self.sd, -CLIP, CLIP)])

    def decision(self, h: np.ndarray, P: np.ndarray) -> np.ndarray:
        return self._z(h, P) @ self.coef + self.intercept - self.offset

    def block(self) -> dict:
        r = lambda a: [round(float(v), 6) for v in np.ravel(a)]  # noqa: E731
        return {"features": list(PZ.PAUSE_FEATURES), "median": r(self.med), "mean": r(self.mu), "scale": r(self.sd),
                "clip": CLIP, "coef": r(self.coef[1:]), "head_coef": float(self.coef[0]),
                "intercept": float(self.intercept) - self.offset, "human_offset": self.offset}


def _rows_for(mask: np.ndarray, conds: list[str], oof: dict, P: dict, lab: np.ndarray, cw: np.ndarray):
    """Stack (head logit, pause features, label, weight) over clips in mask x channels, dropping clips the head could not score."""
    h, F, y, w = [], [], [], []
    for c in conds:
        ok = mask & np.isfinite(oof[c])
        h.append(oof[c][ok]); F.append(P[c][ok]); y.append(lab[ok]); w.append(cw[ok])
    return np.concatenate(h), np.vstack(F), np.concatenate(y), np.concatenate(w)


def _setup(fam: str, layer: int):
    C.EVAL_CONDS[:] = [c for c in C.ALL_CONDS if c in set(C.TRAIN_CONDS) | set(EVAL_ONLY)]
    res, rows = E.run_scenarios([fam], layer)
    P = {c: load_pauses(c) for c in C.EVAL_CONDS}
    lab = np.array([r["label"] for r in rows])
    return res, rows, P, lab, E.clip_weights(rows)


def stack(fam: str = "emb_l2_cal", layer: int = 12) -> dict:
    res, rows, P, lab, cw = _setup(fam, layer)
    gen = np.array([r["generator"] for r in rows])
    grp = np.array([r["group"] for r in rows], dtype=object)
    pool = np.array([r["role"] for r in rows]) == "train"
    out, coefs = {}, {}
    for (f, sc), oof in res.items():
        held = sc[3:] if sc.startswith("no_") else None
        st = {c: np.full(len(rows), np.nan) for c in EVAL_ONLY}
        cs = []
        for g in np.unique(grp[pool]):
            tr = pool & (grp != g)
            if held:
                tr &= ~((lab == 1) & (gen == held))
            te = np.where(pool & (grp == g))[0]
            s = Stacker().fit(*_rows_for(tr, C.TRAIN_CONDS, oof, P, lab, cw))
            cs.append(s.coef)
            for c in EVAL_ONLY:
                ok = te[np.isfinite(oof[c][te])]
                st[c][ok] = s.decision(oof[c][ok], P[c][ok])
        coefs[sc] = np.mean(cs, axis=0).round(3).tolist()
        for c in EVAL_ONLY:
            out[f"{sc}|{c}"] = {"head": _metrics(oof[c], lab, pool), "stacked": _metrics(st[c], lab, pool)}
    _print(out, coefs)
    json.dump({"cells": out, "mean_coef": coefs, "coef_names": ["head_logit", *PZ.PAUSE_FEATURES]},
              open(C.LT / "pauses_stack.json", "w"), indent=1)
    return out


def _metrics(s: np.ndarray, lab: np.ndarray, pool: np.ndarray) -> dict:
    ok = pool & np.isfinite(s)
    y, v = lab[ok], s[ok]
    if len(np.unique(y)) < 2:
        return {}
    a, lo, hi = E.auc_ci(v, y)
    return {"auc": round(a, 3), "ci": [round(lo, 3), round(hi, 3)], "catch": round(float((v[y == 1] >= 0).mean()), 3),
            "fa": int((v[y == 0] >= 0).sum()), "n_ai": int((y == 1).sum()), "n_human": int((y == 0).sum())}


def _print(out: dict, coefs: dict) -> None:
    print("\n| scenario | channel | head AUC | +pauses AUC | head catch / FA | +pauses catch / FA |\n|---|---|---|---|---|---|")
    for k, v in out.items():
        h, s = v["head"], v["stacked"]
        if h and s:
            sc, c = k.split("|")
            print(f"| {sc} | {c} | {h['auc']} | {s['auc']} {s['ci']} | {h['catch']} / {h['fa']} | {s['catch']} / {s['fa']} |")
    print("\nmean stacker coefficients [head_logit, " + ", ".join(PZ.PAUSE_FEATURES) + "] (+ = toward AI):")
    for sc, cf in coefs.items():
        print(f"  {sc:10s} {cf}")
    print("Same sign across scenarios = a pause direction that transfers between generators; flips = generator-specific.")


def export(fam: str = "emb_l2_cal", layer: int = 12) -> None:
    """Fit the stacker on every training clip's 'seen' out-of-fold head logit and add it to the shipped weights."""
    res, rows, P, lab, cw = _setup(fam, layer)
    pool = np.array([r["role"] for r in rows]) == "train"
    s = Stacker().fit(*_rows_for(pool, C.TRAIN_CONDS, res[(fam, "seen")], P, lab, cw))
    b = s.block()
    if b["head_coef"] <= 0:
        raise SystemExit(f"head_coef {b['head_coef']:.3f} <= 0: the stacker overrides the head; do not ship")
    path = C.ROOT / "services" / "api" / "tell" / "signals" / "learned_tells.json"
    doc = json.loads(path.read_text())
    doc["pauses"] = b
    raw = (json.dumps(doc, separators=(",", ":"), sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    print(path, len(raw), "bytes", hashlib.sha256(raw).hexdigest())
    print("pause block:", json.dumps({k: b[k] for k in ("coef", "head_coef", "intercept")}))
    print("NEXT: update learned.SHA256 to the hash above, bump thresholds.THRESHOLDS_VERSION, run make test + golden eval.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stack"
    fam = sys.argv[2] if len(sys.argv) > 2 else "emb_l2_cal"
    layer = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    {"feats": lambda: feats(), "stack": lambda: stack(fam, layer), "export": lambda: export(fam, layer)}[cmd]()
