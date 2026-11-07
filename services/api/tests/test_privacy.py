"""The privacy guarantee is a test, not a promise.

1. No module on the analysis path imports anything that can open a network connection.
2. The egress recorder refuses audio by construction.
3. Verdict signatures verify and are bound to the clip fingerprint.
"""
import io
import json
import re
from pathlib import Path

import pytest

from tell import localhost, privacy, pipeline, stt
from tests.synth import make_call, to_wav_bytes

ANALYSIS_PATH = ["tell/audio.py", "tell/stt.py", "tell/pipeline.py", "tell/scorer.py", "tell/thresholds.py", "tell/types.py",
                 "tell/signals/acoustic.py", "tell/signals/script.py", "tell/signals/intent.py"]
NETWORK = re.compile(r"^\s*(import|from)\s+(socket|http|urllib|requests|httpx|aiohttp|websockets|ssl)\b", re.M)


def test_analysis_path_has_no_network_imports():
    root = Path(__file__).resolve().parents[1]
    for rel in ANALYSIS_PATH:
        src = (root / rel).read_text()
        assert not NETWORK.search(src), f"{rel} imports a network library"


SOCKET_ALLOWLIST = {"localhost.py", "llm.py", "speak.py"}


def test_only_allowlisted_modules_may_open_sockets():
    """Strict: any module under tell/ with a network import must be in the allowlist (D-009)."""
    root = Path(__file__).resolve().parents[1] / "tell"
    offenders = {p.name for p in root.rglob("*.py") if NETWORK.search(p.read_text())}
    assert offenders <= SOCKET_ALLOWLIST, f"unexpected network imports: {offenders - SOCKET_ALLOWLIST}"
    assert "localhost.py" in offenders


class FakeResp:
    def __init__(self, payload): self._b = json.dumps(payload).encode()
    def read(self): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False


class FakeOpener:
    def __init__(self, payload=None, exc=None): self.payload, self.exc, self.requests = payload, exc, []
    def __call__(self, req, timeout=None):
        self.requests.append((req, timeout))
        if self.exc: raise self.exc
        return FakeResp(self.payload)


@pytest.mark.parametrize("url", ["http://example.com/x", "http://10.0.0.5:3900/x", "http://192.168.1.2/x",
                                 "http://127.0.0.1.evil.com/x", "ftp://127.0.0.1/x", "http:///x"])
def test_non_loopback_is_rejected_and_not_counted(url):
    privacy.reset()
    op = FakeOpener({"text": "x"})
    with pytest.raises(localhost.NotLoopbackError):
        localhost.post_json(url, {"a": 1}, opener=op)
    with pytest.raises(localhost.NotLoopbackError):
        localhost.post_multipart(url, {"model": "m"}, "file", "a.wav", b"RIFF", opener=op)
    assert op.requests == [] and privacy.report()["localhost_requests"] == 0


@pytest.mark.parametrize("url", ["http://127.0.0.1:3900/x", "http://localhost:3900/x", "http://[::1]:3900/x"])
def test_loopback_is_accepted_and_counted(url):
    privacy.reset()
    op = FakeOpener({"text": "hi"})
    assert localhost.post_json(url, {"a": 1}, opener=op) == {"text": "hi"}
    assert localhost.post_multipart(url, {"model": "m"}, "file", "a.wav", b"RIFF", opener=op) == {"text": "hi"}
    r = privacy.report()
    assert r["localhost_requests"] == 2 and r["external_requests"] == 0 and r["bytes_sent_external"] == 0


def test_failed_loopback_attempt_is_still_counted():
    privacy.reset()
    with pytest.raises(OSError):
        localhost.post_json("http://127.0.0.1:1/x", {}, opener=FakeOpener(exc=ConnectionRefusedError("no")))
    assert privacy.report()["localhost_requests"] == 1


def test_multipart_shape():
    op = FakeOpener({"text": "ok"})
    localhost.post_multipart("http://127.0.0.1:3900/v1/audio/transcriptions", {"model": "whisper-1"}, "file", "c.wav", b"DATA", opener=op)
    req, _ = op.requests[0]
    assert req.get_method() == "POST" and req.get_header("Content-type").startswith("multipart/form-data; boundary=")
    assert b'name="model"' in req.data and b'name="file"; filename="c.wav"' in req.data and b"DATA" in req.data


