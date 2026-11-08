"""Neural anti-spoof voter(s). Each returns a Tell toward AI, or applicable=False when the model isn't installed.

Two slots, both local:
  1. ONNX anti-spoof model at ANTI_SPOOF_MODEL (e.g. truncated XLS-R + logistic head exported to ONNX,
     or any model taking float32 [1, T] 16 kHz and returning P(fake)). See tools/neural/README.md.
  2. A Hugging Face transformers checkpoint named in HF_SPOOF_MODEL (e.g. a wav2vec2-based detector)
     loaded with `transformers` + `torch` if installed. Slow on CPU; fine for 10 s clips.

Both are *voters*, never the verdict: scorer.py fuses them with the behavioral tells.
"""
from __future__ import annotations

import logging
import os

import numpy as np

from ..types import Tell
from . import learned, windows
from .pella import pella_vote, pella_vote_ex

log = logging.getLogger("tell.neural")
W_ONNX, W_HF = 1.8, 0.7   # W_HF 1.4 -> 0.7 (2026-11-07.2): ~chance on Qwen3-TTS (AUC 0.55/0.48 alone); kept non-zero so it can still vote
_onnx = None
_hf = None
_hf_error = ""


def onnx_vote(x16k: np.ndarray) -> Tell:
    global _onnx
    path = os.environ.get("ANTI_SPOOF_MODEL", "")
    if not path or not os.path.exists(path):
        return Tell("neural_onnx", "acoustic", 0.5, W_ONNX, "no ONNX anti-spoof model configured (ANTI_SPOOF_MODEL)", applicable=False)
    try:
        import onnxruntime as ort
    except ImportError:
        return Tell("neural_onnx", "acoustic", 0.5, W_ONNX, "onnxruntime not installed", applicable=False)
    if _onnx is None:
        _onnx = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    inp = _onnx.get_inputs()[0].name
    out = _onnx.run(None, {inp: x16k[None, :].astype(np.float32)})[0]
    p_fake = float(np.ravel(out)[-1]) if out.size > 1 else float(np.ravel(out)[0])
    p_fake = min(1.0, max(0.0, p_fake))
    return Tell("neural_onnx", "acoustic", p_fake, W_ONNX, f"anti-spoof model: P(synthetic) = {p_fake:.2f}")


_FAKE_WORDS = {"fake", "spoof", "spoofed", "synthetic", "synth", "ai", "deepfake", "generated"}


def fake_label_index(id2label: dict) -> int | None:
    """Index of the 'synthetic' class, matching whole words so 'bona-fide'/'real'/'fail' never match."""
    import re
    for i, label in id2label.items():
        if set(re.split(r"[^a-z0-9]+", str(label).lower())) & _FAKE_WORDS:
            return int(i)
    return None


def hf_vote(x16k: np.ndarray) -> Tell:
    global _hf, _hf_error
    name = os.environ.get("HF_SPOOF_MODEL", "")
    if not name:
        return Tell("neural_hf", "acoustic", 0.5, W_HF, "no HF anti-spoof model configured (HF_SPOOF_MODEL)", applicable=False)
    try:
        import torch
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
    except ImportError:
        return Tell("neural_hf", "acoustic", 0.5, W_HF, "transformers/torch not installed", applicable=False)
    if _hf is None:
        if _hf_error:
            return Tell("neural_hf", "acoustic", 0.5, W_HF, _hf_error, applicable=False)
        try:
            _hf = (AutoFeatureExtractor.from_pretrained(name, local_files_only=True),   # cache only: no update check, no download at runtime
                   AutoModelForAudioClassification.from_pretrained(name, local_files_only=True).eval())
        except Exception as e:  # noqa: BLE001 - offline + uncached, bad name, corrupt cache: degrade, never raise
            _hf_error = f"{name.split('/')[-1]} not available ({type(e).__name__}); run `make models` while online"
            log.warning("anti-spoof model unavailable: %s", e)
            return Tell("neural_hf", "acoustic", 0.5, W_HF, _hf_error, applicable=False)
        log.info("loaded %s (labels %s)", name, _hf[1].config.id2label)
    fe, model = _hf
    fake_idx = fake_label_index(model.config.id2label)
    if fake_idx is None:
        return Tell("neural_hf", "acoustic", 0.5, W_HF, f"cannot tell which label is synthetic in {model.config.id2label}", applicable=False)

    def prob(chunk: np.ndarray) -> float:
        with torch.no_grad():
            inputs = fe(chunk, sampling_rate=16_000, return_tensors="pt")
            return float(torch.softmax(model(**inputs).logits, dim=-1)[0].tolist()[fake_idx])

    # long calls: a few evenly spaced non-silent windows instead of one huge input (bounds latency and memory)
    ws = windows.windows(x16k, 16_000, win_s=6.0, hop_s=3.0, max_n=3) if len(x16k) > 12 * 16_000 else [(0.0, x16k)]
    chunks = [c for _, c in ws]
    if not chunks:
        return Tell("neural_hf", "acoustic", 0.5, W_HF, "no speech found for the anti-spoof model (all windows silent)", applicable=False)
    ps = [prob(c) for c in chunks]
    p_fake = float(np.mean(ps))
    over = f" over {len(ps)} windows" if len(ps) > 1 else ""
    detail = {"windows": [{"t": round(float(t), 2), "p": round(p, 4)} for (t, _), p in zip(ws, ps)]}
    return Tell("neural_hf", "acoustic", p_fake, W_HF, f"{name.split('/')[-1]}: P(synthetic) = {p_fake:.2f}{over}", detail=detail)


def analyze(x16k: np.ndarray, dur_s: float) -> list[Tell]:
    if dur_s < 3.0:
        return [Tell("neural", "acoustic", 0.5, 1.0, "clip too short for neural voters (< 3 s)", applicable=False)]
    layers = learned.layers_needed()
    if layers:
        pt, extras = pella_vote_ex(x16k, layers)   # one Pellav2 forward also yields the embedding the learned voter reads
    else:
        pt, extras = pella_vote(x16k), None
    out = [onnx_vote(x16k), hf_vote(x16k), pt]
    lt = learned.learned_vote(x16k, extras)        # None when TELL_LEARNED_TELLS is off: nothing is added
    if lt is not None:
        out.append(lt)
    return out
