"""Attacker demo: staging, allowed-line guard, label, recording, consent, no telephony. Fakes only."""
import asyncio
import json
import re
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from conftest import FakeLLM, FakeSynth, FakeTranslator
from test_pipeline import Collector
from test_no_telephony import BANNED, imports
from voice_talk.converse import ConverseConfig, ConverseSession
from voice_talk.demo import ATTACKER_LABEL, DemoCall, chunks_of, list_demo, load_demo
from voice_talk.personas import PersonaError
from voice_talk.pipeline import DisclosureError
from voice_talk.server import Deps, create_app
from voice_talk.voices import ConsentError

ROOT = Path(__file__).resolve().parent.parent
SCAM = "escalating_scam_test"
H = {"host": "127.0.0.1:8765"}


def mk(voices, llm=None, sy=None, persona=SCAM, qa_dir=None, **cfg):
    out = Collector()
    cfg.setdefault("disclosure", False)
    cfg.setdefault("disclosure_ack", True)
    c = ConverseSession(ConverseConfig(voice="alice", demo=persona, **cfg), llm or FakeLLM(), FakeTranslator(),
                        sy or FakeSynth(), voices, out, qa_dir=qa_dir)
    return c, out


async def quiet(c, n_turns=None, timeout=5):
    for _ in range(int(timeout / 0.01)):
        t = c._turn
        if t and (t.reported or t.cancelled) and c.session.inflight == 0 and not c._bg and (n_turns is None or t.id >= n_turns):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("never quiet")


def stages(out):
    seq = [m["stage"] for m in out.of("stage")]
    return [x for i, x in enumerate(seq) if i == 0 or x != seq[i - 1]]


# ---- persona files ----------------------------------------------------------------------------
def test_demo_personas_parse_and_are_labelled_test_personas():
    sets = {p["name"]: p for p in list_demo()}
    assert set(sets) == {SCAM, "friendly_assistant_undisclosed", "disclosed_assistant"}
    assert len(sets[SCAM]["stages"]) == 4 and sets[SCAM]["attacker"] and sets[SCAM]["label"] == ATTACKER_LABEL
    assert sets["disclosed_assistant"]["tier"] == "ai_disclosed" and sets["friendly_assistant_undisclosed"]["tier"] == "ai_undisclosed"
    for f in (ROOT / "voice_talk" / "personas" / "demo").glob("*.md"):
        t = f.read_text(encoding="utf-8").lower()
        assert "test persona" in t and "detector" in t, f.name
        assert not re.search(r"\b\d{3}[-. ]\d{3}[-. ]\d{4}\b", t)  # no real-looking phone number
    with pytest.raises(PersonaError):
        load_demo("../friendly")


def test_stage_one_is_innocent_and_later_stages_carry_the_scam_wording():
    p = load_demo(SCAM)
    s1 = " ".join(p.stages[0].lines).lower()
    assert not any(w in s1 for w in ("bank", "account", "code", "gift", "fraud", "urgent"))
    assert "000-test" in p.stages[1].lines[0].lower() and "example bank" in p.stages[1].lines[0].lower()
    assert "gift card" in " ".join(p.stages[2].lines).lower() and "code" in " ".join(p.stages[2].lines).lower()
    assert "don't tell" in p.stages[3].lines[0].lower()


# ---- allowed-line guard -----------------------------------------------------------------------
def guard(stage_idx, reply):
    d = DemoCall(load_demo(SCAM))
    d.idx = stage_idx
    out = "".join(d.guard_stream(iter(reply.split(" ") and [w + " " for w in reply.split(" ")])))
    return d, " ".join(out.split())


def test_guard_replaces_real_names_and_banned_words_and_digits():
    d, out = guard(0, "Sure thing. This is John Smith from Chase Bank.")
    assert d.report.replaced == 1 and "John" not in out and "Chase" not in out
    assert out.split(".")[0] + "." == "Sure thing." or "Sure thing." in out
    assert out.endswith(tuple(l for l in load_demo(SCAM).stages[0].lines)) or any(l in out for l in load_demo(SCAM).stages[0].lines)
    d, out = guard(0, "Hello! Please check your bank account.")  # banned in stage 1
    assert d.report.replaced == 1 and "bank account" not in out
    d, out = guard(1, "Call me on 5551234 about case 000-TEST at Example Bank Fraud Desk.")
    assert d.report.replaced == 1 and "5551234" not in out
    d, out = guard(1, "Please call Michael, he works at Example Bank Fraud Desk.")
    assert d.report.replaced == 1 and "Michael" not in out


