import json
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from conftest import FakeSynth, FakeTranslator, REF_TEXT, make_wav
from voice_talk.server import Deps, create_app


@pytest.fixture
def client(good_voice, tmp_path):
    deps = Deps(voices=good_voice, synth=FakeSynth(), stt=None, translator_factory=lambda b: FakeTranslator(),
                outputs_dir=tmp_path / "outputs", tts_name="fake")
    with TestClient(create_app(deps), base_url="http://127.0.0.1:8765") as c:
        yield c


H = {"host": "127.0.0.1:8765"}


def recv_until(ws, pred, limit=30):
    seen = []
    for _ in range(limit):
        m = ws.receive()
        if m.get("bytes") is not None:
            seen.append(("bytes", len(m["bytes"])))
            continue
        d = json.loads(m["text"])
        seen.append(d)
        if pred(d):
            return seen
    raise AssertionError(f"never matched; saw {seen}")


def test_message_contract_end_to_end(client):
    with client.websocket_connect("/ws", headers=H) as ws:
        assert json.loads(ws.receive_text()) == {"type": "state", "state": "ready"}
        ws.send_json({"type": "start", "voice": "alice", "source": "en", "target": "fr"})
        seen = recv_until(ws, lambda d: d.get("type") == "chunk_done")  # disclosure first
        types = [s["type"] if isinstance(s, dict) else s[0] for s in seen]
        assert types[:2] == ["started", "state"] and "disclosure" in types
        audio = next(s for s in seen if isinstance(s, dict) and s["type"] == "audio")
        assert audio["format"] == "pcm_s16le" and audio["sample_rate"] == 24000 and audio["disclosure"] is True
        assert ("bytes", audio["samples"] * 2) in seen
        ws.send_json({"type": "text", "text": "Hello friend. "})
        seen = recv_until(ws, lambda d: d.get("type") == "chunk_done" and d["seq"] == 2)
        by = {s["type"]: s for s in seen if isinstance(s, dict)}
        assert by["source"]["text"] == "Hello friend." and by["translation"]["text"] == "[fr] Hello friend."
        assert by["audio"]["disclosure"] is False
        ws.send_json({"type": "stop"})
        recv_until(ws, lambda d: d.get("type") == "stopped")


def test_start_without_consent_is_refused(client, good_voice):
    (good_voice.root / "alice" / "consent.json").unlink()
    with client.websocket_connect("/ws", headers=H) as ws:
        ws.receive_text()
        ws.send_json({"type": "start", "voice": "alice", "source": "en", "target": "fr"})
        err = json.loads(ws.receive_text())
        assert err["type"] == "error" and err["code"] == "consent_required" and "refused" in err["message"]
        ws.send_json({"type": "text", "text": "Hi. "})
        assert json.loads(ws.receive_text())["code"] == "no_session"


def test_disclosure_off_needs_ack_and_bad_messages(client):
    with client.websocket_connect("/ws", headers=H) as ws:
        ws.receive_text()
        ws.send_json({"type": "start", "voice": "alice", "disclosure": False})
        assert json.loads(ws.receive_text())["code"] == "disclosure_required"
        ws.send_text("not json")
        assert json.loads(ws.receive_text())["code"] == "bad_message"
        ws.send_json({"type": "start", "voice": "alice", "source": "xx"})
        assert json.loads(ws.receive_text())["code"] == "bad_request"


def test_foreign_origin_and_host_are_rejected(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={**H, "origin": "https://evil.example"}) as ws:
            ws.receive_text()
    assert client.get("/api/voices", headers={"host": "evil.example"}).status_code == 403


def test_voice_api_consent_required(client):
    files = {"audio": ("r.wav", make_wav(), "audio/wav")}
    r = client.post("/api/voices", data={"name": "bob", "ref_text": REF_TEXT, "speaker_name": "Bob", "consent": "false"}, files=files)
    assert r.status_code == 403
    r = client.post("/api/voices", data={"name": "bob", "ref_text": REF_TEXT, "speaker_name": "Bob", "consent": "true"}, files=files)
    assert r.status_code == 200 and r.json()["name"] == "bob"
    assert {v["name"] for v in client.get("/api/voices").json()} == {"alice", "bob"}
    assert client.get("/api/config").json()["languages"]["ja"] == "Japanese"
    assert client.delete("/api/voices/bob").status_code == 200


def test_converse_mode_over_websocket(good_voice, tmp_path):
    from conftest import FakeLLM
    deps = Deps(voices=good_voice, synth=FakeSynth(), stt=None, translator_factory=lambda b: FakeTranslator(),
                chat_factory=lambda b: FakeLLM(["Nice to meet you. Ask me anything."]),
                outputs_dir=tmp_path / "o", tts_name="fake")
    with TestClient(create_app(deps), base_url="http://127.0.0.1:8765") as c:
        assert c.get("/api/personas").json()["default"] == "friendly"
        with c.websocket_connect("/ws", headers=H) as ws:
            ws.receive_text()
            ws.send_json({"type": "start", "mode": "converse", "voice": "alice", "lang": "en", "persona": "friendly",
                          "disclosure": False, "disclosure_ack": True})
            seen = recv_until(ws, lambda d: d.get("type") == "started")
            assert seen[-1]["mode"] == "converse"
            ws.send_json({"type": "say", "text": "Hello bot"})
            seen = recv_until(ws, lambda d: d.get("type") == "turn")
            types = [s["type"] for s in seen if isinstance(s, dict)]
            assert "user" in types and "bot_delta" in types and "audio" in types
            ws.send_json({"type": "interrupt"})
            recv_until(ws, lambda d: d.get("type") == "stopped")
        with c.websocket_connect("/ws", headers=H) as ws:  # a bad persona is a clean error, not a crash
            ws.receive_text()
            ws.send_json({"type": "start", "mode": "converse", "voice": "alice", "persona": "../etc"})
            assert json.loads(ws.receive_text())["code"] == "bad_request"


def test_converse_start_reports_an_unreachable_model_server(good_voice, tmp_path):
    """A dead Ollama/LM Studio is reported when the session starts (with what to do), not as 'Connection error.' mid-call."""
    from conftest import FakeLLM

    class DownLLM(FakeLLM):
        def check(self):
            raise RuntimeError("Connection error.")

    class UpLLM(FakeLLM):
        def check(self):
            return None

    backends = {"ollama": DownLLM(), "lmstudio": UpLLM(["Hello there."])}
    deps = Deps(voices=good_voice, synth=FakeSynth(), stt=None, translator_factory=lambda b: FakeTranslator(),
                chat_factory=lambda b: backends[b], outputs_dir=tmp_path / "o", tts_name="fake")
    start = {"type": "start", "mode": "converse", "voice": "alice", "persona": "friendly", "disclosure": False, "disclosure_ack": True}
    with TestClient(create_app(deps), base_url="http://127.0.0.1:8765") as c:
        with c.websocket_connect("/ws", headers=H) as ws:
            ws.receive_text()
            ws.send_json({**start, "backend": "ollama"})
            err = json.loads(ws.receive_text())
            assert err["type"] == "error" and err["code"] == "llm_unavailable"
            assert "ollama" in err["message"].lower() and "Connection error" in err["message"]
        with c.websocket_connect("/ws", headers=H) as ws:  # the other backend still starts normally
            ws.receive_text()
            ws.send_json({**start, "backend": "lmstudio"})
            assert recv_until(ws, lambda d: d.get("type") == "started")
