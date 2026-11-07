"""Speech-to-text with faster-whisper (base, int8, CPU, VAD).

Runs entirely locally. Transcription is done directly on the in-memory audio
array; no temporary WAV files are written. Transcripts live only in memory and
are discarded by the caller after analysis.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import config
from .config import WhisperConfig


@dataclass
class Transcript:
    """Result of transcribing one window."""

    text: str
    language: str
    #: Mean no-speech probability across segments (0-1). High => likely silence.
    no_speech_probability: float


class Transcriber:
    """Thin wrapper around :class:`faster_whisper.WhisperModel`.

    The model is loaded lazily on first use so importing this module (e.g. for
    the Streamlit UI) stays cheap.
    """

    def __init__(self, cfg: WhisperConfig = config.WHISPER) -> None:
        self.cfg = cfg
        self._model = None  # loaded lazily

    def _ensure_model(self):
        """Load the WhisperModel once, preferring a local offline directory."""
        if self._model is not None:
            return self._model
        from faster_whisper import WhisperModel

        # Prefer an explicit local CTranslate2 directory; otherwise use the model
        # name, which faster-whisper resolves from its offline cache.
        model_ref = (
            str(self.cfg.local_model_dir)
            if self.cfg.local_model_dir is not None
            else self.cfg.model_size
        )
        self._model = WhisperModel(
            model_ref,
            device=self.cfg.device,
            compute_type=self.cfg.compute_type,
        )
        return self._model

    def transcribe(self, audio: np.ndarray) -> Transcript:
        """Transcribe a 16 kHz mono float32 array held in memory.

        Returns an empty transcript (rather than raising) when the clip has no
        detectable speech. With ``vad_filter`` on, faster-whisper can strip the
        entire clip to silence; its internal language detection then fails on an
        empty sequence. We treat that as "no speech", which is the correct
        signal for a silent or speechless window.
        """
        model = self._ensure_model()
        # faster-whisper accepts a float32 numpy array directly (no temp file).
        try:
            segments, info = model.transcribe(
                audio.astype(np.float32, copy=False),
                beam_size=self.cfg.beam_size,
                vad_filter=self.cfg.vad_filter,
                language=None,
            )
        except ValueError:
            # No speech survived VAD -> nothing to transcribe.
            return Transcript(text="", language="", no_speech_probability=1.0)
        texts: list[str] = []
        no_speech: list[float] = []
        try:
            for seg in segments:
                texts.append(seg.text.strip())
                # Attribute name is stable in faster-whisper's Segment.
                no_speech.append(float(getattr(seg, "no_speech_prob", 0.0)))
        except ValueError:
            # Generator can raise mid-iteration when VAD removed all speech.
            return Transcript(text="", language="", no_speech_probability=1.0)
        mean_no_speech = float(np.mean(no_speech)) if no_speech else 1.0
        return Transcript(
            text=" ".join(t for t in texts if t).strip(),
            language=getattr(info, "language", "") or "",
            no_speech_probability=mean_no_speech,
        )
