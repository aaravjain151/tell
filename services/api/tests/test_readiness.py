"""Readiness never runs inference or reaches a real engine in tests."""
import io
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from tests.conftest import AUTH

from tell import localhost, net_monitor, offline_guard, privacy, readiness, stt
from tell.main import app
from tell.signals import neural


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for name in ("TELL_STT", "TELL_WHISPER_MODEL", "HF_SPOOF_MODEL", "LLM_PROVIDER",
                 "OLLAMA_URL", "OLLAMA_MODEL", "VOICESTUDIO_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(stt, "_model", None)
    monkeypatch.setattr(neural, "_hf", None)
    monkeypatch.setattr(net_monitor, "cumulative_report", lambda: {"os_check": "ok"})
    monkeypatch.setattr(localhost._OPENER, "open", Mock(side_effect=OSError("down")))
    monkeypatch.setenv("TELL_WARMUP", "0")


def engine(monkeypatch, responses):
    def open_request(req, timeout):
        assert req.get_method() == "GET"
        assert req.data is None
        assert 0 < timeout <= 1.5
        return io.BytesIO(json.dumps(responses[req.full_url.rsplit("/", 1)[-1]]).encode())
    opener = Mock(side_effect=open_request)
    monkeypatch.setattr(localhost._OPENER, "open", opener)
    return opener


def test_unset_off_and_no_stt_not_ready():
    result = readiness.report()
    assert not result["ready"]
    assert result["degraded"] == []
    assert all(c["status"] == "off" for c in result["components"].values())


@pytest.mark.parametrize("env,component", [("HF_SPOOF_MODEL", "anti_spoof_hf"),
                                            ("TELL_WHISPER_MODEL", "stt")])
@pytest.mark.parametrize("cached", [False, True])
def test_configured_model_cache(monkeypatch, env, component, cached):
    monkeypatch.setenv(env, "test/model")
    probe = Mock(return_value="/cached/model" if cached else None)
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(try_to_load_from_cache=probe))
    result = readiness.report()
    assert result["components"][component] == {
        "status": "degraded", "detail": "cached but not loaded yet" if cached else "not cached, run make models"}
    assert component in result["degraded"]
    assert not result["ready"]
    probe.assert_called()


def test_local_directory_cache(monkeypatch, tmp_path):
    (tmp_path / "model.bin").touch()
    monkeypatch.setenv("TELL_WHISPER_MODEL", str(tmp_path))
    assert readiness.report()["components"]["stt"]["detail"] == "cached but not loaded yet"


def test_negative_cache_sentinel_is_not_cached(monkeypatch):
    monkeypatch.setenv("HF_SPOOF_MODEL", "test/model")
    monkeypatch.setitem(sys.modules, "huggingface_hub",
                        SimpleNamespace(try_to_load_from_cache=lambda *args: object()))
    assert readiness.report()["components"]["anti_spoof_hf"]["detail"] == "not cached, run make models"


