from fastapi.testclient import TestClient

from tell.main import app
from tests.synth import make_call, to_wav_bytes

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"]


def test_analyze_requires_input():
    assert client.post("/analyze").status_code == 400


def test_analyze_audio_and_transcript():
    wav = to_wav_bytes(make_call("tts", seed=21))
    r = client.post("/analyze", files={"audio": ("clip.wav", wav, "audio/wav")},
                    data={"transcript": "Hello. I completely understand your concern. Certainly, I am here to help. Is there anything else I can help you with?"})
    assert r.status_code == 200
    body = r.json()
    assert body["tier"] in ("ai_undisclosed", "unsure") and body["tells"] and body["signature"]


def test_bad_audio_is_415():
    r = client.post("/analyze", files={"audio": ("x.bin", b"not audio at all", "application/octet-stream")})
    assert r.status_code == 415


def test_verdict_returns_the_analysed_transcript():
    """The UI marks up the caller's words in place, so the verdict must carry the text that was analysed."""
    from fastapi.testclient import TestClient
    from tell.main import app
    text = "Grandma it's me, I need bail money right now, please don't tell mom."
    r = TestClient(app).post("/analyze", data={"transcript": text}).json()
    assert r["transcript"] == text
