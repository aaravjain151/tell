"""Optional LLM interpreter. Default provider is `stub` (no network), which is what tests and eval use.

With LLM_PROVIDER=anthropic, the model reads the *transcript only* (never audio) and returns extra
Tells: subtle scam framing and assistant-style structure the regexes miss. Tokens and estimated cost
are logged on every call and returned in the verdict's `cost` block.
"""
from __future__ import annotations

import json
import logging
import os

from . import privacy
from .types import Tell

log = logging.getLogger("tell.llm")

PROMPT = """You read a phone-call transcript and extract structured signals. Output ONLY JSON:
{"assistant_style": 0-1, "assistant_style_reason": "...",
 "scam_framing": 0-1, "scam_framing_reason": "...",
 "disclosed_ai": true|false}
assistant_style: how much the caller's language reads like a scripted LLM/IVR (templated politeness, no hesitation, formal register).
scam_framing: pressure, isolation, payment/credential asks, impersonation, too-good-to-be-true.
Transcript:
"""

# rough public list prices per million tokens; keep in one place, update when you change models
PRICE_PER_MTOK = {"input": 3.0, "output": 15.0}


def interpret(transcript: str) -> tuple[list[Tell], dict]:
    provider = os.environ.get("LLM_PROVIDER", "stub")
    if provider != "anthropic" or not transcript or not transcript.strip():
        return [], {"provider": "stub", "input_tokens": 0, "output_tokens": 0, "usd": 0.0}
    try:
        import anthropic  # optional dependency
    except ImportError:
        log.warning("LLM_PROVIDER=anthropic but `anthropic` not installed; skipping")
        return [], {"provider": "stub", "input_tokens": 0, "output_tokens": 0, "usd": 0.0}
    client = anthropic.Anthropic()
    model = os.environ.get("TELL_LLM_MODEL", "claude-sonnet-5-5")
    privacy.record_egress("text", len(transcript.encode()))
    msg = client.messages.create(model=model, max_tokens=300, messages=[{"role": "user", "content": PROMPT + transcript}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    usage = {"provider": "anthropic", "model": model, "input_tokens": msg.usage.input_tokens,
             "output_tokens": msg.usage.output_tokens}
    usage["usd"] = round(usage["input_tokens"] * PRICE_PER_MTOK["input"] / 1e6 + usage["output_tokens"] * PRICE_PER_MTOK["output"] / 1e6, 6)
    log.info("llm call %s", usage)
    try:
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return [], usage
    tells = [
        Tell("llm_assistant_style", "script", float(data.get("assistant_style", 0.5)), 0.8,
             "model: " + str(data.get("assistant_style_reason", ""))[:140]),
        Tell("llm_scam_framing", "intent", float(data.get("scam_framing", 0.0)), 1.0,
             "model: " + str(data.get("scam_framing_reason", ""))[:140]),
    ]
    if data.get("disclosed_ai"):
        tells.append(Tell("ai_disclosure", "intent", 0.0, 0.0, "model: caller disclosed it is AI", applicable=False))
    return tells, usage
