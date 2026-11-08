"""Call-level pause features for the learned_tells head (signals/learned.py, optional "pauses" block).

Why call-level: the head scores 4 s windows, and a 4 s window rarely holds even one sentence-end pause. Pause style is a
property of the whole call, so these are measured once over the analysed audio and stacked onto the head's call logit.

Why these: the paired Qwen-vs-Sanath cue study (docs/qwen-cues-2026-11-08/, 18 pairs, held out by script) found that real
speech has more and longer long pauses (gap after a full stop ~571 vs ~324 ms; long pauses per minute clip-AUC 0.76-0.80),
and it replicated on scripts the study had not seen. One speaker and one engine, so the stacker is fitted and judged
held-out (training/learned_tells/pauses.py) before it ships; with no "pauses" block in the weights nothing here runs.

Pure numpy, 16 kHz mono float PCM. The speech mask is relative to the call's own levels (shadow._speech_mask), so a noisy
line moves it: that is why the stacker is trained on degraded channels too. NaN = not enough speech to say.
"""
from __future__ import annotations

import numpy as np

from .shadow import _frame_db, _runs, _speech_mask

SR = 16_000
HOP_MS = 10
MIN_PAUSE_MS = 150      # same floor as acoustic.pauses_ms: shorter gaps are stop closures, not pauses
LONG_PAUSE_MS = 300     # the cue study's "long pause"
MIN_SPAN_S = 5.0
MIN_RUNS = 4

PAUSE_FEATURES = ("long_pause_per_min", "long_pause_median_ms", "pause_cv", "pause_share", "speech_run_median_s")
_NAN = float("nan")


def _empty() -> dict[str, float]:
    return {k: _NAN for k in PAUSE_FEATURES}


def speech_runs(x16k: np.ndarray) -> list[tuple[int, int]]:
    """Speech runs as (start, end) in 10 ms hops, from the call's own relative speech mask."""
    db = _frame_db(np.asarray(x16k, dtype=np.float64))
    if db.size == 0:
        return []
    return [(int(s), int(e)) for s, e in _runs(_speech_mask(db))]


def pause_stats(runs: list[tuple[int, int]]) -> dict[str, float]:
    """Pause features from speech runs (10 ms hops). Gaps are measured inside the speech span only."""
    out = _empty()
    if len(runs) < MIN_RUNS:
        return out
    span_s = (runs[-1][1] - runs[0][0]) * HOP_MS / 1000
    if span_s < MIN_SPAN_S:
        return out
    gaps = np.array([(runs[i + 1][0] - runs[i][1]) * HOP_MS for i in range(len(runs) - 1)], dtype=float)
    pauses = gaps[gaps >= MIN_PAUSE_MS]
    long_ = gaps[gaps >= LONG_PAUSE_MS]
    out["long_pause_per_min"] = 60.0 * long_.size / span_s
    out["pause_share"] = float(pauses.sum() / 1000 / span_s)
    out["speech_run_median_s"] = float(np.median([(e - s) * HOP_MS / 1000 for s, e in runs]))
    if long_.size >= 2:
        out["long_pause_median_ms"] = float(np.median(long_))
    if pauses.size >= 3:
        out["pause_cv"] = float(pauses.std() / (pauses.mean() + 1e-9))
    return out


def call_pause_features(x16k: np.ndarray) -> dict[str, float]:
    """All PAUSE_FEATURES for one call; NaN where there is not enough speech (never raises on short/silent input)."""
    return pause_stats(speech_runs(x16k))


def describe(f: dict[str, float]) -> str:
    """One plain-English line for the evidence string."""
    lp, med = f.get("long_pause_per_min", _NAN), f.get("long_pause_median_ms", _NAN)
    if not np.isfinite(lp):
        return "pauses: not enough speech to measure"
    s = f"pauses: {lp:.0f} long pause{'s' if round(lp) != 1 else ''}/min"
    return s + (f", typical {med:.0f} ms" if np.isfinite(med) else "")
