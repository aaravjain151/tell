#!/usr/bin/env python3
"""Step 3: train a small head on cached frozen-backbone features and evaluate it honestly against the shipped voters.

  python3 finetune/head_train_eval.py evaluate  [--backbone pella|hf] [--kind mlp|linear] [--aug|--clean-only] -> data/finetune/results_*.json
  python3 finetune/head_train_eval.py final [--backbone pella] -> data/finetune/head_pella.pt (+ .json), trained on ALL non-owner data

Honest protocol (see docs/HEAD-FINETUNE.md):
  * speakers (80 LibriSpeech + Sanath + demo voices + Gradium voices + `say` voices) are split into 5 folds; a window is only ever scored
    by a model that never saw its SPEAKER;
  * for each generator g in {qwen, gradium, say} the model is ALSO trained without any g fake, so fakes are scored by a model that never saw
    their GENERATOR nor their speaker (leave-one-generator-out x leave-speakers-out; scores are pooled out-of-fold);
  * the same channel conditions are applied to both classes; training conditions are listed in TRAIN_CONDS, the rest are eval-only;
  * hyper-parameters are fixed a priori (no early stopping, no threshold picked on test data);
  * the baseline columns are the SHIPPED voters' probabilities on the same windows.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FT = ROOT / "data" / "finetune"
CONDS = ["clean", "opus8k", "g711_mulaw8k", "g711_alaw8k", "opus_lowbitrate_with_loss", "speaker_rerecord_sim", "chain_pstn_voip", "chain_replay_call"]
TRAIN_CONDS = ["clean", "opus8k", "g711_mulaw8k", "opus_lowbitrate_with_loss", "speaker_rerecord_sim"]
EVAL_CONDS = ["clean", "opus8k", "g711_mulaw8k", "chain_replay_call", "g711_alaw8k", "chain_pstn_voip"]
GENS = ["qwen", "gradium", "say"]
import os
K_FOLDS, SEED = 5, int(os.environ.get("HEAD_FOLD_SEED", "7"))
HN = FT / "humans_new"          # new real humans (finetune/head_humans.py); appended only with --extra-humans
EXTRA = {"on": False, "groups": "location"}
SP = FT / "pairs" / "win"       # Sanath real + Qwen-clone pairs (finetune/qwen_pairs.py windows/features); used only with --sanath-pairs
PAIRS = {"on": False, "split": "script", "no_fakes": False}


# --------------------------------------------------------------------------------------------- data
def _new_speaker(m: dict) -> str:
    """Speaker-group label of a new human window: location (conservative: one group per recording place) or the
    estimated speaker cluster from head_humans.py speakers, or one group for all."""
    if EXTRA["groups"] == "location":
        return f"new_{m['group']}"
    if EXTRA["groups"] == "single":            # most conservative: all new clips are one group, scored only by models that saw none of them
        return "new_all"
    # estimated speakers: the wav2vec2 layer-5 best-silhouette cut (k=4; it groups one clip of each script per cluster,
    # so it is not a same-text artefact; the w2v-BERT cut agrees except that it splits one clip off). A GUESS.
    sp = json.loads((HN / "speakers.json").read_text())["hf"]
    return f"new_c{dict(zip(sp['clips'], sp['clusters_k_best']))[m['clip']]}"


def _sanath_script_fold(script: str) -> int:
    """Script -> fold for the Sanath pairs (--sanath-pairs script): sorted scripts shuffled with the fold seed, round-robin.
    Both the real reading and the Qwen clone of a script land in the same fold, so no script is in train and test."""
    scripts = sorted({m["script"] for m in csv.DictReader(open(SP / "windows.csv"))})
    rng = np.random.default_rng(SEED + 100)
    rng.shuffle(scripts)
    return {sc: i % K_FOLDS for i, sc in enumerate(scripts)}[script]


def _keep_old() -> np.ndarray:
    """With --sanath-pairs the old cache's Sanath rows (10 real + 9 clone clips) and the two owner files are replaced by the pairs set."""
    old = list(csv.DictReader(open(FT / "windows.csv")))
    return np.array([not (PAIRS["on"] and (m["speaker"] == "sanath" or m["owner"] == "1")) for m in old])


