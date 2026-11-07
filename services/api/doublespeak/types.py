from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal

Tier = Literal["human", "ai_disclosed", "ai_undisclosed", "scam", "unsure"]
Family = Literal["acoustic", "script", "intent"]


@dataclass
class Tell:
    """One signal that fired (or explicitly didn't)."""

    name: str
    family: Family
    score: float          # 0..1 toward AI (acoustic/script) or toward scam (intent)
    weight: float
    evidence: str         # one line a non-engineer can read
    applicable: bool = True  # False → excluded from fusion (e.g. clip too short)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["score"] = round(self.score, 3)
        return d


@dataclass
class Verdict:
    tier: Tier
    p_ai: float
    p_scam: float
    confidence: float
    disclosed_ai: bool
    headline: str
    advice: str
    tells: list[Tell] = field(default_factory=list)
    thresholds_version: str = ""
    egress: dict = field(default_factory=dict)
    signature: str = ""
    cost: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)      # plain sentences from fixed wording (reasons.py), deterministic; safe to speak or show
    model_notes: list[str] = field(default_factory=list)  # DISPLAY ONLY: sanitised sentences from the local LLM; never a tell, tier, flag or TTS input
    transcript: str = ""   # what was analysed (typed, or from local STT); returned to the local UI only, so it can mark up the phrases that fired

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "p_ai": round(self.p_ai, 3),
            "p_scam": round(self.p_scam, 3),
            "confidence": round(self.confidence, 3),
            "disclosed_ai": self.disclosed_ai,
            "headline": self.headline,
            "advice": self.advice,
            "tells": [t.to_dict() for t in self.tells],
            "thresholds_version": self.thresholds_version,
            "egress": self.egress,
            "signature": self.signature,
            "cost": self.cost,
            "reasons": list(self.reasons),
            "model_notes": list(self.model_notes),
            "transcript": self.transcript,
        }
