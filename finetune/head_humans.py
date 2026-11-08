#!/usr/bin/env python3
"""New real HUMAN speakers for the head evaluation (2026-11-07, docs/HEAD-FINETUNE.md "Real phone-recorded humans").

Input: 16 kHz mono WAVs converted (ffmpeg) from the owner's iPhone Voice Memos into the gitignored
data/finetune/humans_new/wild/human/<group>/human__<group>__<n>.wav, plus data/finetune/humans_new/humans_meta.json
(one row per clip: id, group, wav, duration, source SHA-256). The audio is never committed.

  python3 -I finetune/head_humans.py windows          # 4 s windows (hop 4 s, max 4 per clip, as for Sanath) x 8 channel conditions
  python3 -I finetune/head_humans.py features pella   # frozen w2v-BERT 2.0 features + shipped Pellav2 prob (HEAD_DEVICE=cpu by default here)
  python3 -I finetune/head_humans.py features hf      # frozen wav2vec2 features + shipped HF prob
  python3 -I finetune/head_humans.py speakers         # speaker-count ESTIMATE: cosine similarity of mean-pooled SSL layers + agglomerative clustering
  python3 -I finetune/head_humans.py falsealarm       # current voters and the existing head (data/finetune/head_pella_mlp.pt) on these clips

Same windowing, same tools/redteam/degrade.py chains and same feature code as head_extract.py, so the new rows can be
appended to the old cache by head_train_eval.py --extra-humans.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "finetune"))
sys.path.insert(0, str(ROOT / "services" / "api"))
sys.path.insert(0, str(ROOT / "tools" / "redteam"))
FT = ROOT / "data" / "finetune"
HN = FT / "humans_new"
SR, WIN = 16_000, 64_000


def build_windows() -> None:
    from concurrent.futures import ProcessPoolExecutor

    import head_extract as he
    from doublespeak.signals import windows as win
    meta = json.loads((HN / "humans_meta.json").read_text())
    items = []
    for r in meta:
        x = he._read(str(HN / r["wav"]))
        for k, (t, c) in enumerate(win.windows(x, SR, win_s=4.0, hop_s=4.0, max_n=4)):
            if len(c) == WIN:
                items.append(({"id": r["id"], "path": r["wav"], "label": 0, "generator": "human", "speaker": f"new_{r['group']}",
                               "split": "humans_new", "source_sha256": r["source_sha256"], "clip": r["id"], "win": k, "owner": 0,
                               "group": r["group"]}, c.astype(np.float32)))
    rows = [m for m, _ in items]
    for i, m in enumerate(rows):
        m["wid"] = i
    with open(HN / "windows.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    X = [c for _, c in items]
    print(len(X), "windows from", len(meta), "clips", flush=True)
    with ProcessPoolExecutor(max_workers=2) as ex:
        for cond in he.CONDS:
            out = list(ex.map(he._degrade_one, [(cond, c) for c in X], chunksize=4))
            np.save(HN / f"win_{cond}.npy", (np.clip(np.stack(out), -1, 1) * 32767).astype(np.int16))
            print(cond, "ok", flush=True)


def features(which: str) -> None:
    import head_extract as he
    os.environ.setdefault("HEAD_DEVICE", "cpu")      # the engine on :8000 owns MPS
    he.FT = HN
    he.extract(which)


# --------------------------------------------------------------------------------------------- speaker-count estimate
def _clip_embed(F, meta, layer):
    """Mean over a clip's clean windows of the time-mean hidden state at `layer`."""
    clips = sorted({m["clip"] for m in meta}, key=lambda c: [m["clip"] for m in meta].index(c))
    E = np.stack([F["mean"][[i for i, m in enumerate(meta) if m["clip"] == c], layer].astype(np.float32).mean(0) for c in clips])
    return clips, E


def _cos(E, center):
    E = E - center
    E = E / np.linalg.norm(E, axis=1, keepdims=True)
    return E @ E.T


def _verif_eer(S, spk):
    """EER of same-vs-different speaker on a cosine matrix (upper triangle)."""
    iu = np.triu_indices(len(spk), 1)
    same = (spk[:, None] == spk[None, :])[iu]
    s = S[iu]
    from sklearn.metrics import roc_curve
    fpr, tpr, thr = roc_curve(same, s)
    i = int(np.nanargmin(np.abs((1 - tpr) - fpr)))
    return float((fpr[i] + 1 - tpr[i]) / 2), float(thr[i])


