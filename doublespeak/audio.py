"""In-memory microphone capture.

Audio is **never** written to disk. Frames are held in a bounded in-memory
ring buffer, handed to the pipeline, and then dropped. This module exposes a
small streaming interface plus a helper to load a clip for offline testing
(again, straight into memory).
"""

from __future__ import annotations

import queue
from collections import deque
from typing import Iterator

import numpy as np

from . import config

try:  # sounddevice is optional at import time so the UI can load without a mic.
    import sounddevice as sd
except Exception:  # pragma: no cover - depends on host audio stack
    sd = None  # type: ignore[assignment]


class MicrophoneStream:
    """Capture mono float32 audio at :data:`config.SAMPLE_RATE`, in memory only.

    Use as a context manager and iterate to receive overlapping analysis
    windows as numpy arrays::

        with MicrophoneStream() as mic:
            for window in mic.windows():
                ...  # window is a float32 array, length = window samples
    """

    def __init__(
        self,
        sample_rate: int = config.SAMPLE_RATE,
        window_seconds: float = config.WINDOW_SECONDS,
        overlap_seconds: float = config.WINDOW_OVERLAP_SECONDS,
        block_seconds: float = 0.5,
    ) -> None:
        if sd is None:
            raise RuntimeError(
                "sounddevice is not available. Install it and ensure a "
                "microphone is present, or use load_wav_in_memory() for testing."
            )
        self.sample_rate = sample_rate
        self.window_samples = int(window_seconds * sample_rate)
        self.hop_samples = int(max(window_seconds - overlap_seconds, 0.1) * sample_rate)
        self.block_samples = int(block_seconds * sample_rate)
        self._q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=64)
        self._buf: deque[float] = deque(maxlen=self.window_samples * 4)
        self._stream: "sd.InputStream | None" = None

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        """sounddevice callback: copy block into the queue (no disk writes)."""
        # indata is float32 (channels last); collapse to mono and copy out.
        mono = indata.mean(axis=1).astype(np.float32, copy=True)
        try:
            self._q.put_nowait(mono)
        except queue.Full:
            # Drop oldest audio under backpressure rather than block the device.
            try:
                self._q.get_nowait()
                self._q.put_nowait(mono)
            except queue.Empty:
                pass

    def __enter__(self) -> "MicrophoneStream":
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.block_samples,
            callback=self._callback,
        )
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        self.close()

    def close(self) -> None:
        """Stop the device and drop any buffered audio from memory."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._buf.clear()
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    def windows(self) -> Iterator[np.ndarray]:
        """Yield overlapping analysis windows as float32 arrays, in memory."""
        pending: list[float] = []
        while True:
            block = self._q.get()  # blocks until audio arrives
            pending.extend(block.tolist())
            while len(pending) >= self.window_samples:
                window = np.asarray(pending[: self.window_samples], dtype=np.float32)
                yield window
                # Advance by the hop, keeping the overlap for the next window.
                del pending[: self.hop_samples]


def load_wav_in_memory(path: str) -> np.ndarray:
    """Load an audio file to a 16 kHz mono float32 array, entirely in memory.

    Intended for offline testing of the pipeline. Uses librosa for decoding and
    resampling. The file on disk is read but nothing is ever written back.
    """
    import librosa

    wav, _ = librosa.load(path, sr=config.SAMPLE_RATE, mono=True)
    return wav.astype(np.float32, copy=False)