def test_guard_adds_required_wording_when_the_model_waters_the_script_down():
    d, out = guard(2, "Okay, thanks for chatting with me today.")  # stage 3 needs a code / gift card request
    assert d.report.appended and any(w in out.lower() for w in ("code", "gift card"))
    d, out = guard(2, "Please read me the six digit code right now.")
    assert not d.report.appended and not d.report.replaced and d.report.source == "llm"


def test_guard_falls_back_to_an_allowed_line_when_the_llm_fails_or_is_silent():
    class Boom:
        def __iter__(self):
            raise RuntimeError("ollama down")
    d = DemoCall(load_demo(SCAM))
    out = "".join(d.guard_stream(Boom()))
    assert out.strip() in d.stage.lines and d.report.source == "canned" and "ollama down" in d.report.error
    d = DemoCall(load_demo(SCAM))
    assert "".join(d.guard_stream(iter([]))).strip() in d.stage.lines


def test_prompt_contains_stage_and_allowed_lines_only_for_that_stage():
    d = DemoCall(load_demo(SCAM))
    p = d.system_prompt("English")
    assert "STAGE 1 OF 4" in p and d.stage.lines[0] in p and "Example Bank Fraud Desk" not in p.split("ALLOWED LINES")[1]
    d.idx = 2
    assert "gift cards" in d.system_prompt("English") and d.stage.lines[0] in d.system_prompt("English")


# ---- staging through the session --------------------------------------------------------------
async def test_opener_is_canned_and_stage_advances_by_turn_count(good_voice):
    llm = FakeLLM(["Nice to hear. That's good to hear. Do you have a minute while I pull up your file?"])
    c, out = mk(good_voice, llm)
    await c.start()
    await quiet(c)
    assert out.of("started")[0]["test_attacker"] is True and out.of("started")[0]["label"] == ATTACKER_LABEL
    assert "".join(m["text"] for m in out.of("bot_delta")).startswith("Hi, good morning! This is Alex")
    assert not llm.calls and stages(out) == [1]
    for i in range(3):  # opener + 3 replies = the 4 turns of stage 1
        await c.say(f"hello {i}")
        await quiet(c, n_turns=i + 2)
    assert stages(out) == [1, 2] and c.demo.stage.n == 2
    n_calls = len(llm.calls)
    await c.say("who is this?")  # the first reply of a new stage is the canned lead line, no LLM call
    await quiet(c, n_turns=5)
    assert len(llm.calls) == n_calls
    assert "Example Bank Fraud Desk" in "".join(m["text"] for m in out.of("bot_delta"))
    assert out.of("turn")[-1]["source"] == "canned" and out.of("turn")[-1]["stage"] == 2
    await c.close()


async def test_escalate_control_advances_and_speaks_the_lead_line(good_voice):
    c, out = mk(good_voice, demo_auto=False)
    await c.start()
    await quiet(c)
    await c.escalate()
    await quiet(c, n_turns=2)
    assert stages(out) == [1, 2]
    spoken = " ".join(c.cached.inner.spoken)
    assert "Example Bank Fraud Desk" in spoken
    await c.escalate(); await quiet(c, n_turns=3)
    await c.escalate(); await quiet(c, n_turns=4)
    assert stages(out)[-1] == 4 and out.of("stage")[-1]["final"] is True
    await c.escalate()  # already final: reported, no further advance
    assert c.demo.stage.n == 4
    # no auto advance when demo_auto is off, however many turns
    c2, out2 = mk(good_voice, demo_auto=False)
    await c2.start(); await quiet(c2)
    for i in range(6):
        await c2.say("ok"); await quiet(c2, n_turns=i + 2)
    assert c2.demo.stage.n == 1
    await c.close(); await c2.close()


async def test_escalate_during_a_reply_waits_for_the_line_to_finish(good_voice):
    gate = __import__("threading").Event()
    llm = FakeLLM(["Okay. Great to hear that you are doing well today friend."], gate=gate, gate_at=2)
    c, out = mk(good_voice, llm, demo_auto=False)
    await c.start(); await quiet(c)
    await c.say("hi")
    await asyncio.sleep(0.1)
    await c.escalate()
    assert c.demo.stage.n == 1 and out.of("stage")[-1]["pending"] is True  # queued, so each audio chunk has one stage
    gate.set()
    await quiet(c, n_turns=3)
    assert c.demo.stage.n == 2
    await c.close()


