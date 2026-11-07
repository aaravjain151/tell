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


def auc(ai_scores: list[float], human_scores: list[float]) -> float | None:
    """P(random AI clip scores above a random human clip); ties count half (Mann-Whitney U)."""
    if not ai_scores or not human_scores:
        return None
    wins = sum((a > h) + 0.5 * (a == h) for a in ai_scores for h in human_scores)
    return wins / (len(ai_scores) * len(human_scores))


def eer(ai_scores: list[float], human_scores: list[float]) -> float | None:
    """Equal error rate: where miss rate (AI below threshold) meets false-alarm rate (human at/above it)."""
    if not ai_scores or not human_scores:
        return None
    best = (2.0, 1.0)
    for t in sorted(set(ai_scores) | set(human_scores)):
        miss = sum(a < t for a in ai_scores) / len(ai_scores)
        fa = sum(h >= t for h in human_scores) / len(human_scores)
        gap = abs(miss - fa)
        if gap < best[0]:
            best = (gap, (miss + fa) / 2)
    return best[1]


def loeo(by_engine: dict[str, list[float]], human_scores: list[float], tpr: float = 0.90) -> dict[str, dict]:
    """Leave-one-engine-out. For each engine: pick the threshold that catches `tpr` of the OTHER engines' clips,
    then report the held-out engine's TPR and the humans' FPR at that threshold. Needs >= 2 engines and humans.
    (Humans are not held out: they are a separate class, so FPR comes from the same human clips for every engine.)
    """
    out: dict[str, dict] = {}
    for held, scores in by_engine.items():
        rest = [s for e, v in by_engine.items() if e != held for s in v]
        if not rest or not human_scores or not scores:
            continue
        _, thr = fpr_at_tpr(rest, human_scores, tpr)
        out[held] = {"threshold": thr, "tpr": sum(s >= thr for s in scores) / len(scores),
                     "fpr": sum(h >= thr for h in human_scores) / len(human_scores)}
    return out
