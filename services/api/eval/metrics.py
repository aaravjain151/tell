"""Pure metric helpers for the wild eval (no I/O, no pipeline)."""
from __future__ import annotations

import math


def fpr_at_tpr(ai_scores: list[float], human_scores: list[float], tpr: float = 0.90) -> tuple[float | None, float | None]:
    """Return (fpr, threshold) of the loosest threshold that still catches >= `tpr` of AI clips.

    Positive = AI. A clip is flagged when score >= threshold. None, None if either class is empty.
    """
    if not ai_scores or not human_scores:
        return None, None
    ranked = sorted(ai_scores, reverse=True)
    k = max(1, math.ceil(tpr * len(ranked)))      # must catch k of n AI clips
    thr = ranked[k - 1]
    fpr = sum(s >= thr for s in human_scores) / len(human_scores)
    return fpr, thr
