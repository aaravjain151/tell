"""RAM-only ring buffer of mono float32 audio for live streaming sessions (numpy + threading only).

Nothing here touches disk. `wipe()` zeroes the backing array in place and drops the reference, so a later
heap snapshot of this process does not contain the caller's samples. `last()` returns a COPY: a caller that
holds it (the analysis worker) owns that copy; wiping the ring does not and cannot reach it.
"""
from __future__ import annotations

import threading

import numpy as np

SR = 16_000


class Ring:
    def __init__(self, capacity_s: float, sr: int = SR) -> None:
        if capacity_s <= 0:
            raise ValueError("capacity_s must be positive")
        self.sr = sr
        self.capacity = max(1, int(capacity_s * sr))
        self._buf: np.ndarray | None = np.zeros(self.capacity, dtype=np.float32)
        self._head = 0          # next write index
        self._total = 0         # samples ever written (monotonic stream clock)
        self._lock = threading.Lock()

    @property
    def wiped(self) -> bool:
        return self._buf is None

    @property
    def total(self) -> int:
        """Samples ever written; total / sr is the stream clock in seconds."""
        return self._total

    @property
    def available(self) -> int:
        return min(self._total, self.capacity)

    def write(self, x: np.ndarray) -> int:
        """Append samples, overwriting the oldest. Returns how many samples were overwritten or never stored
        (i.e. fell out of the ring) by this write."""
        x = np.asarray(x, dtype=np.float32).ravel()
        n = len(x)
        with self._lock:
            if self._buf is None or n == 0:
                return 0
            lost = max(0, self._total + n - self.capacity) - max(0, self._total - self.capacity)
            if n >= self.capacity:
                self._buf[:] = x[-self.capacity:]
                self._head = 0
            else:
                end = self._head + n
                if end <= self.capacity:
                    self._buf[self._head:end] = x
                else:
                    k = self.capacity - self._head
                    self._buf[self._head:] = x[:k]
                    self._buf[:n - k] = x[k:]
                self._head = end % self.capacity
            self._total += n
            return lost

    def last(self, seconds: float) -> np.ndarray:
        """Copy of the newest `seconds` of audio (fewer if less is buffered; empty after wipe)."""
        with self._lock:
            if self._buf is None:
                return np.zeros(0, dtype=np.float32)
            n = min(int(seconds * self.sr), self.available)
            if n <= 0:
                return np.zeros(0, dtype=np.float32)
            start = (self._head - n) % self.capacity
            if start + n <= self.capacity:
                return self._buf[start:start + n].copy()
            return np.concatenate([self._buf[start:], self._buf[:(start + n) % self.capacity]])

    def wipe(self) -> None:
        """Zero the samples in place, drop the array and reset. Idempotent. The ring is unusable afterwards."""
        with self._lock:
            if self._buf is not None:
                self._buf[:] = 0.0
            self._buf = None
            self._head = 0