def load_meta() -> list[dict]:
    meta = list(csv.DictReader(open(FT / "windows.csv")))
    if PAIRS["on"]:
        keep = _keep_old()
        meta = [m for m, k in zip(meta, keep) if k]
        for m in csv.DictReader(open(SP / "windows.csv")):
            m["speaker"] = f"sanath_s{_sanath_script_fold(m['script'])}" if PAIRS["split"] == "script" else "sanath"
            m["wid"] = str(len(meta))
            meta.append(m)
    if EXTRA["on"]:
        new = list(csv.DictReader(open(HN / "windows.csv")))
        for m in new:
            m["speaker"] = _new_speaker(m)
            m["wid"] = str(len(meta) + int(m["wid"]))
        meta = meta + new
    return meta


def load(backbone: str):
    meta = load_meta()
    F = {c: dict(np.load(FT / f"feat_{backbone}_{c}.npz")) for c in CONDS}
    if PAIRS["on"]:
        keep = _keep_old()
        Fp = {c: np.load(SP / f"feat_{backbone}_{c}.npz") for c in CONDS}
        for c in CONDS:
            F[c] = {k: np.concatenate([F[c][k][keep], Fp[c][k]]) for k in ("mean", "std", "p_current")}
    if EXTRA["on"]:
        Fn = {c: np.load(HN / f"feat_{backbone}_{c}.npz") for c in CONDS}
        for c in CONDS:
            F[c] = {k: np.concatenate([F[c][k], Fn[c][k]]) for k in ("mean", "std", "p_current")}
    return meta, F


def folds_for(meta) -> dict[str, int]:
    rng = np.random.default_rng(SEED)
    spk = sorted({m["speaker"] for m in meta if m["owner"] == "0" and m.get("split") not in ("humans_new", "sanath_pairs")}
                 | ({"sanath"} if PAIRS["on"] else set()))
    rng.shuffle(spk)
    f = {s: i % K_FOLDS for i, s in enumerate(spk)}          # identical to the 2026-11-07 run for the old speakers
    for k in range(K_FOLDS):
        f[f"sanath_s{k}"] = k                                  # --sanath-pairs script: Sanath scripts spread over the 5 folds
    for j, s in enumerate(sorted({m["speaker"] for m in meta if m.get("split") == "humans_new"})):
        f[s] = K_FOLDS + j                                     # every new speaker group is its OWN held-out fold
    f["owner"] = -1
    return f


# --------------------------------------------------------------------------------------------- metrics
def roc_metrics(y: np.ndarray, s: np.ndarray) -> dict:
    from sklearn.metrics import roc_auc_score, roc_curve
    n1, n0 = int(y.sum()), int((1 - y).sum())
    out = {"n_fake": n1, "n_real": n0}
    if n1 == 0 or n0 == 0:
        return out
    fpr, tpr, _ = roc_curve(y, s)
    fnr = 1 - tpr
    i = int(np.nanargmin(np.abs(fnr - fpr)))
    out["auc"] = float(roc_auc_score(y, s))
    out["eer"] = float((fpr[i] + fnr[i]) / 2)
    out["fpr_at_tpr90"] = float(fpr[np.searchsorted(tpr, 0.90, side="left").clip(max=len(fpr) - 1)])
    out["tpr_at_fpr5"] = float(tpr[np.searchsorted(fpr, 0.05, side="right") - 1])
    out["tpr_at_0.5"] = float((s[y == 1] >= 0.5).mean())
    out["fpr_at_0.5"] = float((s[y == 0] >= 0.5).mean())
    return out


