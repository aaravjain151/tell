"""Local speech-to-text for the caller's audio. Never a cloud API — caller audio stays on the device.

Provider order (DOUBLESPEAK_STT=auto, default): VoiceStudio on loopback (OpenAI-style
POST {VOICESTUDIO_URL|http://127.0.0.1:3900}/v1/audio/transcriptions, via doublespeak/localhost.py only, D-009)
→ in-process faster-whisper → none. DOUBLESPEAK_STT=voicestudio|whisper forces one. Any failure falls back silently.
VoiceStudio is AGPL-3.0: used over HTTP only. Install whisper:  pip install faster-whisper
"""
from __future__ import annotations

import io
import logging
import os
import wave

import numpy as np

from . import localhost

log = logging.getLogger("doublespeak.stt")
_model = None


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def to_wav(x16k: np.ndarray, sr: int = 16_000) -> bytes:
    """float32 mono -> 16-bit PCM WAV bytes (stdlib `wave`), held in memory only."""
    pcm = (np.clip(np.asarray(x16k, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _voicestudio(x16k: np.ndarray, opener=None) -> str | None:
    base = os.environ.get("VOICESTUDIO_URL", "http://127.0.0.1:3900").rstrip("/")
    try:
        resp = localhost.post_multipart(base + "/v1/audio/transcriptions", {"model": "whisper-1", "response_format": "json"},
                                        "file", "clip.wav", to_wav(x16k),
                                        timeout=float(os.environ.get("VOICESTUDIO_TIMEOUT_S", "3")), opener=opener)
    except Exception as e:  # noqa: BLE001 - unreachable, refused, timeout, bad JSON: fall back silently
        log.info("voicestudio unavailable: %s", e)
        return None
    text = resp.get("text") if isinstance(resp, dict) else None
    return text.strip() if isinstance(text, str) and text.strip() else None


def transcribe_with_source(x16k: np.ndarray, opener=None) -> tuple[str | None, str | None]:
    """Returns (text, source) with source in {"local_voicestudio", "local_whisper"}, or (None, None)."""
    mode = os.environ.get("DOUBLESPEAK_STT", "auto").lower()
    if mode in ("auto", "voicestudio"):
        text = _voicestudio(x16k, opener)
        if text:
            return text, "local_voicestudio"
        if mode == "voicestudio":
            return None, None
    text = transcribe(x16k)
    return (text, "local_whisper") if text else (None, None)


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
