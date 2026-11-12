import io
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice_talk.voices import VoiceStore  # noqa: E402


def make_wav(seconds=5.0, sr=16000, silent=False) -> bytes:
    t = np.arange(int(seconds * sr)) / sr
    x = np.zeros_like(t) if silent else 0.3 * np.sin(2 * np.pi * 180 * t) * (np.sin(2 * np.pi * 3 * t) > -0.5)
    buf = io.BytesIO()
    sf.write(buf, x.astype("float32"), sr, format="WAV")
    return buf.getvalue()


REF_TEXT = "this is a short test sentence that was spoken in the clip for the unit tests ok"


@pytest.fixture
def store(tmp_path):
    return VoiceStore(tmp_path / "voices")


@pytest.fixture
def good_voice(store):
    store.create("alice", make_wav(), REF_TEXT, "Alice Example", True)
    return store


class FakeTranslator:
    def __init__(self, fail_on=None, delay=0.0):
        self.calls, self.fail_on, self.delay = [], fail_on, delay

    def translate(self, text, source, target):
        import time
        time.sleep(self.delay)
        self.calls.append(text)
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("boom")
        return f"[{target}] {text}"


class FakeSynth:
    def __init__(self, fail_on=None, delay=0.0):
        self.prepared, self.spoken, self.fail_on, self.delay = [], [], fail_on, delay
        self.active = 0
        self.max_active = 0

    def prepare_voice(self, name, ref_path, ref_text):
        self.prepared.append(name)

    def synthesize(self, text, language_name, voice):
        import time
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay)
            if self.fail_on and self.fail_on in text:
                raise RuntimeError("tts boom")
            self.spoken.append(text)
            return np.zeros(2400, dtype=np.float32), 24000
        finally:
            self.active -= 1


class _Delta:
    def __init__(self, c): self.content = c


class _Choice:
    def __init__(self, c): self.delta = _Delta(c)


class _Event:
    def __init__(self, c): self.choices = [_Choice(c)]


class FakeLLM:
    """Stands in for ChatLLM: .stream(messages) yields deltas. `gate` (threading.Event) stalls after the first token."""

    def __init__(self, replies=("Sure thing. I can help with that. Anything else?",), tok_delay=0.0, gate=None, gate_at=1):
        self.replies, self.tok_delay, self.gate, self.gate_at = list(replies), tok_delay, gate, gate_at
        self.calls = []
        self.closed = 0
        self.yielded = 0

    def stream(self, messages):
        import time
        self.calls.append(messages)
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        try:
            for i, w in enumerate(reply.split(" ")):
                if i == self.gate_at and self.gate is not None:
                    self.gate.wait(5)
                time.sleep(self.tok_delay)
                self.yielded += 1
                yield (" " if i else "") + w
        finally:
            self.closed += 1