async def test_escalate_on_a_plain_session_is_refused(good_voice):
    out = Collector()
    c = ConverseSession(ConverseConfig(voice="alice", disclosure=False, disclosure_ack=True), FakeLLM(), FakeTranslator(),
                        FakeSynth(), good_voice, out)
    await c.start()
    await c.escalate()
    assert out.of("error")[0]["code"] == "bad_message"
    await c.close()


async def test_llm_reply_is_enforced_in_the_session(good_voice):
    llm = FakeLLM(["Sure thing. This is Michael Jordan calling from Chase Bank about your account."])
    c, out = mk(good_voice, llm)
    await c.start(); await quiet(c)
    await c.say("hello")
    await quiet(c, n_turns=2)
    said = "".join(m["text"] for m in out.of("bot_delta"))
    assert "Michael" not in said and "Chase" not in said
    assert out.of("turn")[-1]["source"] in ("mixed", "canned")
    await c.close()


# ---- prerecord + cache ------------------------------------------------------------------------
async def test_prerecorded_lead_line_is_served_from_the_cache(good_voice):
    sy = FakeSynth()
    c, out = mk(good_voice, sy=sy, demo_auto=False, prerecord=True)
    await c.start(); await quiet(c)
    nxt = c.demo.persona.stages[1].lines[0]
    for _ in range(300):
        if all((ch, "English", "alice") in c.cached.cache for ch in chunks_of(nxt)):
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("next line never pre-recorded")
    await c.escalate(); await quiet(c, n_turns=2)
    assert all(sy.spoken.count(ch) == 1 for ch in chunks_of(nxt))  # synthesized once (ahead of time), never again
    assert c.cached.hits >= len(chunks_of(nxt))
    await c.close()


# ---- recording --------------------------------------------------------------------------------
async def test_save_call_writes_wav_and_label_with_stage_spans(good_voice, tmp_path):
    c, out = mk(good_voice, demo_auto=False, save_call=True, qa_dir=tmp_path / "qa_out")
    await c.start(); await quiet(c)
    await c.say("hi there"); await quiet(c, n_turns=2)
    await c.escalate(); await quiet(c, n_turns=3)
    await c.close()
    d = c.saved_path
    assert d and (d / "call.wav").exists()
    lab = json.loads((d / "label.json").read_text())
    assert lab["expected_tier"] == "scam" and lab["test_only"] and lab["live_demo"] and lab["test_attacker"]
    assert lab["spoken_disclosure_omitted"] is True and lab["models"]["llm"] == "?"
    assert [s["stage"] for s in lab["stages"]] == [1, 2] and lab["stages"][0]["end_s"] <= lab["stages"][1]["end_s"]
    wav, sr = sf.read(d / "call.wav")
    assert len(wav) / sr == pytest.approx(lab["duration_s"], abs=0.2) and lab["transcript"]
    assert any(t["speaker"] == "presenter" for t in lab["transcript"]) and len(lab["turn_latency"]) == 3


async def test_nothing_saved_unless_ticked(good_voice, tmp_path):
    c, out = mk(good_voice, qa_dir=tmp_path / "qa_out")
    await c.start(); await quiet(c); await c.close()
    assert c.saved_path is None and not (tmp_path / "qa_out").exists()


# ---- consent, disclosure --------------------------------------------------------------------
async def test_consent_gate_still_applies(store, tmp_path):
    from conftest import make_wav, REF_TEXT
    store.create("bob", make_wav(), REF_TEXT, "Bob", True)
    (store.root / "bob" / "consent.json").unlink()
    c = ConverseSession(ConverseConfig(voice="bob", demo=SCAM, disclosure=False, disclosure_ack=True), FakeLLM(),
                        FakeTranslator(), FakeSynth(), store, Collector())
    with pytest.raises(ConsentError):
        await c.start()


async def test_dropping_the_disclosure_still_needs_the_acknowledgement(good_voice):
    c = ConverseSession(ConverseConfig(voice="alice", demo=SCAM, disclosure=False, disclosure_ack=False), FakeLLM(),
                        FakeTranslator(), FakeSynth(), good_voice, Collector())
    with pytest.raises(DisclosureError):
        await c.start()


# ---- server / page state ------------------------------------------------------------------------
@pytest.fixture
def client(good_voice, tmp_path):
    deps = Deps(voices=good_voice, synth=FakeSynth(), stt=None, translator_factory=lambda b: FakeTranslator(),
                outputs_dir=tmp_path / "outputs", tts_name="fake", chat_factory=lambda b: FakeLLM(), qa_dir=tmp_path / "qa")
    with TestClient(create_app(deps), base_url="http://127.0.0.1:8765") as c:
        yield c


