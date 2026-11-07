"""The privacy guarantee is a test, not a promise.

1. No module on the analysis path imports anything that can open a network connection.
2. The egress recorder refuses audio by construction.
3. Verdict signatures verify and are bound to the clip fingerprint.
"""
import re
from pathlib import Path

import pytest

from doublespeak import privacy, pipeline
from tests.synth import make_call, to_wav_bytes

ANALYSIS_PATH = ["doublespeak/audio.py", "doublespeak/pipeline.py", "doublespeak/scorer.py", "doublespeak/thresholds.py", "doublespeak/types.py",
                 "doublespeak/signals/acoustic.py", "doublespeak/signals/script.py", "doublespeak/signals/intent.py"]
NETWORK = re.compile(r"^\s*(import|from)\s+(socket|http|urllib|requests|httpx|aiohttp|websockets|ssl)\b", re.M)


def test_analysis_path_has_no_network_imports():
    root = Path(__file__).resolve().parents[1]
    for rel in ANALYSIS_PATH:
        src = (root / rel).read_text()
        assert not NETWORK.search(src), f"{rel} imports a network library"


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
