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

HONEST "HOW SURE" (display only; `confidence` itself and the signature are unchanged). `confidence` measures how many
of our signals ran, not whether the VOICE evidence is reliable, so a voice that sits in the middle for a whole call could
still read "High (100 out of 100)". The voice question is UNRESOLVED when any of these holds (unless the caller said it
is automated, which settles the voice by words):
    * UNSURE_P_AI_LO (0.30) <= p_ai < P_AI_THRESHOLD (0.60)            (the unclear band)
    * fewer than MIN_VOTERS (2) acoustic/neural voters applied
    * the applicable neural voters (neural_onnx, neural_hf, neural_pella) differ by MORE than DISAGREE_SPREAD (0.35)
When unresolved, `confidence_label` is capped at "medium"; it is "low" when the voters disagree AND p_ai is in the band.
`confidence_note` is fixed wording: "The voice check is not sure." or "The voice checks disagree." (empty when resolved).
`voice_sure` (0-100) = margin * coverage * agreement: margin grows from 40 (at the band edge) to 100 (0.25 beyond it) and is
capped at 40 inside the band; coverage = min(1, voters / 3); agreement falls as the neural spread rises. Added fields:
voice_sure, voice_unresolved, confidence_note. Wording never says safe, legal, illegal, fraud or confirmed.
"""
from __future__ import annotations

from . import thresholds

HIGH_P_AI = 0.80
UNSURE_P_AI_LO = 0.30
MIN_VOTERS = 2
DISAGREE_SPREAD = 0.35
NEURAL_VOTERS = ("neural_onnx", "neural_hf", "neural_pella")
NOTE_UNSURE = "The voice check is not sure."
NOTE_DISAGREE = "The voice checks disagree."
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


def voice_state(v) -> dict:
    """-> {voters, spread, in_band, disagree, unresolved}. Reads only p_ai, disclosed_ai and tells."""
    tells = getattr(v, "tells", None) or []
    voters = [t for t in tells if t.family == "acoustic" and t.applicable and t.weight > 0]
    neural = [t.score for t in voters if t.name in NEURAL_VOTERS]
    spread = round(max(neural) - min(neural), 6) if len(neural) >= 2 else 0.0
    in_band = UNSURE_P_AI_LO <= v.p_ai < thresholds.P_AI_THRESHOLD and not getattr(v, "disclosed_ai", False)
    disagree = spread > DISAGREE_SPREAD
    unresolved = in_band or len(voters) < MIN_VOTERS or disagree
    if getattr(v, "disclosed_ai", False):
        unresolved = False
    return {"voters": len(voters), "spread": spread, "in_band": in_band, "disagree": disagree, "unresolved": unresolved}


def voice_sure_for(v, st: dict) -> int:
    p = v.p_ai
    dist = max(0.0, p - thresholds.P_AI_THRESHOLD, UNSURE_P_AI_LO - p)
    margin = 0.4 + 0.6 * min(1.0, dist / 0.25)
    if st["in_band"]:
        margin = min(margin, 0.4)
    coverage = min(1.0, st["voters"] / 3)
    agreement = 1.0 - min(1.0, st["spread"] / 0.7)
    return _pct(margin * coverage * agreement)


def scores_for(v) -> dict:
    level, reason = level_for(v.tier, v.p_ai, v.p_scam)
    label = confidence_label(v.confidence)
    st = voice_state(v)
    note = ""
    if st["unresolved"]:
        if label == "high":
            label = "medium"
        if st["disagree"] and st["in_band"]:
            label = "low"
        note = NOTE_DISAGREE if st["disagree"] else NOTE_UNSURE
    return {"scam": _pct(v.p_scam), "ai_voice": _pct(v.p_ai), "confidence": _pct(v.confidence),
            "confidence_label": label, "level": level, "level_reason": reason,
            "voice_sure": voice_sure_for(v, st), "voice_unresolved": st["unresolved"], "confidence_note": note}