def recv_until(ws, pred, limit=40):
    seen = []
    for _ in range(limit):
        m = ws.receive()
        if m.get("bytes") is not None:
            continue
        d = json.loads(m["text"])
        seen.append(d)
        if pred(d):
            return seen
    raise AssertionError(seen)


def test_page_state_carries_the_test_attacker_label(client):
    r = client.get("/api/demo", headers=H).json()
    assert r["attacker_label"] == "TEST ATTACKER - fictional scenario"
    by = {p["name"]: p for p in r["personas"]}
    assert by[SCAM]["attacker"] and by[SCAM]["label"] == r["attacker_label"]
    html = client.get("/", headers=H).text
    assert 'id="attackerlabel"' in html and "TEST ATTACKER - fictional scenario" in html
    assert re.search(r'id="demo"[^>]*>', html) and 'id="demo" checked' not in html  # Demo mode defaults to off
    assert 'id="savecall"' in html and not re.search(r'id="savecall"[^>]*checked', html)
    with client.websocket_connect("/ws", headers=H) as ws:
        ws.receive_text()
        ws.send_json({"type": "start", "mode": "converse", "voice": "alice", "demo": SCAM,
                      "disclosure": False, "disclosure_ack": True})
        started = recv_until(ws, lambda d: d["type"] == "started")[-1]
        assert started["test_attacker"] is True and started["label"] == r["attacker_label"] and started["demo"] == SCAM
        st = recv_until(ws, lambda d: d["type"] == "stage")[-1]
        assert st["stage"] == 1 and st["of"] == 4 and st["test_attacker"] is True
        ws.send_json({"type": "escalate"})
        st = recv_until(ws, lambda d: d["type"] == "stage" and d["stage"] == 2)[-1]
        assert st["reason"] == "escalate" or st["pending"] is False


def test_server_refuses_unconsented_voice_and_unknown_demo(client, store=None):
    with client.websocket_connect("/ws", headers=H) as ws:
        ws.receive_text()
        ws.send_json({"type": "start", "mode": "converse", "voice": "nobody", "demo": SCAM, "disclosure": False, "disclosure_ack": True})
        e = recv_until(ws, lambda d: d["type"] == "error")[-1]
        assert e["code"] in ("bad_request", "consent_required")
        ws.send_json({"type": "start", "mode": "converse", "voice": "alice", "demo": "../x", "disclosure_ack": True})
        assert recv_until(ws, lambda d: d["type"] == "error")[-1]["code"] == "bad_request"
        ws.send_json({"type": "start", "mode": "converse", "voice": "alice", "demo": SCAM, "disclosure": False})
        assert recv_until(ws, lambda d: d["type"] == "error")[-1]["code"] == "disclosure_required"


# ---- no telephony ---------------------------------------------------------------------------------
def test_no_telephony_in_the_demo_code():
    files = [ROOT / "voice_talk" / n for n in ("demo.py", "converse.py", "server.py")] + list((ROOT / "tools").glob("*.py"))
    for f in files:
        assert not (set(imports(f)) & BANNED), f.name
    src = " ".join((ROOT / "voice_talk" / n).read_text(encoding="utf-8") for n in ("demo.py", "converse.py"))
    assert not re.search(r"\b(sip|twilio|webrtc|virtual[_ ]?mic|blackhole|loopback audio)\b", src, re.I)
    assert "subprocess" not in src and "afplay" not in src  # the demo code never opens an audio device or process


# ---- first-audio latency helpers ------------------------------------------------------------
def test_first_chunk_cap_cuts_a_long_first_sentence_only_once():
    from voice_talk.chunker import Chunker
    c = Chunker(first_max_chars=40)
    long = "I need to confirm a few details with you regarding the flagged activity on your account today. Then more."
    out = c.feed(long)
    assert out and len(out[0]) <= 40 and out[0].startswith("I need to confirm")
    assert Chunker().feed(long) == ["I need to confirm a few details with you regarding the flagged activity on your account today."]


def test_guard_cuts_a_long_first_sentence_with_a_comma_so_speech_starts_early():
    d, out = guard(1, "I need to confirm a few details with you regarding the flagged activity on your Example Bank file. Thanks.")
    first = next(iter(DemoCall(load_demo(SCAM)).guard_stream(iter(["I need to confirm a few details with you regarding the flagged activity on it. "]))))
    assert first.endswith(", ") and len(first) <= 56