def boot_auc(y, s, clips, n=300, seed=0):
    """95% percentile CI for AUC, resampling whole source clips (windows of one clip are not independent)."""
    from sklearn.metrics import roc_auc_score
    rng = np.random.default_rng(seed)
    uc = np.unique(clips)
    idx_by = {c: np.where(clips == c)[0] for c in uc}
    vals = []
    for _ in range(n):
        pick = rng.choice(uc, len(uc))
        ii = np.concatenate([idx_by[c] for c in pick])
        if 0 < y[ii].sum() < len(ii):
            vals.append(roc_auc_score(y[ii], s[ii]))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else None


# --------------------------------------------------------------------------------------------- model
def build_head(L, D, kind, use_std):
    import torch
    import torch.nn as nn

    class Head(nn.Module):
        def __init__(self):
            super().__init__()
            self.layer_weights = nn.Parameter(torch.zeros(L))
            din = D * (2 if use_std else 1)
            self.register_buffer("mu", torch.zeros(din))
            self.register_buffer("sd", torch.ones(din))
            if kind == "mlp":
                self.net = nn.Sequential(nn.Dropout(0.3), nn.Linear(din, 128), nn.GELU(), nn.Dropout(0.3), nn.Linear(128, 1))
            else:
                self.net = nn.Sequential(nn.Dropout(0.1), nn.Linear(din, 1))
            self.use_std = use_std

        def pool(self, mean, std):
            w = torch.softmax(self.layer_weights, 0)[None, :, None]
            z = (mean * w).sum(1)
            if self.use_std:
                z = torch.cat([z, (std * w).sum(1)], 1)
            return z

        def forward(self, mean, std):
            return self.net((self.pool(mean, std) - self.mu) / self.sd).squeeze(-1)

    return Head()


