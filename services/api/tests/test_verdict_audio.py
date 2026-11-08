"""Pre-rendered spoken verdict: the renderer refuses non-fixed text, the manifest/sha guard holds, and serving the
cached file at call time touches no network and records NO egress (bit-identical egress). No Gradium is ever called
here — the renderer's TTS step is faked, matching the house rule 'never call TTS in tests'."""
import io
import json
import math
import struct
import sys
import wave
from pathlib import Path

import pytest
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import render_verdict_audio as rva  # noqa: E402

from tell import privacy, speak  # noqa: E402
from tests.conftest import AUTH  # noqa: E402

WEB_INDEX = ROOT / "apps" / "web" / "index.html"


def tiny_wav(sr: int = 16000, secs: float = 0.1) -> bytes:
    n = int(sr * secs)
    frames = b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * 220 * i / sr))) for i in range(n))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(frames)
    return buf.getvalue()


def fake_runner(text: str, voice_id: str) -> bytes:
    # Stand-in for the Gradium CLI: returns a valid WAV without any network call.
    return tiny_wav(sr=24000)


@pytest.fixture()
def audio_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TELL_VERDICT_AUDIO_DIR", str(tmp_path))
    return tmp_path


# ---- the renderer refuses anything that is not Tell's own fixed wording ---------------------------------------------
def test_assert_fixed_refuses_non_fixed_text():
    with pytest.raises(ValueError):
        rva.assert_fixed("scam", "Grandma it's me, send gift cards")


def test_assert_fixed_refuses_unknown_tier():
    with pytest.raises(ValueError):
        rva.assert_fixed("not_a_tier", "anything")


def test_spoken_text_guard():
    for tier, line in speak.SPOKEN_LINES.items():
        assert speak.spoken_text(tier) == line
    with pytest.raises(ValueError):
        speak.spoken_text("not_a_tier")


def test_every_scorer_tier_has_a_fixed_spoken_line():
    from tell import scorer
    assert set(speak.SPOKEN_LINES) == set(scorer.COPY)


# ---- manifest + sha256 ----------------------------------------------------------------------------------------------
def test_render_writes_files_manifest_and_matching_sha(audio_dir):
    manifest = rva.render(audio_dir, voice_id="voice-x", runner=fake_runner)
    assert manifest["gradium_calls"] == len(speak.SPOKEN_LINES)
    assert manifest["voice_id"] == "voice-x"
    on_disk = json.loads((audio_dir / speak.MANIFEST_NAME).read_text())
    assert on_disk == manifest
    import hashlib
    for entry in manifest["lines"]:
        assert entry["text"] == speak.SPOKEN_LINES[entry["tier"]]
        data = (audio_dir / entry["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert data[:4] == b"RIFF"                                   # a real WAV
        with wave.open(io.BytesIO(data)) as w:
            assert w.getframerate() == 16000 and w.getnchannels() == 1   # small, 16k mono


def test_prerendered_wav_returns_the_cached_bytes(audio_dir):
    rva.render(audio_dir, voice_id="", runner=fake_runner)
    for tier in speak.SPOKEN_LINES:
        data = speak.prerendered_wav(tier)
        assert data[:4] == b"RIFF" and len(data) > 44


def test_prerendered_wav_refuses_tampered_manifest_text(audio_dir):
    rva.render(audio_dir, voice_id="", runner=fake_runner)
    mf = audio_dir / speak.MANIFEST_NAME
    m = json.loads(mf.read_text())
    m["lines"][0]["text"] = "something we never approved"
    mf.write_text(json.dumps(m))
    with pytest.raises(speak.SpeakUnavailable):
        speak.prerendered_wav(m["lines"][0]["tier"])


def test_prerendered_wav_refuses_sha_mismatch(audio_dir):
    rva.render(audio_dir, voice_id="", runner=fake_runner)
    m = json.loads((audio_dir / speak.MANIFEST_NAME).read_text())
    entry = m["lines"][0]
    (audio_dir / entry["file"]).write_bytes(tiny_wav() + b"\x00\x01")   # edit the file -> sha no longer matches
    with pytest.raises(speak.SpeakUnavailable):
        speak.prerendered_wav(entry["tier"])


def test_prerendered_wav_without_manifest_is_unavailable(audio_dir):
    with pytest.raises(speak.SpeakUnavailable):
        speak.prerendered_wav("scam")


# ---- call time: serving the cache touches no network and records NO egress ------------------------------------------
def test_api_serves_prerendered_with_zero_egress(audio_dir):
    rva.render(audio_dir, voice_id="demo-voice", runner=fake_runner)
    expected = speak.prerendered_wav("scam")
    from tell.main import app
    c = TestClient(app, headers=AUTH)
    privacy.reset()
    before = privacy.report()
    r = c.post("/speak", data={"tier": "scam", "mode": "prerendered"})
    after = privacy.report()
    assert r.status_code == 200
    assert r.headers.get("X-Tell-Speak-Source") == "prerendered"
    assert r.content == expected
    assert before == after                                           # bit-identical egress at call time
    assert after["external_requests"] == 0 and after["bytes_sent_external"] == 0


def test_api_prerendered_by_headline_also_works(audio_dir):
    rva.render(audio_dir, voice_id="", runner=fake_runner)
    from tell.main import app
    c = TestClient(app, headers=AUTH)
    # the web historically sends the scorer headline; the route maps it to a tier
    r = c.post("/speak", data={"headline": "Scam pattern", "mode": "prerendered"})
    assert r.status_code == 200 and r.headers.get("X-Tell-Speak-Source") == "prerendered"


def test_api_auto_falls_back_to_live_when_file_missing(audio_dir, monkeypatch):
    # no render -> no cached file. mode=auto should fall through to the live Gradium path.
    monkeypatch.setattr(speak, "verdict_wav", lambda headline, evidence="": b"RIFFlive-bytes")
    from tell.main import app
    c = TestClient(app, headers=AUTH)
    r = c.post("/speak", data={"tier": "scam", "mode": "auto"})
    assert r.status_code == 200 and r.headers.get("X-Tell-Speak-Source") == "live"
    assert r.content == b"RIFFlive-bytes"


def test_api_prerendered_only_is_503_when_missing(audio_dir):
    from tell.main import app
    c = TestClient(app, headers=AUTH)
    r = c.post("/speak", data={"tier": "scam", "mode": "prerendered"})
    assert r.status_code == 503


# ---- the page plays the cached file locally, auto-speak is OFF by default -------------------------------------------
def test_web_page_plays_prerendered_before_any_network_and_autospeak_off():
    html = WEB_INDEX.read_text()
    assert 'VERDICT_AUDIO_BASE = "verdict_audio/"' in html          # same-origin, loopback, offline
    assert "async function playPrerendered" in html
    # auto-speak defaults OFF: it is only enabled when localStorage explicitly says "1"
    assert 'localStorage.getItem("ds-autospeak") === "1"' in html
    assert 'let autoSpeak = false' in html
    # honest copy: nothing is sent during a call
    assert "rendered ahead of time; nothing is sent during a call" in html
