"""Record-on-the-fly voice enrolment: the page records a clip, /api/voices/transcribe returns a draft transcript
(local faster-whisper) that the user edits, then the normal consent-gated POST /api/voices stores the voice."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from conftest import FakeSynth, FakeTranslator, make_wav
from voice_talk.server import Deps, create_app


class FakeSTT:
    def __init__(self, text="hello this is my voice"):
        self.text, self.calls = text, []

    def transcribe(self, audio, language):
        self.calls.append((audio, language))
        return self.text


def mk_client(good_voice, tmp_path, stt):
    deps = Deps(voices=good_voice, synth=FakeSynth(), stt=stt, translator_factory=lambda b: FakeTranslator(),
                outputs_dir=tmp_path / "outputs", tts_name="fake")
    return TestClient(create_app(deps), base_url="http://127.0.0.1:8765")


def test_transcribe_returns_draft_text_and_duration(good_voice, tmp_path):
    stt = FakeSTT()
    with mk_client(good_voice, tmp_path, stt) as c:
        r = c.post("/api/voices/transcribe", data={"lang": "en"}, files={"audio": ("rec.wav", make_wav(5.0), "audio/wav")})
    assert r.status_code == 200, r.text
    assert r.json() == {"text": "hello this is my voice", "duration_s": 5.0}
    audio, lang = stt.calls[0]
    assert lang == "en" and audio.dtype == np.float32 and abs(len(audio) - 5 * 16000) < 10  # 16 kHz mono float


def test_transcribe_resamples_other_rates_to_16k(good_voice, tmp_path):
    stt = FakeSTT()
    with mk_client(good_voice, tmp_path, stt) as c:
        r = c.post("/api/voices/transcribe", files={"audio": ("rec.wav", make_wav(4.0, sr=48000), "audio/wav")})
    assert r.status_code == 200
    assert abs(len(stt.calls[0][0]) - 4 * 16000) < 10


def test_transcribe_without_stt_is_503(good_voice, tmp_path):
    with mk_client(good_voice, tmp_path, None) as c:
        r = c.post("/api/voices/transcribe", files={"audio": ("rec.wav", make_wav(), "audio/wav")})
    assert r.status_code == 503


@pytest.mark.parametrize("payload,status", [(b"not a wav file", 400), (b"x" * (21 * 1024 * 1024), 413)])
def test_transcribe_rejects_bad_uploads(good_voice, tmp_path, payload, status):
    with mk_client(good_voice, tmp_path, FakeSTT()) as c:
        r = c.post("/api/voices/transcribe", files={"audio": ("rec.wav", payload, "audio/wav")})
    assert r.status_code == status


def test_transcribe_refuses_clips_over_the_voice_limit(good_voice, tmp_path):
    with mk_client(good_voice, tmp_path, FakeSTT()) as c:
        r = c.post("/api/voices/transcribe", files={"audio": ("rec.wav", make_wav(31.0), "audio/wav")})
    assert r.status_code == 400 and "30" in r.json()["detail"]


def test_recorded_clip_still_needs_consent_to_become_a_voice(good_voice, tmp_path):
    """Transcribing creates nothing on disk and grants nothing: enrolment still goes through the consent gate."""
    wav = make_wav(6.0)
    with mk_client(good_voice, tmp_path, FakeSTT()) as c:
        text = c.post("/api/voices/transcribe", files={"audio": ("r.wav", wav, "audio/wav")}).json()["text"]
        assert {v["name"] for v in c.get("/api/voices").json()} == {"alice"}
        form = {"name": "me", "ref_text": text, "speaker_name": "Me"}
        assert c.post("/api/voices", data={**form, "consent": "false"}, files={"audio": ("r.wav", wav, "audio/wav")}).status_code == 403
        assert c.post("/api/voices", data={**form, "consent": "true"}, files={"audio": ("r.wav", wav, "audio/wav")}).status_code == 200
