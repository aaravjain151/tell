#!/usr/bin/env python3
"""Held-out evaluation of learned tells (docs/LEARNED-TELLS.md). Run with `python -I`.

  python -I training/learned_tells/evaluate.py models     # every model family, every scenario -> LT_DIR/oof_*.npz + results.json
  python -I training/learned_tells/evaluate.py report     # tables (markdown) from results

Protocol (no leakage):
  * unit = 4 s window; a clip's score = mean of its window logits (the call score);
  * every clip is scored by a model that never saw its SPEAKER GROUP (LibriSpeech speakers in 5 hashed folds, each speaker together
    with their own Qwen clone; Sanath with his Qwen clones; each estimated friend speaker), and in the leave-one-GENERATOR-out
    scenarios by a model that never saw any fake of that generator;
  * scaler, imputer, PCA and the regularisation strength are fitted on the training folds only (C by an inner group CV);
  * training channels: clean, opus8k, g711_mulaw8k, speaker_rerecord_sim, opus_lowbitrate_with_loss; chain_replay_call is
    evaluation-only (a composition never trained as a chain);
  * pure test sets (ElevenLabs lines, owner files, Qwen 1.7B takes, QA calls) are never in any fold.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import data as D  # noqa: E402

GENS = ["qwen", "gradium", "say"]
CLIP_STD = 5.0


# ------------------------------------------------------------------------------------------------ model (numpy inference)
class Model:
    """impute(median) -> standardise -> clip -> [PCA on embeddings -> standardise] -> logistic regression."""

    def __init__(self, kind="l2", C_=None, n_pca=32, feat_idx=None, use_emb=False, use_neural=False, Cs=(0.01, 0.1, 1.0)):
        self.kind, self.C, self.n_pca, self.feat_idx, self.use_emb, self.use_neural, self.Cs = kind, C_, n_pca, feat_idx, use_emb, use_neural, Cs

    def _design(self, Xi, E, N, fit=False):
        parts = []
        if self.feat_idx is not None and len(self.feat_idx):
            x = Xi[:, self.feat_idx]
            if fit:
                self.med = np.nanmedian(x, axis=0)
                self.med = np.where(np.isfinite(self.med), self.med, 0.0)
            x = np.where(np.isfinite(x), x, self.med)
            if fit:
                self.mu, self.sd = x.mean(0), x.std(0) + 1e-9
            parts.append(np.clip((x - self.mu) / self.sd, -CLIP_STD, CLIP_STD))
        if self.use_emb:
            if fit:
                self.e_mu = E.mean(0)
                sub = E[np.random.default_rng(0).choice(len(E), min(len(E), 6000), replace=False)] - self.e_mu
                _, _, vt = np.linalg.svd(sub, full_matrices=False)
                self.pc = vt[: self.n_pca]
            z = (E - self.e_mu) @ self.pc.T
            if fit:
                self.z_mu, self.z_sd = z.mean(0), z.std(0) + 1e-9
            parts.append(np.clip((z - self.z_mu) / self.z_sd, -CLIP_STD, CLIP_STD))
        if self.use_neural:
            N = N[:, :1] if self.use_neural == "pella" else N
            if fit:
                self.n_mu, self.n_sd = N.mean(0), N.std(0) + 1e-9
            parts.append(np.clip((N - self.n_mu) / self.n_sd, -CLIP_STD, CLIP_STD))
        return np.hstack(parts)

    def _lr(self, C_):
        from sklearn.linear_model import LogisticRegression
        if self.kind == "l1":
            return LogisticRegression(penalty="l1", C=C_, solver="liblinear", max_iter=2000)
        return LogisticRegression(C=C_, max_iter=3000)

    def fit(self, Xi, E, N, y, w, groups):
        Z = self._design(Xi, E, N, fit=True)
        if self.kind == "gbm":
            from sklearn.ensemble import HistGradientBoostingClassifier
            self.m = HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05, random_state=0)
            self.m.fit(Z, y, sample_weight=w)
            return self
        if self.C is None:                                          # inner group CV on the TRAINING data only
            inner = np.array([C.fold_of("inner:" + str(g), 3) for g in groups])
            best, bestC = -1, self.Cs[0]
            for C_ in self.Cs:
                sc = []
                for g in range(3):
                    tr, te = inner != g, inner == g
                    if len(np.unique(y[te])) < 2:
                        continue
                    m = self._lr(C_).fit(Z[tr], y[tr], sample_weight=w[tr])
                    sc.append(_auc(m.decision_function(Z[te]), y[te]))
                if sc and np.mean(sc) > best:
                    best, bestC = np.mean(sc), C_
            self.C = bestC
        self.m = self._lr(self.C).fit(Z, y, sample_weight=w)
        return self

    def decision(self, Xi, E, N):
        Z = self._design(Xi, E, N)
        if self.kind == "gbm":
            p = np.clip(self.m.predict_proba(Z)[:, 1], 1e-4, 1 - 1e-4)
            return np.log(p / (1 - p))
        return self.m.decision_function(Z) - getattr(self, "offset", 0.0)


CAL_Q = 99.0


def fit_model(fam, names, A):
    """Fit a family. A '_cal' suffix re-centres the logit on HUMANS: offset = the 99th percentile of human clip logits scored
    out-of-fold inside the training data (3 inner group folds), so 0 means 'at the edge of what real voices we trained on
    look like'. That makes the voter's probability about distance from humans rather than closeness to the fakes it saw,
    which is what matters for a generator it never saw."""
    base = fam[:-4] if fam.endswith("_cal") else fam
    m = make_model(base, names).fit(A["X"], A["E"], A["N"], A["y"], A["w"], A["g"])
    if base == fam:
        return m
    inner = np.array([C.fold_of("cal:" + str(g), 3) for g in A["g"]])
    vals = []
    for k in range(3):
        tr, te = inner != k, (inner == k) & (A["y"] == 0)
        if not te.any():
            continue
        sub = make_model(base, names)
        sub.C = m.C
        sub.fit(A["X"][tr], A["E"][tr], A["N"][tr], A["y"][tr], A["w"][tr], A["g"][tr])
        lg = sub.decision(A["X"][te], A["E"][te], A["N"][te])
        key = np.char.add(A["clip"][te].astype(str), A["cond"][te].astype(str))
        for u in np.unique(key):
            vals.append(float(np.mean(lg[key == u])))
    m.offset = float(np.percentile(vals, CAL_Q))
    return m


def _auc(s, y):
    s, y = np.asarray(s, float), np.asarray(y, int)
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(np.concatenate([neg, pos]), kind="mergesort")
    ranks = np.empty(len(order)); ranks[order] = np.arange(1, len(order) + 1)
    allv = np.concatenate([neg, pos])
    # average ties
    _, inv, cnt = np.unique(allv, return_inverse=True, return_counts=True)
    sums = np.bincount(inv, weights=ranks); ranks = (sums / cnt)[inv]
    return float((ranks[len(neg):].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def auc_ci(s, y, n_boot=1000, seed=0):
    rng = np.random.default_rng(seed)
    s, y = np.asarray(s, float), np.asarray(y, int)
    ip, ineg = np.where(y == 1)[0], np.where(y == 0)[0]
    a = _auc(s, y)
    if len(ip) == 0 or len(ineg) == 0:
        return a, float("nan"), float("nan")
    bs = []
    for _ in range(n_boot):
        b = np.concatenate([rng.choice(ineg, len(ineg)), rng.choice(ip, len(ip))])
        bs.append(_auc(s[b], y[b]))
    return a, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


# ------------------------------------------------------------------------------------------------ dataset assembly
def clip_weights(rows):
    """Per-clip weight: classes equal; inside the fake class each generator ~ sqrt(n); inside humans each domain ~ sqrt(n)."""
    lab = np.array([r["label"] for r in rows])
    key = np.array([r["generator"] if r["label"] else r["note"].split()[0] for r in rows])
    w = np.zeros(len(rows))
    for c in (0, 1):
        ks = np.unique(key[lab == c])
        tot = {k: np.sqrt((key[lab == c] == k).sum()) for k in ks}
        for k in ks:
            m = (lab == c) & (key == k)
            w[m] = tot[k] / m.sum()
        w[lab == c] /= w[lab == c].sum()
    return w


def assemble(conds, layer, rows, clip_mask):
    """Stack windows of the selected clips over conditions. Returns dict of arrays."""
    Xs, Es, Ns, ys, ws, gs, cs, cid = [], [], [], [], [], [], [], []
    cw = clip_weights(rows)
    lab = np.array([r["label"] for r in rows])
    grp = np.array([r["group"] for r in rows])
    for cond in conds:
        d = D.load(cond, (layer,))
        for i in np.where(clip_mask)[0]:
            w = d.win_of[i]
            if len(w) == 0:
                continue
            Xs.append(d.X[w]); Es.append(d.emb[layer][w])
            Ns.append(np.stack([np.clip(d.pella_logit[w], -9.2103, 9.2103), D.logit(d.hf_p[w])], 1))
            ys.append(np.full(len(w), lab[i])); ws.append(np.full(len(w), cw[i] / len(w)))
            gs.append(np.full(len(w), grp[i], dtype=object)); cs.append(np.full(len(w), cond, dtype=object)); cid.append(np.full(len(w), i))
    return dict(X=np.vstack(Xs), E=np.vstack(Es), N=np.vstack(Ns), y=np.concatenate(ys), w=np.concatenate(ws),
                g=np.concatenate(gs), cond=np.concatenate(cs), clip=np.concatenate(cid))


def clip_scores(model, cond, layer, idx):
    d = D.load(cond, (layer,))
    out = np.full(len(idx), np.nan)
    for k, i in enumerate(idx):
        w = d.win_of[i]
        if len(w) == 0:
            continue
        N = np.stack([np.clip(d.pella_logit[w], -9.2103, 9.2103), D.logit(d.hf_p[w])], 1)
        out[k] = float(np.mean(model.decision(d.X[w], d.emb[layer][w], N)))
    return out


FAMILIES = {
    # name: (kind, use interpretable voice feats, use channel feats, use emb, use neural)
    "interp_l2": ("l2", True, False, False, False),
    "interp_l1": ("l1", True, False, False, False),
    "interp_ch_l2": ("l2", True, True, False, False),
    "emb_l2": ("l2", False, False, True, False),
    "interp_emb_l2": ("l2", True, False, True, False),
    "stack_l2": ("l2", True, False, True, True),
    "interp_neural_l2": ("l2", True, False, False, True),
    "interp_pella_l2": ("l2", True, False, False, "pella"),
    "interp_emb_pella_l2": ("l2", True, False, True, "pella"),
    "interp_emb_pella_l1": ("l1", True, False, True, "pella"),
    "gbm_interp_neural": ("gbm", True, False, False, True),
}


def make_model(fam, names):
    from tell.signals import tell_features as TF
    kind, iv, ich, ue, un = FAMILIES[fam[:-4] if fam.endswith("_cal") else fam]
    idx = [j for j, n in enumerate(names) if (iv and n not in TF.CHANNEL_FEATURES) or (ich and n in TF.CHANNEL_FEATURES)]
    return Model(kind=kind, feat_idx=np.array(idx, int), use_emb=ue, use_neural=un)


def run_scenarios(fams, layer=12, group_scheme="cluster", scenarios=None):
    rows = D.sources()
    n = len(rows)
    lab = np.array([r["label"] for r in rows])
    gen = np.array([r["generator"] for r in rows])
    role = np.array([r["role"] for r in rows])
    grp = np.array([r["group"] for r in rows], dtype=object)
    if group_scheme == "single":
        grp = np.array(["friends" if g.startswith("f") and r["note"] == "phone memo" else g for g, r in zip(grp, rows)], dtype=object)
        for r, g in zip(rows, grp):
            r["group"] = g
    names = D.load("clean", (layer,)).names
    train_pool = role == "train"
    scen = scenarios or (["seen"] + [f"no_{g}" for g in GENS])
    res = {}
    for fam in fams:
        for sc in scen:
            held_gen = sc[3:] if sc.startswith("no_") else None
            oof = {c: np.full(n, np.nan) for c in C.EVAL_CONDS}
            for g in np.unique(grp[train_pool]):
                te_mask = train_pool & (grp == g)
                tr_mask = train_pool & (grp != g)
                if held_gen:
                    tr_mask &= ~((lab == 1) & (gen == held_gen))
                A = assemble(C.TRAIN_CONDS, layer, rows, tr_mask)
                m = fit_model(fam, names, A)
                idx = np.where(te_mask)[0]
                for c in C.EVAL_CONDS:
                    oof[c][idx] = clip_scores(m, c, layer, idx)
            res[(fam, sc)] = oof
            print(fam, sc, "done", flush=True)
    return res, rows


def run_scripts(fams, layer=12, k=5):
    """Sanath vs his Qwen clones, held out BY SCRIPT: the model saw other scripts of both (and every other speaker)."""
    rows = D.sources()
    n = len(rows)
    role = np.array([r["role"] for r in rows])
    grp = np.array([r["group"] for r in rows])
    scr = np.array([r["script"] for r in rows])
    names = D.load("clean", (layer,)).names
    pool = role == "train"
    sanath = pool & (grp == "sanath")
    scripts = sorted(set(scr[sanath]))
    fold = {s: C.fold_of("script:" + s, k) for s in scripts}
    res = {}
    for fam in fams:
        oof = {c: np.full(n, np.nan) for c in C.EVAL_CONDS}
        for f in range(k):
            held = {s for s in scripts if fold[s] == f}
            te = sanath & np.isin(scr, list(held))
            tr = pool & ~te
            A = assemble(C.TRAIN_CONDS, layer, rows, tr)
            m = fit_model(fam, names, A)
            idx = np.where(te)[0]
            for c in C.EVAL_CONDS:
                oof[c][idx] = clip_scores(m, c, layer, idx)
        res[fam] = oof
        print(fam, "scripts done", flush=True)
    return res


def fit_final(fam, layer=12, exclude_group=None):
    rows = D.sources()
    role = np.array([r["role"] for r in rows])
    grp = np.array([r["group"] for r in rows])
    mask = role == "train"
    if exclude_group:
        mask &= grp != exclude_group
    A = assemble(C.TRAIN_CONDS, layer, rows, mask)
    names = D.load("clean", (layer,)).names
    return fit_model(fam, names, A), rows


if __name__ == "__main__":
    cmd = sys.argv[1]
    layer = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    fams = sys.argv[3].split(",") if len(sys.argv) > 3 else list(FAMILIES)
    if cmd == "models":
        res, rows = run_scenarios(fams, layer)
        out = {f"{fam}|{sc}|{c}": v[c].tolist() for (fam, sc), v in res.items() for c in v}
        json.dump(out, open(C.LT / f"oof_L{layer}_{'_'.join(fams) if len(fams) < 3 else 'all'}.json", "w"))
    elif cmd == "single":           # all 12 phone memos held out TOGETHER (conservative: no phone-memo speaker in training)
        res, rows = run_scenarios(fams, layer, group_scheme="single", scenarios=["seen"])
        json.dump({f"{fam}|{sc}|{c}": v[c].tolist() for (fam, sc), v in res.items() for c in v},
                  open(C.LT / f"oof_single_L{layer}_{'_'.join(fams)}.json", "w"))
    elif cmd == "lossy":            # the lossy paths where Pellav2 false-alarms on real humans (docs/HEAD-FINETUNE.md)
        C.EVAL_CONDS[:] = ["chain_pstn_voip", "opus_lowbitrate_with_loss"]
        res, rows = run_scenarios(fams, layer, scenarios=["seen"])
        json.dump({f"{fam}|{sc}|{c}": v[c].tolist() for (fam, sc), v in res.items() for c in v},
                  open(C.LT / f"oof_lossy_L{layer}_{'_'.join(fams)}.json", "w"))
    elif cmd == "scripts":
        res = run_scripts(fams, layer)
        json.dump({f"{fam}|{c}": v[c].tolist() for fam, v in res.items() for c in v}, open(C.LT / f"oof_scripts_L{layer}.json", "w"))
