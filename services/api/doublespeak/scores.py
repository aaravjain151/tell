"""DISPLAY-ONLY scores for the UI. Nothing here is read by scorer.py, reasons.py, speak.py or the signature.

What `Verdict.confidence` means (scorer.py): it is NOT accuracy and NOT a calibrated probability. It is
    min(1, 0.35 + 0.12 * n_signals) * (0.5 + 0.5 * min(1, |p_ai - P_AI_THRESHOLD| / 0.25))
i.e. how many applicable signals ran, times how far p_ai sits from the AI threshold; a scam score above its
threshold lifts it to at least 0.5 + 0.5 * p_scam, a disclosure lifts it to at least 0.75, a human-denial tell adds
0.1. So it measures agreement and coverage of our own signals, not how often we are right.

`level` (a plain Low / Medium / High for the person on the call), deterministic from the tier and p values:
    high   : tier scam; or tier ai_undisclosed with p_ai >= 0.80
    medium : other ai_undisclosed; or unsure with p_scam >= 0.30; or ai_disclosed with p_scam >= 0.30
    low    : everything else (human, unsure without pressure cues, ai_disclosed without scam cues)
`confidence_label` bands: < 0.50 low, < 0.80 medium, otherwise high.
Wording never says safe, legal, illegal or fraud confirmed.
"""
from __future__ import annotations

HIGH_P_AI = 0.80
CUE_P_SCAM = 0.30
CONF_MEDIUM, CONF_HIGH = 0.50, 0.80


def _pct(x: float) -> int:
    return int(round(max(0.0, min(1.0, float(x))) * 100))


def confidence_label(conf: float) -> str:
    return "high" if conf >= CONF_HIGH else "medium" if conf >= CONF_MEDIUM else "low"


def level_for(tier: str, p_ai: float, p_scam: float) -> tuple[str, str]:
    if tier == "scam":
        return "high", "Scam wording was detected on this call."
    if tier == "ai_undisclosed":
        if p_ai >= HIGH_P_AI:
            return "high", "The voice looks synthetic and the caller did not say so."
        return "medium", "The voice may be synthetic and the caller did not say so."
    if tier in ("unsure", "ai_disclosed") and p_scam >= CUE_P_SCAM:
        return "medium", "Some pressure or payment wording came up."
    if tier == "ai_disclosed":
        return "low", "The caller said it is automated, and no scam wording was found."
    if tier == "unsure":
        return "low", "Not enough signal to judge, and no scam wording was found."
    return "low", "No synthetic-voice or scam signs were found in what we heard."


def scores_for(v) -> dict:
    level, reason = level_for(v.tier, v.p_ai, v.p_scam)
    return {"scam": _pct(v.p_scam), "ai_voice": _pct(v.p_ai), "confidence": _pct(v.confidence),
            "confidence_label": confidence_label(v.confidence), "level": level, "level_reason": reason}
