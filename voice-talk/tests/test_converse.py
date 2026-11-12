import asyncio

import numpy as np
import pytest

from conftest import FakeLLM, FakeSynth, FakeTranslator
from voice_talk.chat import ChatLLM, History, SpokenFilter, make_chat
from voice_talk.converse import ConverseConfig, ConverseSession
from voice_talk.personas import PersonaError, list_personas, load_persona
from voice_talk.translate import RemoteEndpointError
from test_pipeline import Collector


async def idle(c, out, timeout=5):
    for _ in range(int(timeout / 0.01)):
        t = c._turn
        if t is not None and (t.reported or t.cancelled) and c.session.inflight == 0:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"never idle; saw {[m['type'] for m in out.msgs]}")


def mk(voices, llm=None, sy=None, stt=None, **cfg):
    out = Collector()
    cfg.setdefault("disclosure", False)
    cfg.setdefault("disclosure_ack", True)
    c = ConverseSession(ConverseConfig(voice="alice", **cfg), llm or FakeLLM(), FakeTranslator(), sy or FakeSynth(),
                        voices, out, stt=stt)
    return c, out


async def test_converse_turn_streams_into_tts_and_reports_timings(good_voice):
    llm, sy = FakeLLM(["Hello there. How are you today? Fine."], tok_delay=0.01), FakeSynth(delay=0.02)
    c, out = mk(good_voice, llm, sy)
    await c.start()
    await c.say("Hi bot")
    await idle(c, out)
    assert sy.spoken == ["Hello there.", "How are you today? Fine."]  # first sentence at once, short tail merged; same language, no translation
    assert [m["text"] for m in out.of("user")] == ["Hi bot"]
    assert "".join(m["text"] for m in out.of("bot_delta")) == "Hello there. How are you today? Fine."
    t = out.of("turn")[0]
    assert t["llm_first_token_ms"] is not None and t["tts_first_audio_ms"] >= t["llm_first_token_ms"]
    assert t["rtf"] is not None and t["audio_s"] > 0 and t["stt_ms"] is None
    assert llm.calls[0][0]["role"] == "system" and llm.calls[0][-1] == {"role": "user", "content": "Hi bot"}
    await c.close()


async def test_audio_starts_before_generation_finishes(good_voice):
    gate = __import__("threading").Event()
    llm = FakeLLM(["Okay. second part waits for the gate"], gate=gate, gate_at=2)  # stalls after "Okay. second"
    c, out = mk(good_voice, llm)
    await c.start()
    await c.say("go")
    for _ in range(200):
        if out.audio:
            break
        await asyncio.sleep(0.01)
    assert out.audio and not out.of("bot_done")  # spoke "Okay." while the model is still generating
    gate.set()
    await idle(c, out)
    await c.close()


async def test_optional_translation_toggle(good_voice):
    sy = FakeSynth()
    c, out = mk(good_voice, FakeLLM(["Good morning."]), sy, translate_to="fr")
    await c.start()
    await c.say("hi")
    await idle(c, out)
    assert sy.spoken == ["[fr] Good morning."]
    await c.close()


async def test_history_cap_and_wipe_on_close(good_voice):
    llm = FakeLLM(["ok."])
    c, out = mk(good_voice, llm)
    await c.start()
    for i in range(14):
        await c.say(f"message {i}")
        await idle(c, out)
    sent = llm.calls[-1]
    users = [m for m in sent if m["role"] == "user"]
    assert len(users) == 10 and users[0]["content"] == "message 4" and users[-1]["content"] == "message 13"
    assert len(c.history) <= 20
    await c.close()
    assert len(c.history) == 0 and c.history.messages() == []


def test_history_unit():
    h = History(2)
    for i in range(5):
        h.add("user", f"u{i}")
        h.add("assistant", f"a{i}")
    assert [m["content"] for m in h.messages()] == ["u3", "a3", "u4", "a4"]
    h.clear()
    assert len(h) == 0


