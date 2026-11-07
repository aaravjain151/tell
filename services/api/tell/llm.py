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


def _parse(text: str) -> dict:
    try:
        return json.loads(text[text.find("{"): text.rfind("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return {}


def _to_tells(data: dict, src: str) -> list[Tell]:
    if not data:
        return []
    tells = [
        Tell("llm_assistant_style", "script", _score(data, "assistant_style", 0.5), 0.8, f"{src}: " + str(data.get("assistant_style_reason", ""))[:140]),
        Tell("llm_scam_framing", "intent", _score(data, "scam_framing", 0.0), 1.0, f"{src}: " + str(data.get("scam_framing_reason", ""))[:140]),
    ]
    if data.get("disclosed_ai"):
        tells.append(Tell("ai_disclosure", "intent", 0.0, 0.0, f"{src}: caller disclosed it is AI", applicable=False))
    return tells


def cap_words(transcript: str, limit: int | None = None) -> str:
    """Keep only the last `limit` words (default TELL_LLM_MAX_WORDS=120): the latest turns carry the ask, and it bounds local latency."""
    limit = limit or int(os.environ.get("TELL_LLM_MAX_WORDS", "120"))
    words = transcript.split()
    return transcript if len(words) <= limit else " ".join(words[-limit:])


def _score(data: dict, key: str, default: float) -> float:
    try:
        return min(1.0, max(0.0, float(data.get(key, default))))
    except (TypeError, ValueError):   # 3B models sometimes answer "high" or null
        return default


def _ollama(transcript: str) -> tuple[list[Tell], dict]:
    """Local 3B model via Ollama on localhost (http://127.0.0.1:11434). Transcript text only; nothing leaves the machine."""
    import urllib.request
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
    base = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    payload = {"model": model, "prompt": PROMPT + cap_words(transcript), "stream": False, "format": "json",
               "options": {"temperature": 0, "num_predict": 200}}
    if "qwen3" in model.lower() or os.environ.get("OLLAMA_THINK") == "0":
        payload["think"] = False   # reasoning tokens would eat num_predict and the 3 s budget
    body = json.dumps(payload).encode()
    req = urllib.request.Request(base + "/api/generate", data=body, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=float(os.environ.get('OLLAMA_TIMEOUT_S', '10'))) as r:
            resp = json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        log.warning("ollama unavailable: %s", e)
        return [], {"provider": "ollama", "model": model, "error": str(e)[:80], "usd": 0.0}
    usage = {"provider": "ollama", "model": model, "input_tokens": resp.get("prompt_eval_count", 0),
             "output_tokens": resp.get("eval_count", 0), "usd": 0.0, "local": True}
    return _to_tells(_parse(resp.get("response", "")), model), usage


def interpret(transcript: str) -> tuple[list[Tell], dict]:
    provider = os.environ.get("LLM_PROVIDER", "stub")
    if not transcript or not transcript.strip():
        return [], {"provider": "stub", "input_tokens": 0, "output_tokens": 0, "usd": 0.0}
    if provider == "ollama":
        return _ollama(transcript)
    if provider != "anthropic":
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
        Tell("llm_assistant_style", "script", _score(data, "assistant_style", 0.5), 0.8,
             "model: " + str(data.get("assistant_style_reason", ""))[:140]),
        Tell("llm_scam_framing", "intent", _score(data, "scam_framing", 0.0), 1.0,
             "model: " + str(data.get("scam_framing_reason", ""))[:140]),
    ]
    if data.get("disclosed_ai"):
        tells.append(Tell("ai_disclosure", "intent", 0.0, 0.0, "model: caller disclosed it is AI", applicable=False))
    return tells, usage
