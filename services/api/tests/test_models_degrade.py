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


def test_model_loads_are_cache_only(monkeypatch):
    """Even a fully cached model contacts huggingface.co for an update check unless told not to. Runtime loads must never do that;
    `make models` is the only place that downloads."""
    transformers = pytest.importorskip("transformers")
    faster_whisper = pytest.importorskip("faster_whisper")
    seen = {}

    def spy_hf(name, **kw):
        seen.setdefault("hf", []).append(kw.get("local_files_only"))
        raise OSError("stop")

    def spy_whisper(*a, **kw):
        seen["whisper"] = kw.get("local_files_only")
        raise OSError("stop")
    monkeypatch.setattr(transformers.AutoFeatureExtractor, "from_pretrained", spy_hf)
    monkeypatch.setattr(transformers.AutoModelForAudioClassification, "from_pretrained", spy_hf)
    monkeypatch.setattr(faster_whisper, "WhisperModel", spy_whisper)
    monkeypatch.setenv("HF_SPOOF_MODEL", "nobody/not-a-model")
    for mod, attr, val in ((neural, "_hf", None), (neural, "_hf_error", ""), (stt, "_model", None), (stt, "_model_failed", False)):
        monkeypatch.setattr(mod, attr, val)
    neural.hf_vote(np.zeros(16000 * 5, dtype=np.float32))
    stt.transcribe(np.zeros(16000 * 3, dtype=np.float32))
    assert seen["hf"] and all(v is True for v in seen["hf"]) and seen["whisper"] is True