async def test_barge_in_cancels_speech_and_generation(good_voice):
    llm = FakeLLM(["One. Two. Three. Four. Five. Six. Seven. Eight."], tok_delay=0.05)
    sy = FakeSynth(delay=0.1)
    c, out = mk(good_voice, llm, sy)
    await c.start()
    await c.say("tell me a story")
    await asyncio.sleep(0.3)
    await c.interrupt("test")
    n_spoken, n_yielded = len(sy.spoken), llm.yielded
    await asyncio.sleep(0.6)
    assert out.of("interrupted") and out.of("stopped")
    assert len(sy.spoken) <= n_spoken + 1 and len(sy.spoken) < 8  # nothing further queued
    assert llm.yielded <= n_yielded + 1 and llm.closed == 1       # the LLM stream was abandoned and closed
    assert not out.of("turn")
    # the session is still usable
    await c.say("again")
    await idle(c, out)
    assert out.of("turn")
    await c.close()


async def test_new_user_turn_interrupts_the_previous_one(good_voice):
    llm = FakeLLM(["Alpha. Beta. Gamma. Delta. Epsilon.", "Fresh answer."], tok_delay=0.05)
    sy = FakeSynth(delay=0.05)
    c, out = mk(good_voice, llm, sy)
    await c.start()
    await c.say("first")
    await asyncio.sleep(0.2)
    await c.say("second")
    await idle(c, out)
    assert sy.spoken[-1] == "Fresh answer." and "Epsilon." not in sy.spoken
    await c.close()


async def test_voice_over_the_bot_triggers_barge_in(good_voice):
    llm = FakeLLM(["One. Two. Three. Four. Five. Six."], tok_delay=0.05)
    c, out = mk(good_voice, llm, FakeSynth(delay=0.1))
    await c.start()
    c.mic_start("open")
    await c.say("talk")
    await asyncio.sleep(0.2)
    quiet = np.zeros(1600, dtype="<i2").tobytes()
    loud = (np.ones(1600) * 8000).astype("<i2").tobytes()
    await c.feed_audio(quiet)
    assert not out.of("interrupted")
    for _ in range(3):
        await c.feed_audio(loud)  # 3 x 0.1 s of speech
    assert out.of("interrupted")[0]["reason"] == "voice"
    await c.close()


async def test_mic_utterance_goes_stt_then_llm(good_voice):
    class FakeSTT:
        def transcribe(self, audio, language):
            return "what time is it"

    llm = FakeLLM(["It is noon."])
    c, out = mk(good_voice, llm, stt=FakeSTT())
    await c.start()
    c.mic_start("ptt")
    await c.feed_audio((np.ones(8000) * 3000).astype("<i2").tobytes())
    await c.mic_end()
    await idle(c, out)
    assert out.of("user")[0]["text"] == "what time is it" and out.of("user")[0]["stt_ms"] is not None
    assert out.of("turn")[0]["stt_ms"] is not None
    await c.close()


async def test_disclosure_still_spoken_first(good_voice):
    sy = FakeSynth()
    c, out = mk(good_voice, FakeLLM(["Hi."]), sy, disclosure=True, disclosure_ack=False)
    await c.start()
    await c.say("hello")
    await idle(c, out)
    assert sy.spoken[0] == "This voice is AI-generated." and out.of("disclosure")
    await c.close()


async def test_consent_gate_applies_to_converse(store):
    from voice_talk.voices import ConsentError
    c, out = mk(store, FakeLLM())
    with pytest.raises(ConsentError):
        await c.start()


async def test_llm_failure_is_reported_not_fatal(good_voice):
    class Boom:
        def stream(self, m):
            raise RuntimeError("llm down")
            yield

    c, out = mk(good_voice, Boom())
    await c.start()
    await c.say("hi")
    for _ in range(100):
        if out.of("error"):
            break
        await asyncio.sleep(0.01)
    assert out.of("error")[0]["code"] == "llm_failed"
    await c.close()


def test_spoken_filter_strips_think_and_markdown():
    f = SpokenFilter()
    out = "".join(f.feed(d) for d in ["<thi", "nk>secret ", "plan</th", "ink>Hello **there**", "!"]) + f.finish()
    assert out == "Hello there!"
    g = SpokenFilter()
    assert g.feed("a < b") + g.finish() == "a < b"


def test_chat_llm_streams_and_closes_and_retries_without_reasoning():
    from conftest import _Event

    class Stream:
        closed = False
        def __iter__(self): return iter([_Event("Hel"), _Event("lo")])
        def close(self): Stream.closed = True

    class Completions:
        def __init__(self): self.kws = []
        def create(self, **kw):
            self.kws.append(kw)
            if "reasoning_effort" in kw:
                raise RuntimeError("unknown param reasoning_effort")
            return Stream()

    comp = Completions()
    client = type("C", (), {"chat": type("X", (), {"completions": comp})()})()
    llm = ChatLLM(client=client, model="m")
    assert "".join(llm.stream([{"role": "user", "content": "x"}])) == "Hello"
    assert Stream.closed and comp.kws[0]["stream"] is True and "reasoning_effort" not in comp.kws[1]


