"""Plain-language reasons: one fixed sentence per tell that fired, for an older person to read.

Deterministic and code-only. The sentences are fixed wording (never built from caller text or model output),
so they are safe to show and carry no quote of what the caller said. Model tells (`llm_assistant_style`, `llm_scam_framing`) are ignored here on
purpose: model text is shown separately as `model_notes` and never becomes a reason.
"""
from __future__ import annotations

import re

from .types import Tell

MAX_REASONS = 4
FIRED = 0.5         # intent tells: any pattern hit scores >= 0.55
FIRED_VOICE = 0.6   # voice and wording tells point toward AI at the same bar as P_AI_THRESHOLD

NONE_FOUND = "No warning signs found. Doublespeak can be wrong."
DISCLOSED = "The caller said it is an automated assistant."

INTENT_REASON = {
    "payment_rails": "They asked you to pay or send money.",
    "secrecy": "They asked you to keep this secret.",
    "urgency": "They pressed you to act right now.",
    "impersonation": "They claimed to be someone you know or trust.",
    "credential_ask": "They asked for a code or a password.",
    "emergency": "They described an emergency to scare you.",
    "authority_threat": "They threatened you with arrest or the police.",
}
GIFT_CARDS = "They asked you to buy gift cards."
VOICE = "The voice may be an AI copy, not a real person."
SCRIPTED = "The wording sounds scripted."

VOICE_TELLS = {"pause_regularity", "breath_proxy", "pitch_stability", "noise_floor", "high_band", "neural_onnx", "neural_hf"}
SCRIPT_TELLS = {"llm_isms", "disfluency", "sentence_uniformity", "contraction_rate"}
MODEL_TELLS = {"llm_assistant_style", "llm_scam_framing"}   # model-made tells never become reasons
_GIFT = re.compile(r"gift ?card|steam card|itunes card|google play|scratch", re.I)


def build(tells: list[Tell], disclosed_ai: bool = False) -> list[str]:
    """At most MAX_REASONS sentences, strongest first (weight x score), no duplicates."""
    ranked: list[tuple[float, str]] = []
    for t in tells:
        if not t.applicable or t.weight <= 0 or t.name in MODEL_TELLS:
            continue
        rank = t.weight * t.score
        if t.family == "intent" and t.name in INTENT_REASON and t.score >= FIRED:
            sentence = GIFT_CARDS if t.name == "payment_rails" and _GIFT.search(t.evidence) else INTENT_REASON[t.name]
            ranked.append((rank, sentence))
        elif t.name in VOICE_TELLS and t.score >= FIRED_VOICE and not disclosed_ai:
            ranked.append((rank, VOICE))
        elif t.name in SCRIPT_TELLS and t.score >= FIRED_VOICE and not disclosed_ai:
            ranked.append((rank, SCRIPTED))
    ranked.sort(key=lambda r: -r[0])
    out: list[str] = []
    for _, s in ranked:
        if s not in out:
            out.append(s)
    if disclosed_ai:
        out.insert(0, DISCLOSED)
    out = out[:MAX_REASONS]
    return out or [NONE_FOUND]
