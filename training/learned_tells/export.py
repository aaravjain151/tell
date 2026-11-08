#!/usr/bin/env python3
"""Fit the shipping models on ALL training clips and write services/api/tell/signals/learned_tells.json (+ print its SHA-256).

  python -I training/learned_tells/export.py emb_l2_cal 12      # what ships (docs/LEARNED-TELLS.md)

The file holds two logistic regressions: "full" (the voter: PCA of one Pellav2 backbone layer, logit re-centred on held-in
humans) and "interp" (interpretable voice tells; never votes, only names the tells in the evidence line). Pure JSON numbers; the runtime parses it with `json` and checks the hash.
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
from meaning import meaning_json  # noqa: E402

from tell.signals import tell_features as TF  # noqa: E402

OUT = C.ROOT / "services" / "api" / "tell" / "signals" / "learned_tells.json"


def r(a, nd=6):
    return [round(float(v), nd) for v in np.ravel(a)]


def block(m: E.Model, names: list[str]) -> dict:
    feats = [names[j] for j in m.feat_idx]
    has = len(feats) > 0
    d = {"features": feats, "median": r(m.med) if has else [], "mean": r(m.mu) if has else [], "scale": r(m.sd) if has else [],
         "clip": E.CLIP_STD,
         "coef": r(m.m.coef_[0]), "intercept": float(m.m.intercept_[0]) - float(getattr(m, "offset", 0.0)), "C": m.C,
         "human_offset": float(getattr(m, "offset", 0.0))}
    if m.use_emb:
        d["emb"] = {"layer": m.layer, "k": int(m.pc.shape[0]), "dim": int(m.pc.shape[1]), "mean": r(m.e_mu, 5),
                    "components": [r(row, 5) for row in m.pc], "z_mean": r(m.z_mu), "z_scale": r(m.z_sd)}
    if m.use_neural:
        d["neural"] = {"inputs": ["pella_logit", "hf_logit"][: len(m.n_mu)], "mean": r(m.n_mu), "scale": r(m.n_sd)}
    return d


def main():
    fam = sys.argv[1]
    layer = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    mi, _ = E.fit_final("interp_l2", layer)
    mf, _ = E.fit_final(fam, layer)
    mf.layer = mi.layer = layer
    names = E.D.load("clean", (layer,)).names
    coef = dict(zip([names[j] for j in mi.feat_idx], mi.m.coef_[0]))
    doc = {"format": "tell-learned-tells/1", "version": "2026-11-08.1",
           "trained_on": "LibriSpeech 80 speakers + Sanath + 12 phone memos (human) vs Qwen3-TTS 0.6B clones, Gradium, macOS say; "
                         "conditions clean/opus8k/g711_mulaw8k/speaker_rerecord_sim/opus_lowbitrate_with_loss; see docs/LEARNED-TELLS.md",
           "window": {"seconds": 4.0, "hop": 2.0, "aggregate": "sigmoid(mean window logit)"},
           "models": {"interp": block(mi, names), "full": block(mf, names)},
           "meaning": meaning_json(coef)}
    raw = (json.dumps(doc, separators=(",", ":"), sort_keys=True) + "\n").encode()
    OUT.write_bytes(raw)
    print(OUT, len(raw), "bytes", hashlib.sha256(raw).hexdigest())
    for n, c in sorted(coef.items(), key=lambda kv: -abs(kv[1])):
        print(f"  {n:20s} {c:+.3f}")


if __name__ == "__main__":
    main()