def test_voicestudio_stt_used_when_it_answers(monkeypatch):
    monkeypatch.setenv("DOUBLESPEAK_STT", "voicestudio")
    privacy.reset()
    op = FakeOpener({"text": "  this is the voicestudio transcript  "})
    monkeypatch.setattr(localhost.urllib.request, "urlopen", op)
    v = pipeline.analyze(to_wav_bytes(make_call("human", seed=5)), None)
    assert v.egress["context"]["transcript_source"] == "local_voicestudio"
    req, timeout = op.requests[0]
    assert req.full_url.endswith("/v1/audio/transcriptions") and timeout <= 3
    assert req.data[req.data.find(b"RIFF"):][:4] == b"RIFF"   # a real WAV was uploaded
    assert v.egress["caller_audio_bytes_sent"] == 0 and v.egress["bytes_sent_external"] == 0
    assert v.egress["external_requests"] == 0 and v.egress["localhost_requests"] == 1


def test_voicestudio_unreachable_falls_back_silently(monkeypatch):
    monkeypatch.setenv("DOUBLESPEAK_STT", "auto")
    monkeypatch.setattr(stt, "available", lambda: False)
    monkeypatch.setattr(localhost.urllib.request, "urlopen", FakeOpener(exc=ConnectionRefusedError("down")))
    v = pipeline.analyze(to_wav_bytes(make_call("human", seed=5)), None)
    assert "transcript_source" not in v.egress["context"]
    assert v.egress["caller_audio_bytes_sent"] == 0


def test_voicestudio_bad_response_falls_back(monkeypatch):
    monkeypatch.setenv("DOUBLESPEAK_STT", "auto")
    monkeypatch.setattr(stt, "available", lambda: False)
    monkeypatch.setattr(localhost.urllib.request, "urlopen", FakeOpener({"error": "x"}))
    assert stt.transcribe_with_source(make_call("human", seed=5)) == (None, None)


def test_stt_whisper_mode_never_contacts_voicestudio(monkeypatch):
    monkeypatch.setenv("DOUBLESPEAK_STT", "whisper")
    op = FakeOpener({"text": "x"})
    monkeypatch.setattr(localhost.urllib.request, "urlopen", op)
    monkeypatch.setattr(stt, "available", lambda: False)
    assert stt.transcribe_with_source(make_call("human", seed=5)) == (None, None) and op.requests == []


def test_to_wav_roundtrips():
    import wave, numpy as np
    x = np.linspace(-1, 1, 1600, dtype=np.float32)
    with wave.open(io.BytesIO(stt.to_wav(x))) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()) == (16000, 1, 2, 1600)


def test_ollama_non_loopback_refused(monkeypatch):
    from tell import llm
    monkeypatch.setenv("OLLAMA_URL", "http://10.0.0.5:11434")
    privacy.reset()
    tells, cost = llm._ollama("hello there")
    assert tells == [] and "loopback" in cost["error"] and privacy.report()["localhost_requests"] == 0


def test_audio_egress_is_impossible():
    with pytest.raises(privacy.AudioEgressError):
        privacy.record_egress("audio", 10)


def test_analyze_sends_zero_bytes():
    privacy.reset()
    v = pipeline.analyze(to_wav_bytes(make_call("human", seed=5)), "hey, um, just checking in, call me back")
    assert v.egress["bytes_sent_external"] == 0 and v.egress["external_requests"] == 0
    assert v.egress["caller_audio_bytes_sent"] == 0


def test_signature_verifies_and_binds_to_clip():
    wav = to_wav_bytes(make_call("tts", seed=9))
    v = pipeline.analyze(wav, "Hello. I completely understand. Certainly, I can help.")
    payload = {"tier": v.tier, "p_ai": round(v.p_ai, 3), "p_scam": round(v.p_scam, 3),
               "tells": [(t.name, round(t.score, 3)) for t in v.tells], "thresholds_version": v.thresholds_version}
    assert privacy.verify(payload, v.signature)
    assert privacy.audio_fingerprint(wav) in v.signature
    assert not privacy.verify({**payload, "tier": "human"}, v.signature)