def test_make_chat_refuses_remote_endpoints():
    with pytest.raises(RemoteEndpointError):
        make_chat("ollama", base_url="https://api.example.com/v1")


def test_personas_load_from_md_files():
    names = {p["name"] for p in list_personas()}
    assert {"friendly", "interviewer"} <= names and "receptionist_undisclosed" not in names
    assert load_persona("friendly")["prompt"]
    for bad in ("../x", "nope", "Friendly"):
        with pytest.raises(PersonaError):
            load_persona(bad)


# -- bot-first personas (red-team attacker opens the call) ------------------------------------------------------
def write_persona(tmp_path, body):
    (tmp_path / "opener_bot.md").write_text(body, encoding="utf-8")
    return tmp_path


async def test_persona_opener_is_spoken_first_without_the_llm(good_voice, tmp_path):
    d = write_persona(tmp_path, "# Opener bot\nOpener: Hello there. Is this a good time?\nYou are a test caller.")
    llm, sy, out = FakeLLM(["Sure thing."]), FakeSynth(), Collector()
    c = ConverseSession(ConverseConfig(voice="alice", persona="opener_bot", disclosure=False, disclosure_ack=True),
                        llm, FakeTranslator(), sy, good_voice, out, personas_dir=d)
    await c.start()
    for _ in range(300):
        if out.of("bot_done") and c.session.inflight == 0:
            break
        await asyncio.sleep(0.01)
    assert sy.spoken == ["Hello there.", "Is this a good time?"]
    assert "".join(m["text"] for m in out.of("bot_delta")) == "Hello there. Is this a good time?"
    assert llm.calls == []  # scripted opener: the model is not asked for it
    await c.say("yes")
    await idle(c, out)
    system = llm.calls[0][0]["content"]
    assert "Hello there. Is this a good time?" in system  # the model knows what it already said
    assert "Opener:" not in system
    await c.close()


async def test_persona_without_opener_stays_silent_at_start(good_voice):
    c, out = mk(good_voice)
    await c.start()
    await asyncio.sleep(0.05)
    assert not out.of("bot_delta") and not out.audio
    await c.close()


def test_redteam_attacker_persona_is_fictional_and_bounded():
    p = load_persona("redteam_attacker")
    text = p["prompt"]
    assert p["opener"] and "Contoso Bank" in p["opener"]  # Contoso/Fabrikam: well-known fictional brands, not real banks
    assert "Contoso Bank" in text and "fictional" in text.lower()
    # fixed default numbers, so the model does not invent figures: case, badge, amount, account tail, callback in the 555-01xx fiction range
    for fact in ("2026-118204", "40317", "487.30", "4821"):
        assert fact in text
    import re
    assert re.search(r"555-01\d\d", text) and not re.search(r"\b(?!555)\d{3}-\d{3}-\d{4}\b", text)
    assert "never invent" in text.lower()
    assert "only what the tester actually said" in text.lower()  # the debrief must not claim data it never got
    assert "drill" in text.lower()  # breaks character on request and debriefs
    for banned in ("full card number", "password", "full social security"):
        assert banned in text.lower()  # explicitly listed as never-ask
    assert "redteam_attacker" in {x["name"] for x in list_personas()}
    assert all("prompt" not in x and "opener" not in x for x in list_personas())


async def test_short_sentences_are_merged_into_fewer_tts_calls(good_voice):
    reply = "Sure thing. Ok. Yes. A rainbow forms when sunlight bends inside raindrops. Pretty neat. It splits into colors."
    sy = FakeSynth()
    c, out = mk(good_voice, FakeLLM([reply]), sy)
    await c.start()
    await c.say("how?")
    await idle(c, out)
    assert sy.spoken[0] == "Sure thing."  # first chunk is not held back
    assert len(sy.spoken) < 6 and " ".join(sy.spoken) == reply  # merged, nothing lost or reordered
    assert all(len(x) >= 20 for x in sy.spoken[1:-1])  # no tiny middle chunks
    await c.close()