def fit(Xm, Xs, y, sw, kind, use_std, epochs=25, seed=0, bs=128, lr=1e-3):
    import torch
    torch.manual_seed(seed)
    N, L, D = Xm.shape
    h = build_head(L, D, kind, use_std)
    with torch.no_grad():
        z = h.pool(torch.from_numpy(Xm[::max(1, N // 2000)].astype(np.float32)), torch.from_numpy(Xs[::max(1, N // 2000)].astype(np.float32)))
        h.mu.copy_(z.mean(0))
        h.sd.copy_(z.std(0) + 1e-5)
    opt = torch.optim.AdamW(h.parameters(), lr=lr, weight_decay=1e-2)
    yt, swt = torch.from_numpy(y.astype(np.float32)), torch.from_numpy(sw.astype(np.float32))
    for _ in range(epochs):
        h.train()
        for ib in torch.randperm(N).split(bs):
            ii = ib.numpy()
            xm = torch.from_numpy(Xm[ii].astype(np.float32))
            xs = torch.from_numpy(Xs[ii].astype(np.float32))
            # Gaussian jitter on the pooled features: cheap regulariser against memorising a single clip
            loss = (torch.nn.functional.binary_cross_entropy_with_logits(h(xm, xs), yt[ib], reduction="none") * swt[ib]).sum() / swt[ib].sum()
            opt.zero_grad()
            loss.backward()
            opt.step()
    return h.eval()


def predict(h, Xm, Xs, bs=512):
    import torch
    out = []
    with torch.no_grad():
        for i in range(0, len(Xm), bs):
            out.append(torch.sigmoid(h(torch.from_numpy(Xm[i:i + bs].astype(np.float32)), torch.from_numpy(Xs[i:i + bs].astype(np.float32)))).numpy())
    return np.concatenate(out)


def weights_for(label, gen, speaker):
    """Per-window weights: each class sums to 1; within a class a speaker (reals) / generator (fakes) counts by sqrt of its window count."""
    n = len(label)
    w = np.ones(n)
    key = np.array([f"{l}|{g if l == 1 else s}" for l, g, s in zip(label, gen, speaker)])
    for k in np.unique(key):
        m = key == k
        w[m] = 1.0 / np.sqrt(m.sum())          # group total = sqrt(count)
    for l in (0, 1):
        m = label == l
        w[m] /= w[m].sum()
    return w * n


def assemble(meta, F, conds):
    idx = np.array([i for i, m in enumerate(meta) if m["owner"] == "0"])
    Xm = np.concatenate([F[c]["mean"][idx] for c in conds])
    Xs = np.concatenate([F[c]["std"][idx] for c in conds])
    rep = len(conds)
    lab = np.tile(np.array([int(meta[i]["label"]) for i in idx]), rep)
    gen = np.tile(np.array([meta[i]["generator"] for i in idx]), rep)
    spk = np.tile(np.array([meta[i]["speaker"] for i in idx]), rep)
    return idx, Xm, Xs, lab, gen, spk


def run_eval(backbone, kind, use_std, aug, epochs, train_conds_arg=None):
    meta, F = load(backbone)
    fold = folds_for(meta)
    train_conds = train_conds_arg or (TRAIN_CONDS if aug else ["clean"])
    idx, Xm, Xs, lab, gen, spk = assemble(meta, F, train_conds)
    fold_of = np.array([fold[s] for s in spk])
    sources = {"current": {c: F[c]["p_current"] for c in CONDS}}
    # OOF scores per scenario: scores[scn][cond] -> array over ALL windows (NaN where not scored)
    scenarios = ["seen_gen"] + [f"loo_{g}" for g in GENS]
    scores = {s: {c: np.full(len(meta), np.nan) for c in CONDS} for s in scenarios}
    owner_idx = np.array([i for i, m in enumerate(meta) if m["owner"] == "1"])
    owner_scores = {s: {c: [] for c in CONDS} for s in scenarios}
    t0 = time.time()
    n_params = None
    for scn in scenarios:
        g_out = scn[4:] if scn.startswith("loo_") else None
        for k in range(max(fold.values()) + 1):
            tr = (fold_of != k) & ((lab == 0) | (gen != g_out) if g_out else True)
            if PAIRS["no_fakes"]:                              # ablation: Sanath clones never in training
                tr = tr & ~((lab == 1) & np.char.startswith(spk.astype(str), "sanath"))
            h = fit(Xm[tr], Xs[tr], lab[tr], weights_for(lab[tr], gen[tr], spk[tr]), kind, use_std, epochs=epochs, seed=k)
            n_params = sum(p.numel() for p in h.parameters())
            te_w = np.array([fold[meta[i]["speaker"]] == k for i in idx])
            for c in CONDS:
                s = predict(h, F[c]["mean"][idx][te_w], F[c]["std"][idx][te_w])
                scores[scn][c][idx[te_w]] = s
                if len(owner_idx):
                    owner_scores[scn][c].append(predict(h, F[c]["mean"][owner_idx], F[c]["std"][owner_idx]))
        print(f"{scn} done {time.time() - t0:.0f}s", flush=True)
    return meta, idx, sources, scores, owner_idx, owner_scores, n_params, time.time() - t0


def report(meta, idx, sources, scores, owner_idx, owner_scores, n_params, secs, tag, sanath_fold=0):
    y_all = np.array([int(m["label"]) for m in meta])
    gen_all = np.array([m["generator"] for m in meta])
    clip_all = np.array([m["clip"] for m in meta])
    res = {"tag": tag, "head_params": n_params, "train_seconds_total_all_folds": round(secs, 1), "table": {}}

    def block(name, s_by_cond, mask_fn):
        for c in EVAL_CONDS:
            s = s_by_cond[c]
            m = mask_fn & np.isfinite(s)
            m[[i for i, mm in enumerate(meta) if mm["owner"] == "1"]] = False
            r = roc_metrics(y_all[m], s[m])
            if c in ("clean", "chain_replay_call") and "auc" in r:
                r["auc_ci95"] = boot_auc(y_all[m], s[m], clip_all[m])
            res["table"].setdefault(name, {})[c] = r

    for g in GENS:
        mk = (y_all == 0) | (gen_all == g)
        block(f"loo_{g}/head", scores[f"loo_{g}"], mk)
        block(f"loo_{g}/current", sources["current"], mk)
    spk_all = np.array([m["speaker"] for m in meta])
    is_san = np.char.startswith(spk_all.astype(str), "sanath")
    mk = ((y_all == 0) & is_san) | ((y_all == 1) & (gen_all == "qwen") & is_san)
    block("sanath_only_loo_qwen/head", scores["loo_qwen"], mk)
    block("sanath_only_loo_qwen/current", sources["current"], mk)
    pairs_rows = np.array([m.get("split") == "sanath_pairs" for m in meta])
    if pairs_rows.any():
        # the paired set: Sanath real vs his Qwen clone; every window scored by a model that never saw its SCRIPT (script split)
        # or never saw Sanath at all (speaker split). new = scripts recorded after the 2026-11-07 study.
        old8 = {"casual_clone", "long_appointment", "long_checkin", "sales_disclosed", "sales_undisclosed", "scam_bank_otp",
                "scam_grandparent", "scam_irs", "long_agent_undisclosed"}
        new_s = np.array([m.get("split") == "sanath_pairs" and m["script"] not in old8 for m in meta])
        for scn in ("seen_gen", "loo_qwen"):
            block(f"sanath_pairs_{scn}/head", scores[scn], pairs_rows)
            block(f"sanath_pairs_new_{scn}/head", scores[scn], new_s)
        block("sanath_pairs/current", sources["current"], pairs_rows)
        block("sanath_pairs_new/current", sources["current"], new_s)
        src = np.array(["libri" if m.get("split") in ("dev-clean", "test-clean") else "sanath" if m.get("split") == "sanath_pairs" else
                        "friends" if m.get("split") == "humans_new" else "other" for m in meta])
        fa = {}
        for name, sc in [("head_seen_gen", scores["seen_gen"]), ("head_loo_qwen", scores["loo_qwen"]), ("current", sources["current"])]:
            fa[name] = {}
            for c in EVAL_CONDS:
                fa[name][c] = {}
                for g in ("libri", "sanath", "friends"):
                    mm = (y_all == 0) & (src == g) & np.isfinite(sc[c])
                    if mm.any():
                        fa[name][c][g] = {"n": int(mm.sum()), "fpr_0.5": float((sc[c][mm] >= 0.5).mean())}
        res["human_false_alarms_by_source"] = fa
    mk = np.ones(len(meta), bool)
    block("seen_gen/head", scores["seen_gen"], mk)
    block("seen_gen/current", sources["current"], mk)
    new_h = np.array([m.get("split") == "humans_new" for m in meta])
    if new_h.any():
        # reals = ONLY the new phone-memo humans (each scored by a model that never saw its group); fakes = held-out generator
        for g in GENS:
            mk = new_h | ((y_all == 1) & (gen_all == g))
            block(f"newhum_loo_{g}/head", scores[f"loo_{g}"], mk)
            block(f"newhum_loo_{g}/current", sources["current"], mk)
        old_real = (y_all == 0) & ~new_h
        fa = {}
        for name, src in [("head_loo_qwen", scores["loo_qwen"]), ("head_seen_gen", scores["seen_gen"]), ("current", sources["current"])]:
            fa[name] = {}
            for c in EVAL_CONDS:
                s = src[c]
                op = float(np.nanquantile(s[old_real], 0.95))          # 5% FPR on the OLD reals (out-of-fold for the head)
                fa[name][c] = {"n_new_windows": int(new_h.sum()), "fa_0.5": float((s[new_h] >= 0.5).mean()), "op_fpr5_old": op,
                               "fa_op": float((s[new_h] >= op).mean()),
                               "by_group": {sp: float((s[new_h & (spk_all == sp)] >= 0.5).mean()) for sp in sorted(set(spk_all[new_h]))}}
        res["new_humans_false_alarms"] = fa
    # owner files: mean over the production windows of each file, per scenario (mean over the 5 fold-models)
    own = {}
    for name in ("owner_rough_morning", "owner_long_tech_scam"):
        ii = np.array([j for j, i in enumerate(owner_idx) if meta[i]["clip"] == name])
        if not len(ii):
            continue
        own[name] = {"n_windows": int(len(ii)), "current": {c: float(np.mean(sources["current"][c][owner_idx[ii]])) for c in ("clean", "opus8k", "chain_replay_call")}}
        for scn in owner_scores:
            own[name][scn] = {c: float(np.mean(np.mean(owner_scores[scn][c], 0)[ii])) for c in ("clean", "opus8k", "chain_replay_call")}
            # the single fold-model that never saw Sanath (real or cloned): the cleanest speaker-held-out score for these Sanath-voice files
            own[name][scn + "_sanath_heldout"] = {c: float(owner_scores[scn][c][sanath_fold][ii].mean()) for c in ("clean", "opus8k", "chain_replay_call")}
    res["owner"] = own
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["evaluate", "final"])
    ap.add_argument("--backbone", default="pella")
    ap.add_argument("--kind", default="mlp")
    ap.add_argument("--no-std", action="store_true")
    ap.add_argument("--clean-only", action="store_true")
    ap.add_argument("--train-all-conds", action="store_true", help="also train on the eval conditions (all 8 chains)")
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--out", default="")
    ap.add_argument("--extra-humans", choices=["", "location", "cluster", "single"], default="",
                    help="append the new phone-memo humans (data/finetune/humans_new) to the real class, grouped by location, estimated speaker cluster, or as one group")
    ap.add_argument("--sanath-pairs", choices=["", "script", "speaker"], default="",
                    help="replace the old Sanath rows by the 2026-11-08 Sanath real + Qwen-clone pairs (data/finetune/pairs/win), folded by script or as one speaker")
    ap.add_argument("--no-sanath-fakes", action="store_true", help="with --sanath-pairs: never train on a Sanath clone (ablation)")
    a = ap.parse_args()
    if a.sanath_pairs:
        PAIRS.update(on=True, split=a.sanath_pairs, no_fakes=a.no_sanath_fakes)
    if a.extra_humans:
        EXTRA.update(on=True, groups=a.extra_humans)
    use_std = not a.no_std
    tag = f"{'pairs_' + a.sanath_pairs + ('_nofakes' if a.no_sanath_fakes else '') + '_' if a.sanath_pairs else ''}{'hum_' + a.extra_humans + '_' if a.extra_humans else ''}{'s' + str(SEED) + '_' if SEED != 7 else ''}{'all_' if a.train_all_conds else ''}{a.backbone}_{a.kind}{'' if use_std else '_meanonly'}{'_cleanonly' if a.clean_only else ''}"
    if a.mode == "evaluate":
        meta0 = load_meta()
        r = report(*run_eval(a.backbone, a.kind, use_std, not a.clean_only, a.epochs, CONDS if a.train_all_conds else None), tag,
                   sanath_fold=folds_for(meta0).get("sanath", 0))
        (FT / f"results_{tag}.json").write_text(json.dumps(r, indent=1))
        print("wrote", FT / f"results_{tag}.json", "params", r["head_params"])
    else:
        import torch
        meta, F = load(a.backbone)
        idx, Xm, Xs, lab, gen, spk = assemble(meta, F, TRAIN_CONDS)
        t0 = time.time()
        h = fit(Xm, Xs, lab, weights_for(lab, gen, spk), a.kind, use_std, epochs=a.epochs)
        sd = {k: v.detach().clone() for k, v in h.state_dict().items()}
        out = Path(a.out or FT / f"head_{tag}.pt")
        torch.save(sd, out)
        info = {"backbone": a.backbone, "kind": a.kind, "use_std": use_std, "layers": Xm.shape[1], "hidden": Xm.shape[2],
                "params": sum(p.numel() for p in h.parameters()), "train_seconds": round(time.time() - t0, 1), "n_windows": int(len(lab)),
                "train_conditions": TRAIN_CONDS}
        out.with_suffix(".json").write_text(json.dumps(info, indent=1))
        print(info)


if __name__ == "__main__":
    main()
