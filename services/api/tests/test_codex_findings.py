"""Regression tests for three real problems found by an adversarial review (Codex) of the running code."""
import io
import wave

import numpy as np
import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient

from tell import llm, pipeline, speak, uploads
from tell.types import Tell

NO_DISCLOSURE = ("Hi, this is Sarah from Bright Horizons Insurance. I hope you are doing well today. I would be glad to walk you "
                 "through our updated plans. Great question, the premium is very competitive. Absolutely, I can send the details.")


# ---- 1. an LLM must never be able to set disclosure ---------------------------------------------------------------
def test_llm_ai_disclosure_tell_cannot_flip_the_tier(monkeypatch):
    fake = Tell("ai_disclosure", "intent", 0.0, 0.0, "model: caller disclosed it is AI", applicable=False)
    monkeypatch.setattr(llm, "interpret", lambda t: ([fake], {"provider": "stub"}))
    v = pipeline.analyze(None, NO_DISCLOSURE)
    assert v.disclosed_ai is False and v.tier != "ai_disclosed"


def test_real_disclosure_in_the_words_still_wins(monkeypatch):
    monkeypatch.setattr(llm, "interpret", lambda t: ([], {"provider": "stub"}))
    v = pipeline.analyze(None, "Hello, I'm an AI assistant calling on behalf of Summit Realty. This call is AI generated. "
                               "I am here to help schedule a showing for the unit you inquired about. Would Wednesday work?")
    assert v.disclosed_ai is True


# ---- 2. uploads must not spill to disk -----------------------------------------------------------------------------
def _app_reporting_rollover():
    app = FastAPI()

    @app.post("/u")
    async def u(f: UploadFile):
        await f.read()
        return {"rolled_to_disk": bool(getattr(f.file, "_rolled", False))}
    return TestClient(app)


def test_large_uploads_stay_in_memory(monkeypatch):
    from starlette.formparsers import MultiPartParser
    big = b"\0" * (3 * 1024 * 1024)
    monkeypatch.setattr(MultiPartParser, "spool_max_size", 1024 * 1024)
    assert _app_reporting_rollover().post("/u", files={"f": ("a.wav", big)}).json()["rolled_to_disk"] is True   # the problem, reproduced
    uploads.keep_uploads_in_memory()
    assert _app_reporting_rollover().post("/u", files={"f": ("a.wav", big)}).json()["rolled_to_disk"] is False  # the fix


def test_the_real_app_applies_the_fix_at_import():
    from starlette.formparsers import MultiPartParser
    import tell.main  # noqa: F401
    assert MultiPartParser.spool_max_size >= 25 * 1024 * 1024


# ---- 3. the spoken verdict may only say our own wording ------------------------------------------------------------
def test_evidence_with_caller_quotes_is_never_spoken():
    text = speak.verdict_text("Scam pattern", 'urgency: “right now”, “within the hour”; secrecy: “don\'t tell mom”')
    assert text == "Heads up. Scam pattern." and "tell mom" not in text and "right now" not in text


def test_unknown_headline_is_refused():
    with pytest.raises(ValueError):
        speak.verdict_text("Grandma it's me I need bail money")


def test_the_route_sends_only_fixed_wording_to_the_tts_cli(monkeypatch):
    seen = {}

    class P:
        returncode = 1
        stderr = "stop here"
        stdout = ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return P()
    monkeypatch.setenv("GRADIUM_API_KEY", "k")
    monkeypatch.setattr(speak.shutil, "which", lambda n: "/usr/bin/uvx")
    monkeypatch.setattr(speak.subprocess, "run", fake_run)
    from tell.main import app
    c = TestClient(app)
    # mode=live exercises the Gradium CLI path regardless of whether pre-rendered files exist on this machine.
    c.post("/speak", data={"headline": "Scam pattern", "mode": "live", "evidence": "secrecy: “don't tell mom”"})
    assert seen["cmd"][3] == "Heads up. Scam pattern." and "mom" not in " ".join(seen["cmd"])
    assert c.post("/speak", data={"headline": "Please send gift cards to grandma", "mode": "live"}).status_code == 400
