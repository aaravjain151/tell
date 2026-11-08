#!/usr/bin/env python3
"""Learned-tells feature cache. Run with `python -I` (reads downloaded audio). Writes only to LT_DIR.

  python -I training/learned_tells/extract.py sources        # LT_DIR/sources.csv
  python -I training/learned_tells/extract.py audio          # every clip x condition through tools/redteam/degrade.py
  python -I training/learned_tells/extract.py neural [cond]  # Pellav2 on EVERY 4 s / 2 s-hop window (prob + 25 layer means),
                                                             #   HF voter per window and per clip (production windows)
  python -I training/learned_tells/extract.py feats [cond]   # interpretable tells per window (tell/signals/tell_features.py)
                                                             #   + the current engine's acoustic tells per clip
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

SR = 16_000


# ------------------------------------------------------------------------------------------------ audio
def _one(args):
    path, cond = args
    import degrade
    x = degrade.read_wav(Path(path))
    if cond != "clean":
        x = degrade.CONDITIONS[cond][0](x)
    return (np.clip(np.asarray(x, np.float32), -1, 1) * 32767).astype(np.int16)


def audio(conds=None) -> None:
    rows = C.read_sources()
    with ProcessPoolExecutor(max_workers=12) as ex:
        for cond in conds or C.ALL_CONDS:
            out = C.LT / f"audio_{cond}.npz"
            if out.exists():
                continue
            t0 = time.time()
            xs = list(ex.map(_one, [(r["path"], cond) for r in rows], chunksize=4))
            off = np.cumsum([0] + [len(x) for x in xs])
            np.savez(out, pcm=np.concatenate(xs), off=off)
            print(cond, len(xs), "clips", f"{off[-1] / SR / 3600:.2f} h", f"{time.time() - t0:.0f}s", flush=True)


def load_audio(cond: str) -> list[np.ndarray]:
    z = np.load(C.LT / f"audio_{cond}.npz")
    pcm, off = z["pcm"], z["off"]
    return [pcm[off[i]:off[i + 1]].astype(np.float32) / 32767.0 for i in range(len(off) - 1)]


def clip_windows(x: np.ndarray) -> list[tuple[float, np.ndarray]]:
    """The production windowing (signals/windows.py, 4 s, 2 s hop, silence skipped) with NO cap: every window."""
    from tell.signals import windows as win
    return win.windows(x, SR, win_s=4.0, hop_s=2.0, max_n=10 ** 9)


# ------------------------------------------------------------------------------------------------ neural
def neural(conds=None) -> None:
    import torch
    from tell.signals import pella
    os.environ.setdefault("PELLA_MODEL", pella.REPO)
    os.environ["PELLA_DEVICE"] = os.environ.get("LT_DEVICE", "mps")
    pella._load()
    assert pella._model is not None, pella._error
    m, dev = pella._model, pella._device
    from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
    from tell.signals.neural import fake_label_index
    name = "garystafford/wav2vec2-deepfake-voice-detector"
    fe = AutoFeatureExtractor.from_pretrained(name, local_files_only=True)
    hf = AutoModelForAudioClassification.from_pretrained(name, local_files_only=True).eval().to(dev)
    fi = fake_label_index(hf.config.id2label)

    def pella_run(chunks):
        wav = torch.from_numpy(np.stack([pella.prep(c) for c in chunks])).to(dev)
        feats, mask = m.features(wav)
        hs = m.backbone(input_features=feats, attention_mask=mask, output_hidden_states=True).hidden_states
        mk = mask[:, :, None].float()
        means = torch.stack([(h * mk).sum(1) / mk.sum(1).clamp(min=1) for h in hs], 1)      # B, L+1, D
        w = torch.softmax(m.layer_weights, 0)
        logit = m.head((means * w[None, :, None]).sum(1)).squeeze(-1)
        return logit.float().cpu().numpy(), means.float().cpu().numpy().astype(np.float16)

    def hf_prob(chunk):
        inp = fe(chunk, sampling_rate=SR, return_tensors="pt")
        return float(torch.softmax(hf(input_values=inp["input_values"].to(dev)).logits, -1)[0, fi])

    for cond in conds or C.ALL_CONDS:
        out = C.LT / f"neural_{cond}.npz"
        if out.exists():
            continue
        xs = load_audio(cond)
        t0 = time.time()
        CI, T, PL, E, H, HP = [], [], [], [], [], []
        batch, meta = [], []

        def flush():
            if not batch:
                return
            with torch.no_grad():
                lg, em = pella_run(batch)
                hp = [hf_prob(c) for c in batch]
            PL.extend(lg.tolist()); E.append(em); H.extend(hp)
            for ci, t in meta:
                CI.append(ci); T.append(t)
            batch.clear(); meta.clear()

        for i, x in enumerate(xs):
            for t, c in clip_windows(x):
                batch.append(c); meta.append((i, t))
                if len(batch) == 8:
                    flush()
            # production HF vote: 6 s / 3 s windows (max 3) when the clip is longer than 12 s, else the whole clip
            from tell.signals import windows as win
            ws = win.windows(x, SR, win_s=6.0, hop_s=3.0, max_n=3) if len(x) > 12 * SR else ([(0.0, x)] if len(x) else [])
            with torch.no_grad():
                HP.append(float(np.mean([hf_prob(c) for _, c in ws])) if ws else np.nan)
            if i % 100 == 0:
                print(cond, i, len(xs), f"{time.time() - t0:.0f}s", flush=True)
        flush()
        np.savez(out, clip=np.array(CI), t=np.array(T, np.float32), pella_logit=np.array(PL, np.float32),
                 emb=np.concatenate(E), hf_p=np.array(H, np.float32), hf_prod=np.array(HP, np.float32))
        print(cond, "done", len(CI), "windows", f"{time.time() - t0:.0f}s", flush=True)


# ------------------------------------------------------------------------------------------------ interpretable features
def _feat_clip(args):
    x, = args
    from tell.signals import acoustic, tell_features as TF
    wins = clip_windows(x)
    F = [TF.window_features(c) for _, c in wins]
    tl, ctx = acoustic.analyze(x, int(1000 * len(x) / SR))
    cur = {t.name: (t.score if t.applicable else np.nan) for t in tl}
    return F, [t for t, _ in wins], cur, ctx


def feats(conds=None) -> None:
    from tell.signals import tell_features as TF
    names = TF.FEATURE_NAMES
    for cond in conds or C.ALL_CONDS:
        out = C.LT / f"feats_{cond}.npz"
        if out.exists() and not os.environ.get("LT_FORCE"):
            continue
        xs = load_audio(cond)
        t0 = time.time()
        with ProcessPoolExecutor(max_workers=14) as ex:
            res = list(ex.map(_feat_clip, [(x,) for x in xs], chunksize=4))
        CI, T, X = [], [], []
        cur_names = ["pause_regularity", "breath_proxy", "pitch_stability", "noise_floor"]
        CUR = np.full((len(xs), len(cur_names)), np.nan, np.float32)
        HB = np.full(len(xs), np.nan, np.float32)
        BL = np.zeros(len(xs), bool)
        for i, (F, ts, cur, ctx) in enumerate(res):
            for f, t in zip(F, ts):
                CI.append(i); T.append(t); X.append([f[n] for n in names])
            for j, n in enumerate(cur_names):
                CUR[i, j] = cur.get(n, np.nan)
            HB[i] = ctx.get("high_band_ratio", np.nan)
            BL[i] = bool(ctx.get("band_limited", False))
        np.savez(out, clip=np.array(CI), t=np.array(T, np.float32), X=np.array(X, np.float32), names=np.array(names),
                 cur=CUR, cur_names=np.array(cur_names), high_band_ratio=HB, band_limited=BL)
        print(cond, "feats done", len(CI), "windows", f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1]
    conds = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    if cmd == "sources":
        rows = C.write_sources()
        from collections import Counter
        print(len(rows), Counter((r["generator"], r["role"]) for r in rows))
    elif cmd == "audio":
        audio(conds)
    elif cmd == "neural":
        neural(conds)
    elif cmd == "feats":
        feats(conds)
