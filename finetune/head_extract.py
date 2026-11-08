#!/usr/bin/env python3
"""Step 2: cut 4 s windows from every source clip, apply IDENTICAL channel chains to both classes, cache frozen-backbone features.

  python3 finetune/head_extract.py windows            # CPU, parallel: data/finetune/win_<condition>.npy (int16) + windows.csv
  python3 finetune/head_extract.py features pella     # frozen w2v-BERT 2.0 (the shipped Pellav2 backbone), device MPS/CPU
  python3 finetune/head_extract.py features hf        # frozen wav2vec2 (the shipped HF voter's backbone)

Per window and condition the cache holds, for every hidden layer, the masked time MEAN and STD of the hidden states
([L+1, D] each, float16) plus the CURRENT voter's own probability on that exact window (so the baseline needs no second pass
and is byte-for-byte what the shipped voter computes on that window: Pellav2 = softmax-weighted layer mean -> linear head;
HF = the checkpoint's classification head).

Degradation is tools/redteam/degrade.py (PR #72) applied to the 4 s window itself, same function and seeds for every class.
"""
from __future__ import annotations

import csv
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FT = ROOT / "data" / "finetune"
sys.path.insert(0, str(ROOT / "services" / "api"))
sys.path.insert(0, str(ROOT / "tools" / "redteam"))
SR, WIN = 16_000, 64_000
CONDS = ["clean", "opus8k", "g711_mulaw8k", "g711_alaw8k", "opus_lowbitrate_with_loss", "speaker_rerecord_sim", "chain_pstn_voip", "chain_replay_call"]
OWNER = {"owner_rough_morning": "/Users/aarav/Downloads/data_calls_qwen3tts_rough_morning.wav",
         "owner_long_tech_scam": "/Users/aarav/Downloads/data_calls_qwen3tts_long_tech_scam.wav"}


def _read(p: str) -> np.ndarray:
    import degrade
    return degrade.read_wav(Path(p))


def _degrade_one(args):
    cond, x = args
    if cond == "clean":
        return x
    import degrade
    y = degrade.CONDITIONS[cond][0](x)
    y = y[:WIN] if len(y) >= WIN else np.concatenate([y, np.zeros(WIN - len(y), np.float32)])
    return y.astype(np.float32)


def build_windows() -> None:
    from tell.signals import windows as win
    rows = list(csv.DictReader(open(FT / "sources.csv")))
    items = []   # (meta dict, window)
    for r in rows:
        x = _read(str(FT / r["path"]))
        long_repo = r["split"] == "repo" or r["split"] == "local" and r["generator"] == "say"
        ws = win.windows(x, SR, win_s=4.0, hop_s=4.0, max_n=4 if long_repo else 1)
        for k, (t, c) in enumerate(ws):
            if len(c) == WIN:
                items.append(({**r, "clip": r["id"], "win": k, "owner": 0}, c.astype(np.float32)))
    for name, p in OWNER.items():
        x = _read(p)
        for k, (t, c) in enumerate(win.windows(x, SR, win_s=4.0, hop_s=2.0, max_n=3)):   # exactly the production windowing
            items.append(({"id": name, "path": p, "label": 1, "generator": "qwen", "speaker": "owner", "split": "owner", "source_sha256": "",
                           "clip": name, "win": k, "owner": 1}, c.astype(np.float32)))
    # one-time: drop near-silent or clipped-short windows already handled by windows(); write meta
    meta = [m for m, _ in items]
    for i, m in enumerate(meta):
        m["wid"] = i
    with open(FT / "windows.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(meta[0]))
        w.writeheader()
        w.writerows(meta)
    X = [c for _, c in items]
    print(len(items), "windows;", sum(int(m["label"]) for m in meta), "fake", flush=True)
    with ProcessPoolExecutor(max_workers=4) as ex:
        for cond in CONDS:
            t0 = time.time()
            out = list(ex.map(_degrade_one, [(cond, c) for c in X], chunksize=16))
            arr = (np.clip(np.stack(out), -1, 1) * 32767).astype(np.int16)
            np.save(FT / f"win_{cond}.npy", arr)
            print(cond, arr.shape, f"{time.time() - t0:.0f}s", flush=True)


# ------------------------------------------------------------------------------------------- feature extraction
def _pool(hs, mask):
    import torch
    m = mask[:, :, None].float()
    n = m.sum(1).clamp(min=1)
    st = torch.stack(hs, 1)                                  # B, L, T, D
    mean = (st * m[:, None]).sum(2) / n[:, None]
    var = (((st - mean[:, :, None]) ** 2) * m[:, None]).sum(2) / n[:, None]
    return mean, var.clamp(min=0).sqrt()


def extract(which: str) -> None:
    import torch
    dev = os.environ.get("HEAD_DEVICE", "mps" if torch.backends.mps.is_available() else "cpu")
    bs = int(os.environ.get("HEAD_BATCH", "8"))
    if which == "pella":
        from tell.signals import pella
        os.environ.setdefault("PELLA_MODEL", str(pella.weights_path() or ""))
        os.environ["PELLA_DEVICE"] = dev
        pella._load()
        assert pella._model is not None, pella._error
        m = pella._model

        def run(x):                                           # x: [B, 64000] float32 raw window
            wav = torch.from_numpy(np.stack([pella.prep(c) for c in x])).to(dev)
            feats, mask = m.features(wav)
            hs = m.backbone(input_features=feats, attention_mask=mask, output_hidden_states=True).hidden_states
            mean, std = _pool(hs, mask)
            w = torch.softmax(m.layer_weights, 0)
            logit = m.head((mean * w[None, :, None]).sum(1)).squeeze(-1)
            return mean, std, torch.sigmoid(logit)
    else:
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
        name = "garystafford/wav2vec2-deepfake-voice-detector"
        fe = AutoFeatureExtractor.from_pretrained(name, local_files_only=True)
        m = AutoModelForAudioClassification.from_pretrained(name, local_files_only=True).eval().to(dev)
        from tell.signals.neural import fake_label_index
        fi = fake_label_index(m.config.id2label)

        def run(x):
            inp = fe(list(x), sampling_rate=SR, return_tensors="pt", padding=True)
            o = m(input_values=inp["input_values"].to(dev), output_hidden_states=True)
            hs = o.hidden_states
            mask = torch.ones(hs[0].shape[:2], device=dev)
            mean, std = _pool(hs, mask)
            return mean, std, torch.softmax(o.logits, -1)[:, fi]

    for cond in CONDS:
        outp = FT / f"feat_{which}_{cond}.npz"
        if outp.exists():
            continue
        A = np.load(FT / f"win_{cond}.npy")
        M, S, P = [], [], []
        t0 = time.time()
        for i in range(0, len(A), bs):
            x = A[i:i + bs].astype(np.float32) / 32767.0
            with torch.no_grad():
                mean, std, p = run(x)
            M.append(mean.float().cpu().numpy().astype(np.float16))
            S.append(std.float().cpu().numpy().astype(np.float16))
            P.append(p.float().cpu().numpy())
            if (i // bs) % 25 == 0:
                print(which, cond, i, len(A), f"{time.time() - t0:.0f}s", flush=True)
        np.savez(outp, mean=np.concatenate(M), std=np.concatenate(S), p_current=np.concatenate(P))
        print(which, cond, "done", f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "windows":
        build_windows()
    else:
        extract(sys.argv[2])
