"""DISPLAY-ONLY voice x content quadrant. Nothing here is read by scorer.py, reasons.py, speak.py or the signature.

Two independent questions, answered from existing verdict fields only:
  voice  : is the VOICE human or AI?   ai if disclosed_ai or p_ai >= P_AI_THRESHOLD; human if p_ai <= VOICE_HUMAN_MAX;
           unclear in between. If the verdict carries tells but none of the acoustic ones ran (a transcript with no
           audio), a human voice is NOT claimed: voice is unclear unless the caller said it is automated.
  intent : is the CONTENT a scam pattern?  scam if p_scam >= P_SCAM_THRESHOLD; not_scam if p_scam < INTENT_CLEAR_BELOW;
           unclear in between.
The cut points below are display cut points, not detection thresholds, so they live here and not in thresholds.py.
Wording never says safe, legal, illegal, fraud or confirmed.
"""
from __future__ import annotations

from . import thresholds

VOICE_HUMAN_MAX = 0.40       # p_ai <= this reads "human"; between this and P_AI_THRESHOLD reads "unclear"
INTENT_CLEAR_BELOW = 0.30    # p_scam < this reads "no scam pattern"; up to P_SCAM_THRESHOLD reads "unclear"

VOICE_LABEL = {"human": "Voice sounds human", "ai": "Voice may be AI", "unclear": "Voice unclear"}
INTENT_LABEL = {"scam": "Scam pattern in what was said", "not_scam": "No scam pattern heard", "unclear": "Scam pattern unclear"}
COMBO_LABEL = {
    "human_ok": "Human voice, no scam pattern heard.",
    "human_scam": "Human voice, but scam pattern in what was said.",
    "ai_ok": "AI voice, no scam pattern heard.",
    "ai_scam": "AI voice and scam pattern in what was said.",
}


def _voice(v) -> tuple[str, str]:
    if getattr(v, "disclosed_ai", False):
        return "ai", "The caller said it is automated."
    p = v.p_ai
    if p >= thresholds.P_AI_THRESHOLD:
        return "ai", "Based on how the voice and wording sounded."
    tells = getattr(v, "tells", None) or []
    if tells and not any(t.family == "acoustic" and t.applicable and t.weight > 0 for t in tells):
        return "unclear", "No audio was analysed, so the voice could not be judged."
    if p <= VOICE_HUMAN_MAX:
        return "human", "Based on how the voice and wording sounded."
    return "unclear", "The voice signs are mixed."


def _intent(p_scam: float) -> str:
    if p_scam >= thresholds.P_SCAM_THRESHOLD:
        return "scam"
    return "not_scam" if p_scam < INTENT_CLEAR_BELOW else "unclear"


def quadrant_for(v) -> dict:
    voice, note = _voice(v)
    intent = _intent(v.p_scam)
    if voice == "unclear" or intent == "unclear":
        combo = "unclear"
        if voice == "unclear" and intent == "scam":
            label = "Scam pattern. Voice unclear."
        elif voice == "unclear" and intent == "not_scam":
            label = "Voice unclear. No scam pattern heard."
        elif voice == "unclear":
            label = "Voice and scam pattern both unclear."
        else:
            label = f"{VOICE_LABEL[voice]}. Scam pattern unclear."
    else:
        combo = f"{voice}_{'scam' if intent == 'scam' else 'ok'}"
        label = COMBO_LABEL[combo]
    return {"voice": voice, "voice_label": VOICE_LABEL[voice], "intent": intent, "intent_label": INTENT_LABEL[intent],
            "combo": combo, "combo_label": label, "voice_note": note}
