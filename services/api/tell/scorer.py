"""Deterministic fusion. Models (if any) only produce Tells; this file decides.

p_ai   = ACOUSTIC_SHARE * weighted_mean(acoustic) + (1-ACOUSTIC_SHARE) * weighted_mean(script)
         (if only one family is applicable, use it alone)
p_scam = noisy-OR over intent tells, weighted
tier   = scam if p_scam >= P_SCAM_THRESHOLD
         else ai_disclosed / ai_undisclosed if p_ai >= P_AI_THRESHOLD
         else human
         → "unsure" when confidence < MIN_CONFIDENCE (never for scam)
"""
from __future__ import annotations

from . import thresholds as T
from .types import Tell, Verdict

COPY = {
    "human": ("Sounds human", "No synthetic-voice tells found. If money or codes come up, hang up and call back on a number you already have."),
    "ai_disclosed": ("AI — identified itself", "The caller said it's automated. Fine for appointment reminders and sales; never share codes or payment with an automated caller."),
    "ai_undisclosed": ("Likely synthetic, didn't say so", "Legitimate AI callers are required to identify themselves. Treat this as untrusted: hang up and call back on a known number."),
    "scam": ("Scam pattern", "Hang up. Do not send money, cards, or codes. Call the person or organisation back on a number you already have."),
    "unsure": ("Unsure", "Not enough signal to judge. The safe move is the same: if money or codes come up, hang up and call back on a known number."),
}


def _wmean(tells: list[Tell]) -> float | None:
    usable = [t for t in tells if t.applicable and t.weight > 0]
    if not usable:
        return None
    return sum(t.score * t.weight for t in usable) / sum(t.weight for t in usable)


def _noisy_or(tells: list[Tell]) -> float:
    usable = [t for t in tells if t.applicable and t.weight > 0 and t.score > 0]
    if not usable:
        return 0.0
    wmax = max(T.INTENT_WEIGHTS.values())
    p = 1.0
    for t in usable:
        p *= 1.0 - min(1.0, t.score * t.weight / wmax)
    return 1.0 - p


def fuse(acoustic: list[Tell], script: list[Tell], intent: list[Tell], disclosed_ai: bool,
         denial: bool = False, ctx: dict | None = None) -> Verdict:
    ctx = ctx or {}
    a, s = _wmean(acoustic), _wmean(script)
    if a is not None and s is not None:
        p_ai = T.ACOUSTIC_SHARE * a + (1 - T.ACOUSTIC_SHARE) * s
    elif a is not None:
        p_ai = a
    elif s is not None:
        p_ai = s
    else:
        p_ai = 0.5
    p_scam = _noisy_or(intent)

    n_sig = sum(1 for t in acoustic + script if t.applicable and t.weight > 0)
    margin = abs(p_ai - T.P_AI_THRESHOLD)
    conf = min(1.0, 0.35 + 0.12 * n_sig) * (0.5 + 0.5 * min(1.0, margin / 0.25))
    if p_scam >= T.P_SCAM_THRESHOLD:
        conf = max(conf, 0.5 + 0.5 * p_scam)

    tells = list(acoustic) + list(script) + list(intent)
    if denial and p_ai >= T.P_AI_THRESHOLD:
        tells.append(Tell("ai_denial", "script", 0.9, 0.0, "caller claimed to be human while voice tells point to synthetic", applicable=False))
        conf = min(1.0, conf + 0.1)

    if p_scam >= T.P_SCAM_THRESHOLD:
        tier = "scam"
    elif disclosed_ai:
        # "I'm an automated assistant" is itself the strongest AI evidence we can get
        tier = "ai_disclosed"
        p_ai = max(p_ai, T.P_AI_THRESHOLD)
        conf = max(conf, 0.75)
    elif p_ai >= T.P_AI_THRESHOLD:
        tier = "ai_disclosed" if disclosed_ai else "ai_undisclosed"
    else:
        tier = "human"
    if tier not in ("scam", "ai_disclosed") and (conf < T.MIN_CONFIDENCE or (margin < T.UNSURE_BAND and n_sig < 3)):
        tier = "unsure"

    headline, advice = COPY[tier]
    if tier in ("ai_undisclosed", "ai_disclosed", "human") and p_scam >= 0.3:
        advice = "Some pressure or payment language came up. " + advice
    return Verdict(tier=tier, p_ai=p_ai, p_scam=p_scam, confidence=conf, disclosed_ai=disclosed_ai,
                   headline=headline, advice=advice, tells=tells, thresholds_version=T.THRESHOLDS_VERSION)
