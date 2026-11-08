"""privacy.record_egress is a closed set: known kinds, real non-negative ints, never audio-like."""
import re
from pathlib import Path

import pytest

from tell import privacy


@pytest.mark.parametrize("kind", ["text", "verdict_tts"])
def test_known_kinds_are_counted(kind):
    privacy.reset()
    privacy.record_egress(kind, 12)
    privacy.record_egress(kind, 0)
    r = privacy.report()
    assert r["external_requests"] == 2 and r["bytes_sent_external"] == 12 and r["caller_audio_bytes_sent"] == 0


@pytest.mark.parametrize("kind", ["audio", "Audio", "AUDIO", "audio_chunk", "raw_audio", "caller-audio", "text_audio", "audio/wav"])
def test_audio_like_kinds_raise_audio_error(kind):
    privacy.reset()
    with pytest.raises(privacy.AudioEgressError):
        privacy.record_egress(kind, 10)
    assert privacy.report()["external_requests"] == 0


@pytest.mark.parametrize("kind", ["", "telemetry", "TEXT", "text ", "verdict", "b64", None, 5, b"text"])
def test_unknown_or_non_str_kinds_raise(kind):
    privacy.reset()
    with pytest.raises((ValueError, TypeError)):
        privacy.record_egress(kind, 1)
    assert privacy.report()["external_requests"] == 0


@pytest.mark.parametrize("n", [-1, -10**9, 1.5, 2.0, "5", None, True, False])
def test_bad_byte_counts_raise_and_do_not_count(n):
    privacy.reset()
    with pytest.raises((ValueError, TypeError)):
        privacy.record_egress("text", n)
    r = privacy.report()
    assert r["external_requests"] == 0 and r["bytes_sent_external"] == 0


def test_allowed_kinds_cover_real_callers():
    root = Path(__file__).resolve().parents[1] / "tell"
    used = set()
    for p in root.rglob("*.py"):
        used |= set(re.findall(r'record_egress\(\s*"([^"]+)"', p.read_text()))
    assert used and used <= privacy.ALLOWED_EGRESS_KINDS
