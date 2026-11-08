"""Rolling-window helper for neural voters (idea ported from teammate branch sam_dev1: 4 s windows, 2 s hop, skip silence).

A long call is scored as a few evenly spaced non-silent windows instead of one huge input, which bounds latency and
stops one quiet stretch or hold-music segment from dominating. Pure numpy; no models, no I/O.
"""
from __future__ import annotations

import numpy as np

SR = 16_000


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64)))) if len(x) else 0.0


def windows(x: np.ndarray, sr: int = SR, win_s: float = 4.0, hop_s: float = 2.0,
            silence_rms: float = 0.004, max_n: int = 3) -> list[tuple[float, np.ndarray]]:
    """Return up to `max_n` (start_seconds, samples) windows of `win_s`, hopping `hop_s`, skipping silent ones.

    A clip no longer than one window is returned whole (as one window) unless it is silent. When more windows qualify
    than `max_n`, evenly spaced ones are kept so the whole call is still represented. Never returns a window shorter
    than `win_s` except for the single short-clip case.
    """
    win, hop = int(win_s * sr), max(1, int(hop_s * sr))
    if len(x) <= win:
        return [(0.0, x)] if rms(x) >= silence_rms else []
    starts = list(range(0, len(x) - win + 1, hop))
    if starts[-1] + win < len(x):
        starts.append(len(x) - win)                      # make sure the tail of the call is covered
    kept = [(s / sr, x[s:s + win]) for s in starts if rms(x[s:s + win]) >= silence_rms]
    if len(kept) > max_n:
        idx = np.unique(np.linspace(0, len(kept) - 1, max_n).round().astype(int))
        kept = [kept[i] for i in idx]
    return kept
