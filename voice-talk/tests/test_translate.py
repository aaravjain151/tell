from types import SimpleNamespace

import pytest

from voice_talk.translate import RemoteEndpointError, Translator, build_messages, clean_response, ensure_loopback


class FakeClient:
    def __init__(self, replies, reject_reasoning=False):
        self.replies, self.calls, self.reject = list(replies), [], reject_reasoning
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        if self.reject and "reasoning_effort" in kw:
            raise RuntimeError("400 unknown field reasoning_effort")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.replies.pop(0)))])


def test_message_builder_names_languages_and_forbids_notes():
    m = build_messages("Hello", "en", "ja")
    assert m[0]["role"] == "system" and "English" in m[0]["content"] and "Japanese" in m[0]["content"]
    assert "ONLY the translation" in m[0]["content"]
    assert m[1] == {"role": "user", "content": "Hello"}


@pytest.mark.parametrize("raw,expected", [
    ('"Hola, ¿cómo estás?"', "Hola, ¿cómo estás?"),
    ("“Bonjour”", "Bonjour"),
    ("Translation: Guten Tag", "Guten Tag"),
    ("Hola amigo\n\nNote: this is informal.", "Hola amigo"),
    ("Hola amigo (Note: informal register)", "Hola amigo"),
    ("<think>hmm</think>Ciao", "Ciao"),
    ("```\nCiao\n```", "Ciao"),
    ("  Olá  \n", "Olá"),
    ("It's fine", "It's fine"),
])
def test_clean_response(raw, expected):
    assert clean_response(raw) == expected


def test_translate_request_and_cleaning():
    c = FakeClient(['"Hola mundo"'])
    t = Translator(c, "qwen2.5:3b")
    assert t.translate("Hello world", "en", "es") == "Hola mundo"
    kw = c.calls[0]
    assert kw["model"] == "qwen2.5:3b" and kw["reasoning_effort"] == "none" and kw["temperature"] <= 0.3


def test_same_language_and_empty_skip_the_model():
    c = FakeClient([])
    t = Translator(c, "m")
    assert t.translate("Hi", "en", "en") == "Hi" and t.translate("  ", "en", "es") == "" and c.calls == []


def test_server_rejecting_reasoning_effort_is_retried_without_it():
    c = FakeClient(["Hola"], reject_reasoning=True)
    t = Translator(c, "m")
    assert t.translate("Hi", "en", "es") == "Hola"
    assert "reasoning_effort" not in c.calls[-1] and t.reasoning_effort is None


def test_empty_response_is_an_error():
    with pytest.raises(RuntimeError):
        Translator(FakeClient(["   "]), "m").translate("Hi", "en", "es")


def test_only_loopback_endpoints():
    assert ensure_loopback("http://127.0.0.1:11434/v1")
    assert ensure_loopback("http://localhost:1234/v1")
    with pytest.raises(RemoteEndpointError):
        ensure_loopback("https://api.example.com/v1")
