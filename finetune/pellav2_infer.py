"""Local stand-in for the model author's ``pellav2_infer.py``.

The reference fine-tuning scripts import ``Detector`` and ``load_clip`` from
``pellav2_infer``. The official file from the model page
(https://huggingface.co/Sadanie/pellav2-audio-deepfake-detector) can be dropped
in here to replace this shim; the API below matches it exactly, so the scripts
work either way, and the fine-tuned ``.pt`` stays drop-in compatible with the
official inference script.

This shim reuses DoubleSpeak's already-ported, verified implementation
(``doublespeak.deepfake``) so the pipeline runs offline right now. Importing it
pulls in the offline guard via the ``doublespeak`` package, which is fine for
feature extraction and training (both run offline).

Exposes:
  * ``Detector``  - nn.Module: w2v-bert-2.0 backbone + layer_weights + head,
                    with ``.features(wav)`` and ``.forward(wav)`` identical to
                    the reference.
  * ``load_clip(path)`` - read any audio to a 16 kHz mono float32 array with
                    pellav2's preprocessing (4 s centre crop, DC removal,
                    20 Hz high-pass, -23 LUFS, pad) applied.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

# Allow import whether run from repo root or finetune/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doublespeak import config  # noqa: E402  (applies offline guard)
from doublespeak.deepfake import _build_detector_class, _preprocess  # noqa: E402

_SR = config.SAMPLE_RATE

# The reference exposes ``Detector`` as a class; ours is produced by a factory
# so torch is imported lazily. Build it at import time (torch is available in
# the training environment).
Detector = _build_detector_class()


def load_clip(path: str) -> np.ndarray:
    """Load ``path`` to a 16 kHz mono float32 array with pellav2 preprocessing.

    Mirrors the reference ``load_clip``: decode -> mono -> 16 kHz -> the exact
    ``_preprocess`` pipeline (4 s centre crop, -23 LUFS, 20 Hz HPF, pad).
    Returns a float32 array of exactly ``crop_seconds * 16000`` samples.
    """
    import librosa

    wav, _ = librosa.load(str(path), sr=_SR, mono=True)
    return _preprocess(wav.astype(np.float32), config.DEEPFAKE)
