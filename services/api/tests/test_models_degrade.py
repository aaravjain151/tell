"""A model that cannot be loaded (offline + uncached, bad name) must degrade its voter, never fail the request."""
import numpy as np
import pytest

from doublespeak import stt
from doublespeak.signals import neural


def test_hf_voter_degrades_when_the_model_cannot_load(monkeypatch):
    transformers = pytest.importorskip("transformers")
    def boom(*a, **k): raise OSError("offline and not cached")
    monkeypatch.setattr(transformers.AutoFeatureExtractor, "from_pretrained", boom)
    monkeypatch.setattr(transformers.AutoModelForAudioClassification, "from_pretrained", boom)
    monkeypatch.setenv("HF_SPOOF_MODEL", "nobody/not-a-model")
    monkeypatch.setattr(neural, "_hf", None); monkeypatch.setattr(neural, "_hf_error", "")
    t = neural.hf_vote(np.zeros(16000 * 5, dtype=np.float32))
    assert not t.applicable and "make models" in t.evidence
    calls = []
    monkeypatch.setattr(transformers.AutoModelForAudioClassification, "from_pretrained", lambda *a, **k: calls.append(1))
    assert not neural.hf_vote(np.zeros(16000 * 5, dtype=np.float32)).applicable and not calls   # failure is remembered, not retried per request


def test_whisper_degrades_when_the_model_cannot_load(monkeypatch):
    faster_whisper = pytest.importorskip("faster_whisper")
    def boom(*a, **k): raise OSError("offline and not cached")
    monkeypatch.setattr(faster_whisper, "WhisperModel", boom)
    monkeypatch.setattr(stt, "_model", None); monkeypatch.setattr(stt, "_model_failed", False)
    assert stt.transcribe(np.zeros(16000 * 3, dtype=np.float32)) is None
