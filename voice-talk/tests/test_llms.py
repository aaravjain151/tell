"""Backend-agnostic local LLMs: any OpenAI-compatible server on loopback, discovered at runtime, model picked by name or auto."""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from conftest import FakeLLM, FakeSynth, FakeTranslator
from voice_talk import llms
from voice_talk.chat import ChatLLM
from voice_talk.server import Deps, create_app
from voice_talk.translate import BACKENDS, RemoteEndpointError


class FakeModels:
    def __init__(self, ids):
        self.ids = ids

    def list(self):
        return [SimpleNamespace(id=i) for i in self.ids]


class FakeClient:
    def __init__(self, ids):
        self.models = FakeModels(ids)

    def with_options(self, **kw):
        return self


def lister_for(up: dict):
    def lister(base_url, timeout=1.0):
        for url, ids in up.items():
            if base_url == url:
                return ids
        raise ConnectionError("refused")
    return lister


def test_discover_marks_each_server_reachable_or_not_and_lists_models():
    up = {"http://127.0.0.1:1234/v1": ["model-a", "text-embedding-nomic"], "http://127.0.0.1:11434/v1": ["llama3.2:3b"]}
    found = {s["id"]: s for s in llms.discover(BACKENDS, lister_for(up))}
    assert found["lmstudio"]["reachable"] and found["lmstudio"]["models"] == ["model-a"]  # embedding models are not chat models
    assert found["ollama"]["reachable"] and found["ollama"]["models"] == ["llama3.2:3b"]
    assert not found["llamacpp"]["reachable"] and found["llamacpp"]["models"] == []
    assert all(s["label"] and s["base_url"].startswith("http://127.0.0.1") for s in found.values())


def test_custom_endpoint_is_registered_but_only_on_loopback():
    saved = dict(BACKENDS)
    try:
        llms.register_custom("http://localhost:9999/v1", "my-model")
        assert BACKENDS["custom"]["base_url"] == "http://localhost:9999/v1" and BACKENDS["custom"]["model"] == "my-model"
        with pytest.raises(RemoteEndpointError):
            llms.register_custom("https://api.example.com/v1")
    finally:
        BACKENDS.clear(); BACKENDS.update(saved)


def test_check_auto_picks_the_first_chat_model_when_none_is_named():
    c = ChatLLM(client=FakeClient(["text-embedding-x", "qwen-big", "gemma"]), model=None)
    c.check()
    assert c.model == "qwen-big"


def test_check_names_the_available_models_when_the_chosen_one_is_missing():
    c = ChatLLM(client=FakeClient(["qwen-big", "gemma"]), model="does-not-exist")
    with pytest.raises(RuntimeError) as e:
        c.check()
    assert "does-not-exist" in str(e.value) and "qwen-big" in str(e.value) and "gemma" in str(e.value)
    with pytest.raises(RuntimeError, match="no models"):
        ChatLLM(client=FakeClient([]), model=None).check()


def mk_client(good_voice, tmp_path, **kw):
    deps = Deps(voices=good_voice, synth=FakeSynth(), stt=None, translator_factory=lambda b: FakeTranslator(),
                outputs_dir=tmp_path / "o", tts_name="fake", **kw)
    return TestClient(create_app(deps), base_url="http://127.0.0.1:8765")


def test_api_llm_lists_servers_models_and_the_default(good_voice, tmp_path):
    up = {"http://127.0.0.1:1234/v1": ["qwen-big", "gemma"]}
    with mk_client(good_voice, tmp_path, llm_lister=lister_for(up), default_backend="lmstudio", llm_model="gemma") as c:
        j = c.get("/api/llm").json()
    assert j["default_backend"] == "lmstudio" and j["default_model"] == "gemma"
    by = {s["id"]: s for s in j["servers"]}
    assert by["lmstudio"]["reachable"] and by["lmstudio"]["models"] == ["qwen-big", "gemma"]
    assert not by["ollama"]["reachable"]


def test_start_can_pick_a_model_and_an_unknown_backend_is_a_clean_error(good_voice, tmp_path):
    chat = FakeLLM(["Hello there."])
    chat.model = "default-model"
    with mk_client(good_voice, tmp_path, chat_factory=lambda b: chat) as c:
        H = {"host": "127.0.0.1:8765"}
        start = {"type": "start", "mode": "converse", "voice": "alice", "persona": "friendly", "disclosure": False, "disclosure_ack": True}
        with c.websocket_connect("/ws", headers=H) as ws:
            ws.receive_text()
            ws.send_json({**start, "backend": "lmstudio", "model": "qwen-big"})
            for _ in range(30):
                if json.loads(ws.receive_text()).get("type") == "started":
                    break
            assert chat.model == "qwen-big"