def speakers() -> None:
    """Pick the layer on LibriSpeech (80 known speakers, old cache), calibrate a same-speaker cosine threshold there,
    then cluster the 12 new clips. Everything printed is an ESTIMATE: read speech vs. phone memos, and same-text pairs
    (the owner used shared scripts) push similarity up for different speakers."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    out = {}
    for bb in ("pella", "hf"):
        old_meta = list(csv.DictReader(open(FT / "windows.csv")))
        Fo = np.load(FT / f"feat_{bb}_clean.npz")
        li = [i for i, m in enumerate(old_meta) if m["label"] == "0" and m["split"] != "repo"]   # LibriSpeech reals, one window per utterance
        spk = np.array([old_meta[i]["speaker"] for i in li])
        L = Fo["mean"].shape[1]
        per_layer = {}
        for layer in range(L):
            E = Fo["mean"][li, layer].astype(np.float32)
            per_layer[layer] = _verif_eer(_cos(E, E.mean(0)), spk)
        best = min(per_layer, key=lambda k: per_layer[k][0])
        eer, thr = per_layer[best]
        new_meta = list(csv.DictReader(open(HN / "windows.csv")))
        Fn = np.load(HN / f"feat_{bb}_clean.npz")
        clips, En = _clip_embed(Fn, new_meta, best)
        center = Fo["mean"][li, best].astype(np.float32).mean(0)            # LibriSpeech mean, so the 12 clips do not centre themselves
        S = _cos(En, center)
        S_self = _cos(En, En.mean(0))
        D = np.clip(1 - S_self, 0, None)
        np.fill_diagonal(D, 0)
        Z = linkage(squareform(D, checks=False), "average")
        cuts = {}
        for k in range(1, 9):
            lab = fcluster(Z, k, "maxclust")
            cuts[k] = [int(v) for v in lab]
        # silhouette for k = 2..8 on the self-centred matrix (the best-guess k)
        from sklearn.metrics import silhouette_score
        sil = {k: float(silhouette_score(D, cuts[k], metric="precomputed")) for k in range(2, 9) if len(set(cuts[k])) > 1}
        k_best = max(sil, key=sil.get)
        # threshold cut: clips above the LibriSpeech EER threshold (LibriSpeech-centred cosine) are 'same speaker'
        Zt = linkage(squareform(np.clip(1 - S, 0, None) * (1 - np.eye(len(S))), checks=False), "average")
        lab_thr = [int(v) for v in fcluster(Zt, 1 - thr, "distance")]
        out[bb] = {"layer": best, "librispeech_verif_eer": round(eer, 3), "librispeech_eer_threshold": round(thr, 3),
                   "clips": clips, "cos_librispeech_centred": np.round(S, 2).tolist(), "cos_self_centred": np.round(S_self, 2).tolist(),
                   "silhouette": {k: round(v, 3) for k, v in sil.items()}, "k_best_silhouette": k_best, "clusters_k_best": cuts[k_best],
                   "clusters_threshold": lab_thr, "n_clusters_threshold": len(set(lab_thr))}
        print(f"\n[{bb}] layer {best}: LibriSpeech speaker-verif EER {eer:.3f} at cosine {thr:.2f}")
        print("      " + " ".join(f"{c:>6}" for c in clips))
        for c, row in zip(clips, S):
            print(f"{c:>6} " + " ".join(f"{v:6.2f}" for v in row))
        print("silhouette", out[bb]["silhouette"], "-> k", k_best, dict(zip(clips, cuts[k_best])))
        print("threshold cut:", len(set(lab_thr)), "clusters", dict(zip(clips, lab_thr)))
    (HN / "speakers.json").write_text(json.dumps(out, indent=1))


# --------------------------------------------------------------------------------------------- false alarms on the new humans
def falsealarm() -> None:
    import torch

    import head_train_eval as hte
    meta = list(csv.DictReader(open(HN / "windows.csv")))
    old_meta = list(csv.DictReader(open(FT / "windows.csv")))
    res = {}
    head = None
    if (FT / "head_pella_mlp.pt").exists():
        info = json.loads((FT / "head_pella_mlp.json").read_text())
        head = hte.build_head(info["layers"], info["hidden"], info["kind"], info["use_std"])
        head.load_state_dict(torch.load(FT / "head_pella_mlp.pt", map_location="cpu", weights_only=True))
        head.eval()
    old_real = np.array([m["label"] == "0" for m in old_meta])
    for cond in hte.EVAL_CONDS:
        Fp = np.load(HN / f"feat_pella_{cond}.npz")
        Fh = np.load(HN / f"feat_hf_{cond}.npz")
        Fo_p = np.load(FT / f"feat_pella_{cond}.npz")
        Fo_h = np.load(FT / f"feat_hf_{cond}.npz")
        scores = {"pella_now": Fp["p_current"], "hf_now": Fh["p_current"]}
        # operating point = threshold giving 5% FPR on the OLD real windows (LibriSpeech + Sanath) in the same condition
        ops = {"pella_now": float(np.quantile(Fo_p["p_current"][old_real], 0.95)), "hf_now": float(np.quantile(Fo_h["p_current"][old_real], 0.95))}
        if head is not None:
            scores["head_old"] = hte.predict(head, Fp["mean"], Fp["std"])
            ops["head_old"] = float(np.quantile(hte.predict(head, Fo_p["mean"][old_real], Fo_p["std"][old_real]), 0.95))   # in-sample for the final head
        clips = np.array([m["clip"] for m in meta])
        grp = np.array([m["group"] for m in meta])
        res[cond] = {}
        for name, s in scores.items():
            s = np.asarray(s, float)
            per_clip = {c: float(s[clips == c].mean()) for c in dict.fromkeys(clips)}
            res[cond][name] = {"n_windows": int(len(s)), "n_clips": len(per_clip), "fa_win_0.5": float((s >= 0.5).mean()),
                               "fa_clip_0.5": float(np.mean([v >= 0.5 for v in per_clip.values()])), "op_fpr5_old": ops[name],
                               "fa_win_op": float((s >= ops[name]).mean()), "fa_clip_op": float(np.mean([v >= ops[name] for v in per_clip.values()])),
                               "mean": float(s.mean()), "max_clip": float(max(per_clip.values())),
                               "by_group": {g: {"n_win": int((grp == g).sum()), "fa_win_0.5": float((s[grp == g] >= 0.5).mean())} for g in sorted(set(grp))},
                               "per_clip": per_clip}
    (HN / "falsealarm.json").write_text(json.dumps(res, indent=1))
    for cond, d in res.items():
        print(cond, {k: (v["n_windows"], round(v["fa_win_0.5"], 2), round(v["fa_clip_0.5"], 2), round(v["op_fpr5_old"], 3), round(v["fa_win_op"], 2), round(v["max_clip"], 2)) for k, v in d.items()})


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "windows":
        build_windows()
    elif cmd == "features":
        features(sys.argv[2])
    elif cmd == "speakers":
        speakers()
    elif cmd == "falsealarm":
        falsealarm()
