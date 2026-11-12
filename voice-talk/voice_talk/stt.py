"""Speech input: energy-based utterance segmenter + faster-whisper transcriber."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np

SR = 16000


class Transcriber(Protocol):
    def transcribe(self, audio: np.ndarray, language: str) -> str: ...


class MicSegmenter:
    """Splits a 16 kHz mono int16 stream into utterances on pauses (open mic),
    or collects everything until finish() (push to talk)."""

    def __init__(self, mode: str = "open", silence_ms: int = 600, min_speech_ms: int = 250,
                 max_utterance_s: float = 25.0, threshold: float = 0.015):
        assert mode in ("open", "ptt")
        self.mode, self.threshold = mode, threshold
        self.silence_n = int(SR * silence_ms / 1000)
        self.min_speech_n = int(SR * min_speech_ms / 1000)
        self.max_n = int(SR * max_utterance_s)
        self._buf: list[np.ndarray] = []
        self._len = 0
        self._speech = 0
        self._trailing_silence = 0

    def feed(self, pcm16: bytes) -> list[np.ndarray]:
        x = np.frombuffer(pcm16[: len(pcm16) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
        if x.size == 0:
            return []
        if self.mode == "ptt":
            self._buf.append(x)
            self._len += x.size
            return []
        loud = float(np.sqrt((x ** 2).mean())) > self.threshold
        if not loud and self._len == 0:
            return []  # still waiting for speech to start
        self._buf.append(x)
        self._len += x.size
        if loud:
            self._speech += x.size
            self._trailing_silence = 0
        else:
            self._trailing_silence += x.size
        if self._trailing_silence >= self.silence_n or self._len >= self.max_n:
            return self._take()
        return []

    def finish(self) -> list[np.ndarray]:
        return self._take()

    def _take(self) -> list[np.ndarray]:
        if self._len == 0:
            return []
        audio = np.concatenate(self._buf)
        enough = self.mode == "ptt" or self._speech >= self.min_speech_n
        self._buf, self._len, self._speech, self._trailing_silence = [], 0, 0, 0
        return [audio] if enough else []


class FasterWhisperSTT:
    def __init__(self, models_dir: Path):
        self.models_dir = Path(models_dir)
        self._models: dict[str, object] = {}

    def _model_for(self, language: str):
        # English: prefer the fastest local model (tiny.en -> base.en), else the
        # multilingual small model. tiny.en is ~2x faster than base.en on CPU and
        # is accurate enough for short conversational turns.
        if language == "en":
            name = next(
                (n for n in ("whisper-tiny.en", "whisper-base.en")
                 if (self.models_dir / n).exists()),
                "whisper-small",
            )
        else:
            name = "whisper-small"
        path = self.models_dir / name
        if not path.exists():
            hint = "--whisper small" if name.endswith("small") else (
                "--whisper tiny.en" if name.endswith("tiny.en") else "--whisper base.en")
            raise FileNotFoundError(f"speech model {name} missing; run: python setup_models.py {hint}")
        if name not in self._models:
            from faster_whisper import WhisperModel
            self._models[name] = WhisperModel(str(path), device="cpu", compute_type="int8")
        return self._models[name], name

    def transcribe(self, audio: np.ndarray, language: str) -> str:
        model, name = self._model_for(language)
        kw = {} if name.endswith(".en") else {"language": language}
        segs, _ = model.transcribe(audio, beam_size=1, condition_on_previous_text=False, **kw)
        return " ".join(s.text.strip() for s in segs).strip()
