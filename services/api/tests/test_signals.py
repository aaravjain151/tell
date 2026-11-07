import numpy as np
import pytest

from doublespeak import pipeline, thresholds as T
from doublespeak.audio import decode
from doublespeak.signals import acoustic, intent, script
from tests.synth import make_call, to_wav_bytes

HUMAN_TXT = ("Hey, um, it's me. So, yeah, I was gonna call you earlier but I, I got stuck at the store. "
             "Anyway, are we still on for Sunday? Mom said she'd bring the, you know, the pie thing. Okay cool, talk later.")
AI_TXT = ("Hello. I completely understand your concern. I am here to help you today. "
          "To ensure your account security, please note that we will need to verify some information. "
          "Certainly, I can assist with that. Is there anything else I can help you with?")
SCAM_TXT = ("This is Officer Daniels calling from the Social Security fraud department. Your number has been suspended. "
            "You need to act now and stay on the line. Go to the store and buy gift cards, then read me the numbers on the back. "
            "Do not tell anyone about this call, this is confidential.")
DISCLOSED_TXT = ("Hi, this is an automated assistant calling from Lakeside Dental to confirm your appointment on Tuesday at 3 PM. "
                 "Please note that you can press one to confirm or two to reschedule. Certainly, we are happy to help. Thank you.")


def _acoustic_pai(kind: str, seed: int = 1, **kw) -> float:
    x = make_call(kind, seed=seed, **kw)
    tells, _ = acoustic.analyze(x, int(1000 * len(x) / 16000))
    usable = [t for t in tells if t.applicable and t.weight > 0]
    return sum(t.score * t.weight for t in usable) / sum(t.weight for t in usable)


def test_acoustic_separates_human_from_tts():
    h = [_acoustic_pai("human", seed=s) for s in range(3)]
    a = [_acoustic_pai("tts", seed=s) for s in range(3)]
    assert max(h) < T.P_AI_THRESHOLD, h
    assert min(a) >= T.P_AI_THRESHOLD, a


def test_acoustic_still_separates_on_phone_band():
    assert _acoustic_pai("human", seed=7, phone_band=True) < T.P_AI_THRESHOLD
    assert _acoustic_pai("tts", seed=7, phone_band=True) >= T.P_AI_THRESHOLD


def test_short_clip_marks_acoustic_not_applicable():
    x = make_call("tts", seconds=2.0)
    tells, ctx = acoustic.analyze(x, 2000)
    assert ctx["too_short"] and all(not t.applicable for t in tells)


def test_band_limited_flag():
    x = make_call("human", seed=3, phone_band=True)
    _, ctx = acoustic.analyze(x, 14000)
    assert ctx["band_limited"] is True


def test_wav_roundtrip_and_resample():
    x = make_call("human", seconds=5, sr=44100)
    y, sr, dur = decode(to_wav_bytes(x, 44100))
    assert sr == 44100 and abs(dur - 5000) < 20 and len(y) == pytest.approx(80000, abs=50)


def test_script_tells():
    h = {t.name: t for t in script.analyze(HUMAN_TXT)}
    a = {t.name: t for t in script.analyze(AI_TXT)}
    assert h["disfluency"].score < 0.3 and a["disfluency"].score > 0.7
    assert a["llm_isms"].score > 0.6 and h["llm_isms"].score < 0.3


def test_intent_scam_and_disclosure():
    tells, disclosed = intent.detect(SCAM_TXT)
    fired = {t.name for t in tells if t.score > 0}
    assert {"impersonation", "urgency", "payment_rails", "secrecy"} <= fired and not disclosed
    _, disclosed2 = intent.detect(DISCLOSED_TXT)
    assert disclosed2


def test_end_to_end_tiers():
    assert pipeline.analyze(to_wav_bytes(make_call("human", seed=11)), HUMAN_TXT).tier == "human"
    assert pipeline.analyze(to_wav_bytes(make_call("tts", seed=11)), AI_TXT).tier == "ai_undisclosed"
    assert pipeline.analyze(to_wav_bytes(make_call("tts", seed=12)), DISCLOSED_TXT).tier == "ai_disclosed"
    assert pipeline.analyze(to_wav_bytes(make_call("tts", seed=13)), SCAM_TXT).tier == "scam"
    assert pipeline.analyze(None, SCAM_TXT).tier == "scam"  # transcript-only still catches scams


def test_verdict_has_evidence_and_signature():
    v = pipeline.analyze(to_wav_bytes(make_call("tts", seed=2)), AI_TXT)
    assert all(t.evidence for t in v.tells)
    assert v.signature.startswith("ds1:") and v.egress["caller_audio_bytes_sent"] == 0
