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

log = logging.getLogger("doublespeak.neural")
W_ONNX, W_HF = 1.8, 1.4
_onnx = None
_hf = None


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
    global _hf
    name = os.environ.get("HF_SPOOF_MODEL", "")
    if not name:
        return Tell("neural_hf", "acoustic", 0.5, W_HF, "no HF anti-spoof model configured (HF_SPOOF_MODEL)", applicable=False)
    try:
        import torch
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
    except ImportError:
        return Tell("neural_hf", "acoustic", 0.5, W_HF, "transformers/torch not installed", applicable=False)
    if _hf is None:
        _hf = (AutoFeatureExtractor.from_pretrained(name), AutoModelForAudioClassification.from_pretrained(name).eval())
        log.info("loaded %s (labels %s)", name, _hf[1].config.id2label)
    fe, model = _hf
    with torch.no_grad():
        inputs = fe(x16k, sampling_rate=16_000, return_tensors="pt")
        probs = torch.softmax(model(**inputs).logits, dim=-1)[0].tolist()
    fake_idx = fake_label_index(model.config.id2label)
    if fake_idx is None:
        return Tell("neural_hf", "acoustic", 0.5, W_HF, f"cannot tell which label is synthetic in {model.config.id2label}", applicable=False)
    p_fake = probs[fake_idx]
    return Tell("neural_hf", "acoustic", float(p_fake), W_HF, f"{name.split('/')[-1]}: P(synthetic) = {p_fake:.2f}")


def analyze(x16k: np.ndarray, dur_s: float) -> list[Tell]:
    if dur_s < 3.0:
        return [Tell("neural", "acoustic", 0.5, 1.0, "clip too short for neural voters (< 3 s)", applicable=False)]
    return [onnx_vote(x16k), hf_vote(x16k)]
