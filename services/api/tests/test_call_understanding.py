"""reasons.py (deterministic plain sentences), model_notes sanitising/isolation, and the STT silence guard."""
import sys
import types

import numpy as np

from doublespeak import llm, localhost, pipeline, reasons, stt
from doublespeak.types import Tell


def intent_tell(name, score=0.75, weight=1.0, ev="x"):
    return Tell(name, "intent", score, weight, ev)


# ---------------- reasons ----------------
def test_each_family_has_its_sentence():
    expect = {
        "payment_rails": "They asked you to pay or send money.",
        "secrecy": "They asked you to keep this secret.",
        "urgency": "They pressed you to act right now.",
        "impersonation": "They claimed to be someone you know or trust.",
        "credential_ask": "They asked for a code or a password.",
        "emergency": "They described an emergency to scare you.",
        "authority_threat": "They threatened you with arrest or the police.",
    }
    for name, sentence in expect.items():
        assert reasons.build([intent_tell(name)]) == [sentence]


def test_gift_cards_sentence_and_voice_and_script():
    assert reasons.build([intent_tell("payment_rails", ev="payment rails: “gift cards”")]) == ["They asked you to buy gift cards."]
    voice = [Tell(n, "acoustic", 0.9, 1.0, "e") for n in ("pause_regularity", "breath_proxy", "neural_hf")]
    assert reasons.build(voice) == ["The voice may be an AI copy, not a real person."]   # de-duplicated to one
    assert reasons.build([Tell("llm_isms", "script", 0.9, 1.0, "e")]) == ["The wording sounds scripted."]


def test_at_most_four_ordered_by_weight_times_score():
    tells = [intent_tell("urgency", 0.55, 0.8), intent_tell("payment_rails", 0.9, 1.5), intent_tell("secrecy", 0.55, 1.0),
             intent_tell("credential_ask", 0.75, 1.3), intent_tell("emergency", 0.55, 0.9), intent_tell("impersonation", 0.55, 1.0)]
    out = reasons.build(tells)
    assert len(out) == 4
    assert out[0] == "They asked you to pay or send money." and out[1] == "They asked for a code or a password."
    assert "They pressed you to act right now." not in out    # weakest dropped


def test_empty_case_is_honest_and_never_says_safe():
    for tells in ([], [intent_tell("urgency", 0.0)], [Tell("pitch_stability", "acoustic", 0.2, 1.0, "e")]):
        out = reasons.build(tells)
        assert out == ["No warning signs found. Doublespeak can be wrong."]
        assert "safe" not in out[0].lower()


def test_llm_and_inapplicable_tells_never_make_reasons():
    tells = [Tell("llm_scam_framing", "intent", 1.0, 1.0, "model says scam"), Tell("pitch_stability", "acoustic", 0.9, 1.0, "e", applicable=False)]
    assert reasons.build(tells) == [reasons.NONE_FOUND]


def test_disclosed_ai_does_not_also_claim_an_ai_copy():
    out = reasons.build([Tell("pause_regularity", "acoustic", 0.9, 1.0, "e")], disclosed_ai=True)
    assert out == [reasons.DISCLOSED]


def test_verdict_carries_reasons_and_notes():
    v = pipeline.analyze(None, "This is the IRS. Buy gift cards right now and don't tell anyone, you are going to be arrested.")
    d = v.to_dict()
    assert d["tier"] == "scam" and 1 <= len(d["reasons"]) <= 4 and "They asked you to buy gift cards." in d["reasons"]
    assert d["model_notes"] == []   # stub provider


# ---------------- model notes ----------------
def test_sanitise_strips_urls_phones_digits_and_caps():
    out = llm.sanitise_notes(["The caller wants you to visit www.evil.com now",
                              "They gave the number 555-123-4567 and code 123456 for payment",
                              "x" * 300 + " word word"])
    assert out and all("evil" not in n and "555" not in n and "123456" not in n for n in out)
    assert all(len(n) <= 120 for n in out)


def test_sanitise_drops_call_advice_and_reassurance_and_junk():
    raw = ["You should call 1-800-555-0100 to check", "Please call your bank back", "Call this number now to be safe",
           "This call seems legitimate to me", None, 7, {"a": 1}, "ok", "They asked for gift cards"]
    assert llm.sanitise_notes(raw) == ["They asked for gift cards"]


def test_sanitise_limits_to_three_and_handles_non_lists():
    assert len(llm.sanitise_notes([f"The caller said thing number {w}" for w in "abcdef"])) == 3
    assert llm.sanitise_notes("They asked for gift cards") == ["They asked for gift cards"]
    for junk in ("", None, 5, [None], [[]], {"a": "b"}):
        assert llm.sanitise_notes(junk) == []


def test_notes_are_display_only(monkeypatch):
    """A model that returns scary notes changes no tier, no reason, no tell, no disclosure."""
    text = "Hi Anna it is Priya, I will swing by later, are you around after six, okay cool see you then"
    base = pipeline.analyze(None, text)
    monkeypatch.setattr(pipeline.llm, "interpret", lambda t: ([], {"provider": "ollama", "notes": ["This is clearly a scam call", "They want your money"]}))
    v = pipeline.analyze(None, text)
    assert v.model_notes == ["This is clearly a scam call", "They want your money"]
    assert (v.tier, v.p_scam, v.disclosed_ai, v.reasons) == (base.tier, base.p_scam, base.disclosed_ai, base.reasons)
    assert "notes" not in v.cost
    assert not any("scam call" in r for r in v.reasons)


def test_ollama_reasons_parsed_and_sanitised(monkeypatch):
    body = (b'{"response": "{\\"assistant_style\\": 0.1, \\"scam_framing\\": 0.9, \\"reasons\\": '
            b'[\\"They want gift cards and the code 556677\\", \\"Call 1-800-000-1111 today\\"]}", "prompt_eval_count": 1, "eval_count": 1}')

    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return body
    monkeypatch.setattr(localhost, "_OPENER", types.SimpleNamespace(open=lambda req, timeout=0: R()))
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    tells, cost = llm.interpret("hello there friend")
    assert cost["notes"] == ["They want gift cards and the code"]
    assert {t.name for t in tells} == {"llm_assistant_style", "llm_scam_framing"}


# ---------------- stt silence guard ----------------
def _fake_whisper(monkeypatch, model):
    fake_mod = types.ModuleType("faster_whisper")
    fake_mod.WhisperModel = object
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)
    monkeypatch.setattr(stt, "_model", model)


def test_all_silence_vad_valueerror_returns_empty(monkeypatch):
    class Silent:
        def transcribe(self, *a, **k):
            raise ValueError("max() arg is an empty sequence")
    _fake_whisper(monkeypatch, Silent())
    assert stt.transcribe(np.zeros(16000, dtype=np.float32)) == ""


def test_valueerror_during_iteration_also_returns_empty(monkeypatch):
    class Lazy:
        def transcribe(self, *a, **k):
            def gen():
                raise ValueError("empty")
                yield
            return gen(), None
    _fake_whisper(monkeypatch, Lazy())
    assert stt.transcribe(np.zeros(16000, dtype=np.float32)) == ""
    monkeypatch.setenv("DOUBLESPEAK_STT", "whisper")
    assert stt.transcribe_with_source(np.zeros(16000, dtype=np.float32)) == (None, None)
