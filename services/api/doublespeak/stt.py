"""Local speech-to-text for the caller's audio. Never a cloud API — caller audio stays on the device.

Provider order: faster-whisper (CTranslate2, CPU-friendly) → whisper (openai-whisper) → none.
Install one on the laptop:  pip install faster-whisper   (first run downloads the model to ~/.cache)
"""
from __future__ import annotations

import logging
import os

import numpy as np

log = logging.getLogger("doublespeak.stt")
_model = None


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def transcribe(x16k: np.ndarray) -> str | None:
    """x16k: float32 mono at 16 kHz. Returns text or None if no local STT is installed."""
    global _model
    if not available():
        return None
    from faster_whisper import WhisperModel
    if _model is None:
        size = os.environ.get("DOUBLESPEAK_WHISPER_MODEL", "base.en")
        _model = WhisperModel(size, device="cpu", compute_type="int8")
        log.info("loaded faster-whisper %s", size)
    segments, _ = _model.transcribe(x16k, beam_size=1, vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()
