import asyncio

import pytest

from conftest import FakeSynth, FakeTranslator
from voice_talk.pipeline import DisclosureError, Session, SessionConfig
from voice_talk.voices import ConsentError


class Collector:
    def __init__(self):
        self.msgs, self.audio = [], []

    async def __call__(self, msg, binary=None):
        self.msgs.append(msg)
        if binary is not None:
            self.audio.append((msg["seq"], len(binary)))

    def of(self, t):
        return [m for m in self.msgs if m["type"] == t]


async def settle(sess, timeout=5):
    for _ in range(int(timeout / 0.01)):
        if sess.inflight == 0 and sess._q_tr.empty() and sess._q_tts.empty():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("pipeline did not settle")


def mk(voices, tr=None, sy=None, **cfg):
    out = Collector()
    s = Session(SessionConfig(voice="alice", **cfg), tr or FakeTranslator(), sy or FakeSynth(), voices, out)
    return s, out


async def test_consent_gate_blocks_synthesis(store):
    sy = FakeSynth()
    s, out = mk(store, sy=sy)
    with pytest.raises(ConsentError):
        await s.start()
    assert sy.prepared == [] and sy.spoken == [] and out.msgs == []


async def test_disclosure_spoken_first_in_target_language(good_voice):
    sy = FakeSynth()
    s, out = mk(good_voice, sy=sy, target="es")
    await s.start()
    s.feed_text("Hello there. ")
    await settle(s)
    assert sy.spoken[0] == "Esta voz está generada por IA."
    assert out.of("disclosure")[0]["seq"] == 1 and out.audio[0][0] == 1
    await s.close()


async def test_disclosure_off_requires_acknowledgement(good_voice):
    s, _ = mk(good_voice, disclosure=False)
    with pytest.raises(DisclosureError):
        await s.start()
    sy = FakeSynth()
    s, out = mk(good_voice, sy=sy, disclosure=False, disclosure_ack=True)
    await s.start()
    s.feed_text("One. ")
    await settle(s)
    assert sy.spoken == ["[es] One."] and not out.of("disclosure")
    await s.close()


async def test_ordering_and_no_overlap(good_voice):
    sy = FakeSynth(delay=0.03)
    s, out = mk(good_voice, tr=FakeTranslator(delay=0.01), sy=sy, disclosure=False, disclosure_ack=True)
    await s.start()
    s.feed_text("One. Two. Three. Four. Five. ")
    await settle(s)
    assert [a[0] for a in out.audio] == [1, 2, 3, 4, 5]
    assert sy.spoken == [f"[es] {w}." for w in ["One", "Two", "Three", "Four", "Five"]]
    assert sy.max_active == 1
    done = out.of("chunk_done")[0]["metrics"]
    assert {"translate_ms", "synth_ms", "audio_s", "rtf", "first_audio_ms"} <= set(done)
    await s.close()


async def test_error_in_one_chunk_does_not_kill_session(good_voice):
    s, out = mk(good_voice, tr=FakeTranslator(fail_on="Bad"), sy=FakeSynth(fail_on="Worse"),
                disclosure=False, disclosure_ack=True)
    await s.start()
    s.feed_text("Fine one. Bad two. Worse three. Fine four. ")
    await settle(s)
    assert [m["code"] for m in out.of("error")] == ["translate_failed", "synth_failed"]
    assert [a[0] for a in out.audio] == [1, 4]
    assert out.msgs[-1] == {"type": "state", "state": "ready"}
    await s.close()


async def test_stop_cancels_queue_and_session_stays_usable(good_voice):
    sy = FakeSynth(delay=0.1)
    s, out = mk(good_voice, sy=sy, disclosure=False, disclosure_ack=True)
    await s.start()
    s.feed_text("One. Two. Three. Four. ")
    await asyncio.sleep(0.05)
    await s.stop()
    await asyncio.sleep(0.4)
    assert len(sy.spoken) <= 1 and out.of("stopped")
    assert not [a for a in out.audio if a[0] > 1]
    s.feed_text("After stop. ")
    await settle(s)
    assert sy.spoken[-1] == "[es] After stop."
    await s.close()


async def test_flush_releases_partial_text(good_voice):
    sy = FakeSynth()
    s, _ = mk(good_voice, sy=sy, disclosure=False, disclosure_ack=True)
    await s.start()
    s.feed_text("no punctuation yet")
    await asyncio.sleep(0.05)
    assert sy.spoken == []
    s.flush()
    await settle(s)
    assert sy.spoken == ["[es] no punctuation yet"]
    await s.close()


async def test_speech_input_goes_through_stt_then_chunker(good_voice):
    import numpy as np

    class FakeSTT:
        def transcribe(self, audio, language):
            return "hello from the mic"

    sy = FakeSynth()
    out = Collector()
    s = Session(SessionConfig(voice="alice", disclosure=False, disclosure_ack=True), FakeTranslator(), sy, good_voice, out, stt=FakeSTT())
    await s.start()
    s.mic_start("ptt")
    await s.feed_audio((np.ones(8000) * 3000).astype("<i2").tobytes())
    assert sy.spoken == []
    await s.mic_end()
    await settle(s)
    assert sy.spoken == ["[es] hello from the mic"]
    await s.close()
