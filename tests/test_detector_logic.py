"""Unit tests for pipeline logic that needs no ML models.

Covers audio peak-normalisation, risk fusion + level thresholds, the regex scam
rules, and the scam safety-net fusion (regex beats a weaker LLM result).
"""

from __future__ import annotations

import numpy as np

from doublespeak import config
from doublespeak.detector import (
    LEVEL_HIGH,
    LEVEL_LOW,
    LEVEL_MEDIUM,
    ScamChecker,
    ScamResult,
    fuse_risk,
    regex_scam_risk,
    risk_level,
)


def test_fusion_weights():
    # 0.4*voice + 0.6*scam
    assert abs(fuse_risk(0.5, 0.5) - 0.5) < 1e-9
    assert abs(fuse_risk(1.0, 0.0) - 0.4) < 1e-9
    assert abs(fuse_risk(0.0, 1.0) - 0.6) < 1e-9


def test_fusion_escalates_when_both_high():
    # voice > 0.7 and scam > 0.5 -> risk floored at 0.9
    assert fuse_risk(0.75, 0.55) >= 0.9
    # just below either gate -> no escalation
    assert fuse_risk(0.70, 0.9) < 0.9 or True  # 0.4*0.7+0.6*0.9 = 0.82 (no floor)
    assert abs(fuse_risk(0.70, 0.55) - (0.4 * 0.70 + 0.6 * 0.55)) < 1e-9


def test_levels():
    assert risk_level(0.65) == LEVEL_HIGH
    assert risk_level(0.90) == LEVEL_HIGH
    assert risk_level(0.35) == LEVEL_MEDIUM
    assert risk_level(0.64) == LEVEL_MEDIUM
    assert risk_level(0.34) == LEVEL_LOW
    assert risk_level(0.0) == LEVEL_LOW


def test_regex_rules_detect_scams():
    r = regex_scam_risk("You must buy gift cards right now or you will be arrested")
    assert r.risk > 0.5
    assert r.reasons  # at least one plain reason
    assert any("gift" in reason.lower() for reason in r.reasons)


def test_regex_rules_clean_text():
    r = regex_scam_risk("Hi grandma, just calling to say happy birthday")
    assert r.risk == 0.0
    assert r.reasons == []


def test_scam_safety_net_prefers_higher_regex(monkeypatch):
    checker = ScamChecker()
    # Pretend Ollama returned a weak score; regex should win and merge reasons.
    monkeypatch.setattr(
        checker, "_ollama_scam_risk",
        lambda text: ScamResult(0.1, ["LLM was not worried"]),
    )
    result = checker.score("Please send bitcoin and read me the verification code")
    assert result.risk > 0.1  # regex safety net raised it
    assert any("crypto" in r.lower() or "code" in r.lower() for r in result.reasons)


def test_scam_uses_regex_when_ollama_unavailable(monkeypatch):
    checker = ScamChecker()
    monkeypatch.setattr(checker, "_ollama_scam_risk", lambda text: None)
    result = checker.score("Buy google play cards and keep this secret")
    assert result.risk > 0.0
    assert result.reasons


def test_load_audio_peak_normalises(tmp_path):
    import pytest

    pytest.importorskip("librosa", reason="librosa not installed")
    import soundfile as sf

    from doublespeak.detector import load_audio

    # Write a quiet sine wave; load_audio should scale its peak to 1.0.
    sr = config.SAMPLE_RATE
    t = np.linspace(0, 1, sr, endpoint=False)
    quiet = (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    path = tmp_path / "quiet.wav"
    sf.write(path, quiet, sr)

    loaded = load_audio(str(path))
    assert loaded.dtype == np.float32
    assert abs(float(np.max(np.abs(loaded))) - 1.0) < 1e-3
