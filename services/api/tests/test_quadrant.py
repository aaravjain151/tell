"""Display-only voice x content quadrant: every cell, every boundary, additive field, unchanged signature."""
import re

import pytest

from doublespeak import pipeline, privacy, thresholds
from doublespeak.quadrant import INTENT_CLEAR_BELOW, VOICE_HUMAN_MAX, quadrant_for
from doublespeak.types import Tell, Verdict

BANNED = re.compile(r"\b(safe|legal|illegal|fraud|confirmed)\b", re.I)


def V(p_ai=0.5, p_scam=0.0, disclosed=False, tier="unsure", tells=None):
    return Verdict(tier=tier, p_ai=p_ai, p_scam=p_scam, confidence=0.9, disclosed_ai=disclosed, headline="h", advice="a", tells=tells or [])


def test_cut_points_documented_as_constants():
    assert VOICE_HUMAN_MAX == 0.40 and INTENT_CLEAR_BELOW == 0.30
    assert thresholds.P_AI_THRESHOLD == 0.60


@pytest.mark.parametrize("p_ai,p_scam,combo", [
    (0.10, 0.0, "human_ok"), (0.10, 0.9, "human_scam"), (0.90, 0.0, "ai_ok"), (0.90, 0.9, "ai_scam"),
])
def test_every_cell(p_ai, p_scam, combo):
    q = quadrant_for(V(p_ai, p_scam))
    assert q["combo"] == combo and q["combo_label"]


@pytest.mark.parametrize("p_ai,voice", [(0.40, "human"), (0.41, "unclear"), (0.59, "unclear"), (0.60, "ai"), (0.0, "human"), (1.0, "ai")])
def test_voice_boundaries(p_ai, voice):
    assert quadrant_for(V(p_ai))["voice"] == voice


@pytest.mark.parametrize("p_scam,intent", [
    (0.29, "not_scam"), (0.30, "unclear"), (thresholds.P_SCAM_THRESHOLD - 0.01, "unclear"),
    (thresholds.P_SCAM_THRESHOLD, "scam"), (1.0, "scam"), (0.0, "not_scam"),
])
def test_intent_boundaries(p_scam, intent):
    assert quadrant_for(V(0.1, p_scam))["intent"] == intent


def test_disclosed_without_scam_is_ai_ok():
    assert quadrant_for(V(0.2, 0.0, disclosed=True, tier="ai_disclosed"))["combo"] == "ai_ok"


def test_disclosed_with_scam_cues_is_ai_scam():
    assert quadrant_for(V(0.2, 0.9, disclosed=True, tier="ai_disclosed"))["combo"] == "ai_scam"


def test_scam_with_no_voice_evidence_is_voice_unclear_not_human():
    q = quadrant_for(V(0.5, 0.9, tier="scam"))
    assert q["voice"] == "unclear" and q["intent"] == "scam" and q["combo"] == "unclear"
    assert q["combo_label"] == "Scam pattern. Voice unclear."
    # transcript-only: tells present but no acoustic one ran -> still not "human"
    t = [Tell("llm_isms", "script", 0.1, 1.0, "e"), Tell("pause_regularity", "acoustic", 0.5, 1.0, "e", applicable=False)]
    assert quadrant_for(V(0.1, 0.9, tier="scam", tells=t))["voice"] == "unclear"
    t.append(Tell("pitch_stability", "acoustic", 0.1, 0.9, "e"))
    assert quadrant_for(V(0.1, 0.9, tier="scam", tells=t))["voice"] == "human"


def test_keys_and_banned_words():
    for p_ai in (0.0, 0.4, 0.5, 0.6, 1.0):
        for p_scam in (0.0, 0.3, 0.5, 0.55, 1.0):
            for d in (False, True):
                q = quadrant_for(V(p_ai, p_scam, disclosed=d))
                assert set(q) == {"voice", "voice_label", "intent", "intent_label", "combo", "combo_label", "voice_note"}
                assert not BANNED.search(" ".join(q.values()))


def test_additive_field_and_signature_unchanged():
    v = pipeline.analyze(None, "Please send gift cards right now, don't tell anyone, I am your grandson in trouble.")
    d = v.to_dict()
    assert d["quadrant"] == quadrant_for(v)
    payload = {"tier": v.tier, "p_ai": round(v.p_ai, 3), "p_scam": round(v.p_scam, 3),
               "tells": [(t.name, round(t.score, 3)) for t in v.tells], "thresholds_version": v.thresholds_version}
    assert v.signature == privacy.sign(payload, privacy.audio_fingerprint(None))
    assert "quadrant" not in payload
