"""Translation through a local OpenAI-compatible endpoint (LM Studio, Ollama, llama.cpp, vLLM, Jan, custom)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .languages import lang_name

# Presets for common local servers (any OpenAI-compatible endpoint on loopback). "model": None = the first chat model the
# server offers; set VT_LLM_MODEL or pick one in the page. See llms.register_custom() for any other URL.
BACKENDS = {
    "lmstudio": {"label": "LM Studio", "base_url": "http://127.0.0.1:1234/v1", "model": None},
    "ollama": {"label": "Ollama", "base_url": "http://127.0.0.1:11434/v1", "model": None},
    "llamacpp": {"label": "llama.cpp server", "base_url": "http://127.0.0.1:8080/v1", "model": None},
    "vllm": {"label": "vLLM", "base_url": "http://127.0.0.1:8000/v1", "model": None},
    "jan": {"label": "Jan", "base_url": "http://127.0.0.1:1337/v1", "model": None},
}
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class RemoteEndpointError(ValueError):
    pass


def ensure_loopback(url: str) -> str:
    host = urlparse(url).hostname
    if host not in LOOPBACK:
        raise RemoteEndpointError(f"only loopback endpoints are allowed, got {url!r}")
    return url


def build_messages(text: str, source: str, target: str) -> list[dict]:
    s, t = lang_name(source), lang_name(target)
    system = (
        f"You are a professional simultaneous interpreter. Translate the user's text "
        f"from {s} to {t}. Preserve tone and meaning. The text is spoken aloud, so use "
        f"natural spoken phrasing and write numbers as a native speaker would say them. "
        f"Output ONLY the translation: no notes, quotes, labels or explanations."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_LABEL = re.compile(r"^\s*(?:here(?:'s| is) the translation|translation|translated text)\s*[:：]\s*", re.I)
_NOTE_LINE = re.compile(r"^\s*[\(\[]?\s*(?:note|notes|n\.b\.|explanation)\b.*$", re.I)
_QUOTE_PAIRS = [('"', '"'), ("“", "”"), ("«", "»"), ("「", "」"), ("『", "』"), ("'", "'"), ("‘", "’")]


def clean_response(raw: str | None) -> str:
    if not raw:
        return ""
    t = _THINK.sub("", raw).strip()
    t = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", t).strip()
    t = _LABEL.sub("", t)
    lines = [ln for ln in t.splitlines()]
    kept: list[str] = []
    for ln in lines:
        if _NOTE_LINE.match(ln):
            break  # everything after a note marker is commentary
        kept.append(ln)
    t = " ".join(x.strip() for x in kept if x.strip())
    t = re.sub(r"\s*\((?:note|translation note|literally)[^)]*\)\s*$", "", t, flags=re.I).strip()
    changed = True
    while changed and len(t) >= 2:
        changed = False
        for a, b in _QUOTE_PAIRS:
            if t[0] == a and t[-1] == b and (a != "'" or t.count("'") == 2):
                t = t[1:-1].strip()
                changed = True
    return t


@dataclass
class Translator:
    client: object  # OpenAI-compatible client (or a fake with .chat.completions.create)
    model: str
    reasoning_effort: str | None = "none"
    temperature: float = 0.2
    max_tokens: int = 400

    def request_kwargs(self, text: str, source: str, target: str) -> dict:
        kw = dict(
            model=self.model,
            messages=build_messages(text, source, target),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        if self.reasoning_effort:
            kw["reasoning_effort"] = self.reasoning_effort  # Qwen3.5 thinking off where supported
        return kw

    def translate(self, text: str, source: str, target: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if source == target:
            return text
        kw = self.request_kwargs(text, source, target)
        try:
            resp = self.client.chat.completions.create(**kw)
        except Exception as e:  # servers that reject reasoning_effort: retry once without it
            if "reasoning_effort" in kw and "reasoning" in str(e).lower():
                self.reasoning_effort = None
                kw.pop("reasoning_effort")
                resp = self.client.chat.completions.create(**kw)
            else:
                raise
        out = clean_response(resp.choices[0].message.content)
        if not out:
            raise RuntimeError("translator returned an empty response")
        return out


def make_translator(backend: str, base_url: str | None = None, model: str | None = None) -> Translator:
    from openai import OpenAI

    cfg = BACKENDS[backend]
    url = ensure_loopback(base_url or cfg["base_url"])
    client = OpenAI(base_url=url, api_key="local", timeout=30.0, max_retries=0)
    return Translator(client=client, model=model or cfg["model"])