def test_ollama_down(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    assert readiness.report()["components"]["llm"]["status"] == "degraded"


@pytest.mark.parametrize("resident,cached,expected", [(True, True, "ready"), (False, True, "degraded"),
                                                      (False, False, "degraded")])
def test_ollama_status_without_inference(monkeypatch, resident, cached, expected):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    models = [{"name": "qwen2.5:3b"}]
    opener = engine(monkeypatch, {"ps": {"models": models if resident else []},
                                  "tags": {"models": models if cached else []}})
    before = privacy.report()
    result = readiness.report()
    assert result["components"]["llm"]["status"] == expected
    assert not result["ready"]  # A working LLM is not an STT path.
    assert opener.call_count == (1 if resident else 2)
    assert privacy.report() == before


@pytest.mark.parametrize("mode", ["auto", "voicestudio"])
def test_voicestudio(monkeypatch, mode):
    monkeypatch.setenv("TELL_STT", mode)
    monkeypatch.setattr(stt, "_model", object())
    engine(monkeypatch, {"models": {"data": [{"id": "whisper-1", "loaded": True}]}})
    result = readiness.report()
    assert result["components"]["voicestudio_stt"]["status"] == "ready"
    assert result["ready"]


def test_broken_configured_component_blocks_ready(monkeypatch):
    monkeypatch.setenv("TELL_STT", "auto")
    monkeypatch.setattr(stt, "_model", object())
    result = readiness.report()
    assert result["components"]["stt"]["status"] == "ready"
    assert result["degraded"] == ["voicestudio_stt"]
    assert not result["ready"]


@pytest.mark.parametrize("models", [[], [{"id": "whisper-1"}], [{"id": "whisper-1", "loaded": False}]])
def test_voicestudio_advertisement_does_not_prove_loaded(monkeypatch, models):
    monkeypatch.setenv("TELL_STT", "voicestudio")
    engine(monkeypatch, {"models": {"data": models}})
    result = readiness.report()
    assert result["components"]["voicestudio_stt"]["status"] == "degraded"
    assert not result["ready"]


@pytest.mark.parametrize("alias,repo", [
    ("base.en", "Systran/faster-whisper-base.en"),
    ("large", "Systran/faster-whisper-large-v3"),
    ("turbo", "mobiuslabsgmbh/faster-whisper-large-v3-turbo"),
    ("distil-large-v3", "Systran/faster-distil-whisper-large-v3"),
    ("distil-large-v3.5", "distil-whisper/distil-large-v3.5-ct2"),
])
def test_whisper_cache_aliases(monkeypatch, alias, repo):
    monkeypatch.setenv("TELL_WHISPER_MODEL", alias)
    cache = Mock(return_value=False)
    monkeypatch.setattr(readiness, "_cached", cache)
    readiness.report()
    cache.assert_called_once_with(repo, ("model.bin",))


def test_schema_endpoint_never_loads_models(monkeypatch):
    load = Mock(side_effect=AssertionError("must not load"))
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=load))
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(
        AutoFeatureExtractor=SimpleNamespace(from_pretrained=load),
        AutoModelForAudioClassification=SimpleNamespace(from_pretrained=load)))
    monkeypatch.setitem(sys.modules, "huggingface_hub",
                        SimpleNamespace(try_to_load_from_cache=lambda *args: None))
    monkeypatch.setenv("TELL_STT", "whisper")
    monkeypatch.setenv("HF_SPOOF_MODEL", "test/model")
    with TestClient(app, headers=AUTH) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"ready", "degraded", "components", "offline_models", "os_network", "privacy_posture", "thresholds_version"}
    assert set(result["components"]) == {"stt", "anti_spoof_hf", "pellav2", "llm", "voicestudio_stt"}
    for component in result["components"].values():
        assert set(component) == {"status", "detail"}
        assert component["status"] in ("ready", "degraded", "off")
        assert isinstance(component["detail"], str)
    assert isinstance(result["offline_models"], bool)
    assert isinstance(result["thresholds_version"], str)
    load.assert_not_called()


def test_loaded_models_ready_without_cache_access(monkeypatch):
    monkeypatch.setenv("TELL_STT", "whisper")
    monkeypatch.setenv("HF_SPOOF_MODEL", "test/model")
    monkeypatch.setattr(stt, "_model", object())
    monkeypatch.setattr(neural, "_hf", (object(), object()))
    cache = Mock(side_effect=AssertionError("loaded models need no cache check"))
    monkeypatch.setattr(readiness, "_cached", cache)
    assert readiness.report()["ready"]
    cache.assert_not_called()


def test_failures_are_isolated(monkeypatch):
    def broken(*args):
        raise RuntimeError("broken")
    monkeypatch.setenv("TELL_STT", "whisper")
    monkeypatch.setenv("HF_SPOOF_MODEL", "test/model")
    monkeypatch.setattr(readiness, "_cached", broken)
    monkeypatch.setattr(net_monitor, "cumulative_report", broken)
    monkeypatch.setattr(offline_guard, "is_enforced", broken)
    result = TestClient(app, headers=AUTH).get("/ready").json()
    assert not result["ready"]
    assert result["degraded"] == ["stt", "anti_spoof_hf"]
    assert result["os_network"]["os_check"] == "unavailable"
    assert result["offline_models"] is False


def test_external_engine_url_refused_before_opener(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "https://example.com")
    opener = engine(monkeypatch, {})
    assert readiness.report()["components"]["llm"]["status"] == "degraded"
    opener.assert_not_called()


def test_report_includes_pellav2_and_the_privacy_posture(monkeypatch):
    from tell import readiness
    monkeypatch.delenv("PELLA_MODEL", raising=False)
    monkeypatch.setenv("TELL_DEBUG_SAVE", "1")
    r = readiness.report()
    assert r["components"]["pellav2"]["status"] == "off"
    assert r["privacy_posture"]["debug_save"] is True and set(r["privacy_posture"]) >= {"debug_save", "llm_provider_anthropic", "gradium_key_set"}


def test_pellav2_never_loads_a_model_while_reporting(monkeypatch):
    from tell import readiness
    from tell.signals import pella
    monkeypatch.setenv("PELLA_MODEL", pella.REPO)
    monkeypatch.setattr(pella, "_model", None); monkeypatch.setattr(pella, "_error", "")
    monkeypatch.setattr(pella, "weights_path", lambda: None)
    monkeypatch.setattr(pella, "_load", lambda: (_ for _ in ()).throw(AssertionError("readiness must not load the model")))
    assert readiness.report()["components"]["pellav2"] == {"status": "degraded", "detail": "not cached, run make models"}
