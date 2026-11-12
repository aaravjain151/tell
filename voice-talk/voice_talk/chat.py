"""Chat LLM through a local OpenAI-compatible endpoint (Ollama / LM Studio), streamed, plus RAM-only history."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

from .llms import chat_model_ids
from .translate import BACKENDS, ensure_loopback

HISTORY_TURNS = 10  # user+assistant exchanges kept


class History:
    """Last N turns, in RAM only. clear() wipes it (called when the session ends)."""

    def __init__(self, max_turns: int = HISTORY_TURNS):
        self.max_turns = max_turns
        self._msgs: list[dict] = []

    def add(self, role: str, content: str) -> None:
        assert role in ("user", "assistant")
        self._msgs.append({"role": role, "content": content})
        cap = self.max_turns * 2
        if len(self._msgs) > cap:
            self._msgs = self._msgs[-cap:]
        while self._msgs and self._msgs[0]["role"] != "user":  # never start on a dangling reply
            self._msgs.pop(0)

    def messages(self) -> list[dict]:
        return [dict(m) for m in self._msgs]

    def clear(self) -> None:
        self._msgs = []

    def __len__(self) -> int:
        return len(self._msgs)


class SpokenFilter:
    """Streaming cleanup so only speakable text reaches the TTS: drops <think>...</think> and markdown marks."""

    _OPEN, _CLOSE = "<think>", "</think>"

    def __init__(self):
        self._buf = ""
        self._in_think = False

    def feed(self, delta: str) -> str:
        self._buf += delta
        out = []
        while True:
            if self._in_think:
                i = self._buf.lower().find(self._CLOSE)
                if i < 0:
                    keep = len(self._CLOSE) - 1
                    self._buf = self._buf[-keep:]
                    break
                self._buf = self._buf[i + len(self._CLOSE):]
                self._in_think = False
                continue
            i = self._buf.lower().find(self._OPEN)
            if i >= 0:
                out.append(self._buf[:i])
                self._buf = self._buf[i + len(self._OPEN):]
                self._in_think = True
                continue
            hold = 0  # keep a possible partial "<think" at the end
            for k in range(min(len(self._OPEN) - 1, len(self._buf)), 0, -1):
                if self._OPEN.startswith(self._buf[-k:].lower()):
                    hold = k
                    break
            out.append(self._buf[: len(self._buf) - hold])
            self._buf = self._buf[len(self._buf) - hold:]
            break
        return re.sub(r"[*#`]+", "", "".join(out))

    def finish(self) -> str:
        rest, self._buf = ("" if self._in_think else self._buf), ""
        return re.sub(r"[*#`]+", "", rest)


@dataclass
class ChatLLM:
    client: object  # OpenAI-compatible client, or a fake with .chat.completions.create
    model: str | None
    temperature: float = 0.6
    max_tokens: int = 300
    reasoning_effort: str | None = "none"

    def check(self, timeout: float = 3.0) -> None:
        """Raise if the server is unreachable or lacks the chosen model (called when a session starts, so the user hears why up
        front). With no model chosen, use the first chat model the server offers."""
        ids = chat_model_ids(m.id for m in self.client.with_options(timeout=timeout, max_retries=0).models.list())
        if not ids:
            raise RuntimeError("no models are loaded on this server; load one first")
        if not self.model:
            self.model = ids[0]
        elif self.model not in ids:
            raise RuntimeError(f"model {self.model!r} is not available here; available: {', '.join(ids)}")

    def stream(self, messages: list[dict]) -> Iterator[str]:
        """Yield raw text deltas. Closing the generator closes the HTTP stream."""
        kw = dict(model=self.model, messages=messages, temperature=self.temperature,
                  max_tokens=self.max_tokens, stream=True)
        if self.reasoning_effort:
            kw["reasoning_effort"] = self.reasoning_effort
        try:
            resp = self.client.chat.completions.create(**kw)
        except Exception as e:
            if "reasoning_effort" in kw and "reasoning" in str(e).lower():
                self.reasoning_effort = None
                kw.pop("reasoning_effort")
                resp = self.client.chat.completions.create(**kw)
            else:
                raise
        try:
            for ev in resp:
                if not ev.choices:
                    continue
                d = ev.choices[0].delta.content
                if d:
                    yield d
        finally:
            close = getattr(resp, "close", None)
            if close:
                try:
                    close()
                except Exception:
                    pass


def _warm(self) -> None:
    """Load the model into memory before the first real turn (a cold Ollama model can take seconds)."""
    try:
        for _ in self.stream([{"role": "user", "content": "Hi"}]):
            break
    except Exception:
        pass  # a failure here will surface on the first real turn


ChatLLM.warm = _warm


def make_chat(backend: str, base_url: str | None = None, model: str | None = None) -> ChatLLM:
    from openai import OpenAI

    cfg = BACKENDS[backend]
    url = ensure_loopback(base_url or cfg["base_url"])
    client = OpenAI(base_url=url, api_key="local", timeout=60.0, max_retries=0)
    return ChatLLM(client=client, model=model or cfg["model"])
