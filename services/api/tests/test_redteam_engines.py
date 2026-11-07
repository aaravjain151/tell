"""Engine clients are exercised with a fake opener: no network, no credits (rule: never call TTS in tests)."""
import io
import json
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "redteam"))
import engines  # noqa: E402


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_opener(payload: bytes, seen: list):
    def opener(req, timeout=0):
        seen.append(req)
        return FakeResp(payload)
    return opener


def _wav_info(path: Path):
    with wave.open(str(path), "rb") as w:
        return w.getframerate(), w.getnchannels(), w.getnframes()


def test_elevenlabs_wraps_pcm_and_sends_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k-test")
    seen: list = []
    out = tmp_path / "a.wav"
    engines.elevenlabs("hello there", out, voice_id="VOICE1", opener=fake_opener(b"\x00\x01" * 1600, seen))
    req = seen[0]
    assert "VOICE1" in req.full_url and "output_format=pcm_16000" in req.full_url
    assert req.get_header("Xi-api-key") == "k-test"
    assert json.loads(req.data)["text"] == "hello there"
    assert _wav_info(out) == (16000, 1, 1600)


def test_voicestudio_posts_openai_style_body(tmp_path, monkeypatch):
    monkeypatch.delenv("VOICESTUDIO_URL", raising=False)
    seen: list = []
    out = tmp_path / "v.wav"
    engines.voicestudio("hi", out, voice_id="prof-7", opener=fake_opener(engines.wrap_pcm16(b"\x00\x00" * 800), seen))
    assert seen[0].full_url == "http://127.0.0.1:3900/v1/audio/speech"
    body = json.loads(seen[0].data)
    assert body["input"] == "hi" and body["voice"] == "prof-7" and body["response_format"] == "wav"
    assert _wav_info(out)[2] == 800


def test_voicestudio_omits_voice_when_unset(tmp_path):
    seen: list = []
    engines.voicestudio("hi", tmp_path / "v.wav", opener=fake_opener(engines.wrap_pcm16(b"\x00\x00" * 8), seen))
    assert "voice" not in json.loads(seen[0].data)


def test_unavailable_reasons(monkeypatch):
    monkeypatch.delenv("GRADIUM_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert "GRADIUM_API_KEY" in engines.unavailable_reason("gradium")
    assert "ELEVENLABS_API_KEY" in engines.unavailable_reason("elevenlabs")

    def refuse(req, timeout=0):
        raise ConnectionRefusedError("nope")
    assert "not reachable" in engines.unavailable_reason("voicestudio", opener=refuse)
    assert engines.unavailable_reason("voicestudio", opener=fake_opener(b"[]", [])) is None
    assert "unknown" in engines.unavailable_reason("bogus")


def test_analysis_package_never_mentions_tts_services():
    """Privacy: TTS clients live in tools/, outside the analysis package (tell/)."""
    banned = ("elevenlabs", "/v1/audio/speech", "xi-api-key", "api.gradium")  # VoiceStudio STT is allowed (D-009); its TTS endpoint is not
    for p in (ROOT / "services" / "api" / "tell").rglob("*.py"):
        src = p.read_text().lower()
        assert not any(b in src for b in banned), p


def test_qwen3tts_clones_from_ref_with_fake_model(tmp_path):
    import numpy as np
    engines._qwen = None
    ref = tmp_path / "ref.wav"
    ref.write_bytes(engines.wrap_pcm16(b"\x00\x00" * 160))
    calls = {}

    class FakeModel:
        def generate_voice_clone(self, text, language, ref_audio, ref_text):
            calls.update(text=text, language=language, ref_audio=ref_audio, ref_text=ref_text)
            return [np.full(2400, 0.5, dtype=np.float32)], 24000

    out = tmp_path / "q.wav"
    engines.qwen3tts("say this", out, voice_id=str(ref), voice_text="exact words", loader=lambda: FakeModel())
    assert calls == {"text": "say this", "language": "English", "ref_audio": str(ref), "ref_text": "exact words"}
    assert _wav_info(out) == (24000, 1, 2400)
    engines._qwen = None


def test_qwen3tts_refuses_without_ref_or_text(tmp_path):
    import pytest
    with pytest.raises(RuntimeError, match="--voice"):
        engines.qwen3tts("x", tmp_path / "o.wav", voice_id="", voice_text="words")
    ref = tmp_path / "r.wav"
    ref.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="voice-text"):
        engines.qwen3tts("x", tmp_path / "o.wav", voice_id=str(ref), voice_text=" ")


def test_wild_eval_reads_engine_folders_and_human_dir(tmp_path):
    """A subfolder per engine plus human/ must all be found (the old flat glob skipped them)."""
    import sys as _s
    _s.path.insert(0, str(ROOT / "services" / "api"))
    from eval import run_eval
    from pathlib import Path as P
    assert run_eval._engine(P("voicestudio/scam_irs.wav"), "scam_irs") == "voicestudio"
    assert run_eval._engine(P("ai__gradium__scam_irs.wav"), "ai__gradium__scam_irs") == "gradium"
    assert run_eval._label(P("human/ana/scam_irs.wav"), "scam_irs") == "human"
    assert run_eval._label(P("elevenlabs/scam_irs.wav"), "scam_irs") == "ai"
    assert run_eval._condition("scam_irs.opus8k") == ("opus-8k", "scam_irs")
