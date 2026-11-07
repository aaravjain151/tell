"""Unwired, in-memory stream policy; all time is supplied by the caller.

Ticks must have finite, nondecreasing call timestamps. Hysteresis runs during
warm-up, starting at human; warm-up masks that tier until both minima are met.
Five lower ticks need not agree on a tier: the fifth tick supplies the target.
Disclosure immediately replaces non-scam tiers and suppresses undisclosed-AI
alerts. Red safety overrides take precedence over warm-up and hysteresis.

Review changes (A1): a single scam tick never alerts (amber and high-p_scam red need `escalation_ticks` consecutive
ticks); an amber is held 15 s; dismiss() clears evidence so stale evidence cannot re-latch; dismiss(None) works.

A pending scam amber can be corroborated on any tier within 30 seconds
(inclusive). High p_scam alone requires a current scam tick. Dismiss accepts
any emitted sequence belonging to the active red episode, clears its pending
amber, and leaves the scam tier to normal de-escalation. Fresh red conditions
can latch again. Sequence numbers start at 1 and restart after reset.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import isfinite
from statistics import median
from typing import Literal

from .types import Tier, Verdict

POLICY_VERSION = "stabiliser-v1"
INTENT_FAMILIES = frozenset({
    "urgency", "payment_rails", "impersonation", "credential_ask", "secrecy",
})
_SEVERITY = {"human": 0, "unsure": 1, "ai_disclosed": 2, "ai_undisclosed": 3, "scam": 4}
ShownTier = Literal["human", "unsure", "ai_disclosed", "ai_undisclosed", "scam", "warming_up"]


@dataclass(frozen=True)
class StabiliserConfig:
    warmup_speech_seconds: float = 8.0
    warmup_words: int = 20
    escalation_ticks: int = 2
    deescalation_ticks: int = 5
    dwell_seconds: float = 20.0
    amber_window_seconds: float = 30.0
    amber_hold_seconds: float = 15.0      # an amber stays amber this long after the last scam tick (no notify flapping)
    red_p_scam_threshold: float = 0.8
    ai_speech_seconds: float = 15.0
    p_ai_threshold: float = 0.6

    def __post_init__(self) -> None:
        for name in ("warmup_speech_seconds", "dwell_seconds", "amber_window_seconds", "amber_hold_seconds", "ai_speech_seconds"):
            value = getattr(self, name)
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        for name in ("warmup_words", "escalation_ticks", "deescalation_ticks"):
            value = getattr(self, name)
            if not isinstance(value, int) or value < (0 if name == "warmup_words" else 1):
                raise ValueError(f"invalid {name}")
        for value in (self.p_ai_threshold, self.red_p_scam_threshold):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError("probability thresholds must be in [0, 1]")


@dataclass
class RawTick:
    t: float
    raw_tier: Tier
    p_ai: float
    p_scam: float
    confidence: float
    disclosed_ai: bool
    intent_families: set[str]
    speech_seconds: float
    words: int
    degraded: list[str]


@dataclass
class StreamVerdict:
    t: float
    seq: int
    raw_tier: Tier
    shown_tier: ShownTier
    p_ai: float
    p_scam: float
    confidence: float
    evidence: list[str]
    alert: Literal["amber", "red"] | None
    alert_reason: list[str]
    degraded: list[str]
    policy_version: str = POLICY_VERSION


def from_verdict(v: Verdict, t: float, speech_seconds: float, words: int) -> RawTick:
    """Map recognised intent names; Verdict has no degraded field (use [])."""
    return RawTick(
        t=t, raw_tier=v.tier, p_ai=v.p_ai, p_scam=v.p_scam,
        confidence=v.confidence, disclosed_ai=v.disclosed_ai,
        intent_families={tell.name for tell in v.tells
                         if tell.family == "intent" and tell.applicable
                         and tell.score >= 0.5 and tell.name in INTENT_FAMILIES},
        speech_seconds=speech_seconds, words=words, degraded=[],
    )


class Stabiliser:
    def __init__(self, config: StabiliserConfig | None = None) -> None:
        self.config = config if config is not None else StabiliserConfig()
        self.reset()

    def reset(self) -> None:
        """Begin a fresh call, retaining only configuration."""
        self._seq = 0
        self._last_t: float | None = None
        self._tier: Tier = "human"
        self._last_change: float | None = None
        self._candidate: Tier | None = None
        self._up_count = 0
        self._down_count = 0
        self._evidence: set[str] = set()
        self._disclosed = False
        self._warmed = False
        self._p_ai: deque[float] = deque(maxlen=3)
        self._amber_t: float | None = None
        self._amber_shown_t: float | None = None
        self._scam_streak = 0                 # consecutive raw scam ticks
        self._hi_streak = 0                   # consecutive raw scam ticks with p_scam >= red threshold
        self._red_seq: int | None = None
        self._red_reasons: list[str] = []

    def dismiss(self, seq: int | None = None) -> bool:
        """Acknowledge the active red episode (seq=None: whatever is active). Stale/future seq is ignored.

        Evidence and streaks are cleared so the SAME stale evidence cannot re-latch on the very next tick: a dismissed
        alert returns only on fresh corroboration. Returns True when something was dismissed."""
        if self._red_seq is None or (seq is not None and not self._red_seq <= seq <= self._seq):
            return False
        self._red_seq = None
        self._red_reasons = []
        self._amber_t = self._amber_shown_t = None
        self._evidence.clear()
        self._scam_streak = self._hi_streak = 0
        self._clear_streaks()
        return True

    @property
    def latched(self) -> bool:
        return self._red_seq is not None

    def _clear_streaks(self) -> None:
        self._candidate = None
        self._up_count = self._down_count = 0

    def _change(self, tier: Tier, t: float) -> None:
        if tier != self._tier:
            self._tier = tier
            self._last_change = t
        self._clear_streaks()

    def _advance(self, target: Tier, t: float) -> None:
        if _SEVERITY[target] > _SEVERITY[self._tier]:
            self._down_count = 0
            self._up_count = self._up_count + 1 if self._candidate == target else 1
            self._candidate = target
            if self._up_count >= self.config.escalation_ticks:
                self._change(target, t)
        elif _SEVERITY[target] < _SEVERITY[self._tier]:
            self._candidate = None
            self._up_count = 0
            self._down_count += 1
            if (self._down_count >= self.config.deescalation_ticks
                    and (self._last_change is None
                         or t - self._last_change >= self.config.dwell_seconds)):
                self._change(target, t)
        else:
            self._clear_streaks()

    def update(self, tick: RawTick) -> StreamVerdict:
        """Consume one ordered tick and return an independent snapshot."""
        if not isfinite(tick.t) or tick.t < 0 or (self._last_t is not None and tick.t < self._last_t):
            raise ValueError("tick.t must be finite, nonnegative and nondecreasing")
        if tick.raw_tier not in _SEVERITY:
            raise ValueError("unknown raw tier")
        self._last_t = tick.t
        self._seq += 1
        self._p_ai.append(tick.p_ai)
        self._evidence.update(tick.intent_families & INTENT_FAMILIES)
        self._disclosed |= tick.disclosed_ai
        self._warmed |= (tick.speech_seconds >= self.config.warmup_speech_seconds
                         and tick.words >= self.config.warmup_words)
        self._scam_streak = self._scam_streak + 1 if tick.raw_tier == "scam" else 0
        self._hi_streak = (self._hi_streak + 1
                           if tick.raw_tier == "scam" and tick.p_scam >= self.config.red_p_scam_threshold else 0)
        if self._amber_t is not None and tick.t - self._amber_t > self.config.amber_window_seconds:
            self._amber_t = None
        corroborated = (len(self._evidence) >= 2
                        and bool(self._evidence & {"payment_rails", "credential_ask"}))
        reasons = []
        if corroborated and (tick.raw_tier == "scam" or self._amber_t is not None):
            reasons.append("corroborated_intent")
        # High p_scam alone is not enough on one tick: it must hold for `escalation_ticks` consecutive ticks.
        if self._hi_streak >= self.config.escalation_ticks:
            reasons.append("high_p_scam")
        if reasons and self._red_seq is None:
            self._red_seq = self._seq
            self._red_reasons = reasons
        alert: Literal["amber", "red"] | None = None
        alert_reason: list[str] = []
        if self._red_seq is not None:
            self._change("scam", tick.t)
            alert, alert_reason = "red", list(self._red_reasons)
        else:
            target = tick.raw_tier
            if self._disclosed:
                if self._tier not in ("scam", "ai_disclosed"):
                    self._change("ai_disclosed", tick.t)
                if target != "scam":
                    target = "ai_disclosed"
            self._advance(target, tick.t)
            if tick.raw_tier == "scam":
                self._amber_t = tick.t
                if self._scam_streak >= self.config.escalation_ticks:    # one outlier tick is not an alert
                    self._amber_shown_t = tick.t
            if (self._amber_shown_t is not None
                    and tick.t - self._amber_shown_t <= self.config.amber_hold_seconds):
                alert, alert_reason = "amber", ["uncorroborated_scam"]
            if (alert is None and tick.raw_tier == "ai_undisclosed" and not self._disclosed
                  and tick.speech_seconds >= self.config.ai_speech_seconds
                  and len(self._p_ai) == 3
                  and median(self._p_ai) >= self.config.p_ai_threshold):
                alert, alert_reason = "amber", ["sustained_ai_evidence"]
        shown: ShownTier = self._tier if self._warmed or alert == "red" else "warming_up"
        return StreamVerdict(
            t=tick.t, seq=self._seq, raw_tier=tick.raw_tier, shown_tier=shown,
            p_ai=tick.p_ai, p_scam=tick.p_scam, confidence=tick.confidence,
            evidence=sorted(self._evidence), alert=alert, alert_reason=alert_reason,
            degraded=list(tick.degraded),
        )
