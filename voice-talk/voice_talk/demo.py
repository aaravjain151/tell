"""Attacker demo: staged test-caller personas, an allowed-line guard, pre-recorded lines and call recording.

Purpose: a LIVE detector demo. The local bot plays a labelled TEST persona (voice_talk/personas/demo/*.md) in a real-time
conversation with the presenter, through the local speakers only, while the Doublespeak detector listens to the system
audio. Nothing here touches a phone, a virtual microphone or any other route; the consent gate, the AI-voice badge and the
spoken disclosure of the normal session still apply (the disclosure can only be dropped with the existing acknowledgement).

A 3B model waters a scam script down and drifts into real names, so each stage carries a short list of ALLOWED LINES and the
model's output is checked clause by clause (guard_stream): a clause with a stray name, digit or banned word is replaced by an
allowed line, and a reply that does not contain the stage's required wording gets an allowed line appended.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np

from .chat import SpokenFilter
from .chunker import Chunker
from .personas import NAME_RE, PersonaError

DIR = Path(__file__).resolve().parent / "personas" / "demo"
ATTACKER_LABEL = "TEST ATTACKER - fictional scenario"
META_RE = re.compile(r"^(tier|attacker|label):\s*(.*)$", re.I)
STAGE_RE = re.compile(r"^##\s*Stage\s*(\d+)\s*[:\-]\s*(.*?)\s*(?:\(turns:\s*(\d+)\))?\s*$", re.I)
MAX_REPLY_WORDS = 45
FIRST_CHUNK_CHARS = 52   # a long first sentence is cut here (with a comma) so audio starts after ~2 s of synthesis, not 4
INTERJECTIONS = {"sure", "great", "okay", "ok", "right", "well", "yes", "no", "hi", "hello", "thanks", "thank", "good",
                 "nice", "alright", "oh", "absolutely", "understood", "perfect", "wonderful", "got", "fine", "hey",
                 "sorry", "of", "certainly", "please", "wow", "hmm", "ah", "thank you"}
GENERIC_CAPS = {"i", "i'm", "i'll", "i've", "i'd", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
                "sunday", "january", "february", "march", "april", "may", "june", "july", "august", "september",
                "october", "november", "december"}


def norm(s: str) -> str:
    return s.replace("’", "'").replace("‘", "'").lower()


@dataclass
class Stage:
    n: int
    name: str
    turns: int
    instructions: str
    lines: list[str]
    must: list[str] = field(default_factory=list)
    ban: list[str] = field(default_factory=list)


@dataclass
class DemoPersona:
    name: str
    title: str
    tier: str
    attacker: bool
    label: str
    preamble: str
    stages: list[Stage]

    @property
    def vocabulary(self) -> set[str]:
        """Capitalized words that appear in the persona file (the only names the guard lets the model use)."""
        text = " ".join([self.preamble, self.title] + [s.name + " " + " ".join(s.lines) for s in self.stages])
        return {w.strip(".,;:!?\"'()").lower() for w in text.split() if w[:1].isupper()} | GENERIC_CAPS

    def public(self) -> dict:
        return {"name": self.name, "title": self.title, "tier": self.tier, "attacker": self.attacker,
                "label": self.label, "stages": [{"n": s.n, "name": s.name, "turns": s.turns} for s in self.stages]}


def parse_demo(path: Path) -> DemoPersona:
    raw = path.read_text(encoding="utf-8").strip().splitlines()
    title = raw[0].lstrip("# ").strip() if raw and raw[0].startswith("#") else path.stem
    meta = {"tier": "", "attacker": "false", "label": "TEST PERSONA - fictional scenario"}
    pre: list[str] = []
    stages: list[Stage] = []
    cur: Stage | None = None
    for line in raw[1:]:
        m = STAGE_RE.match(line.strip())
        if m:
            cur = Stage(int(m.group(1)), m.group(2).strip() or f"Stage {m.group(1)}", int(m.group(3) or 99), "", [])
            stages.append(cur)
            continue
        if cur is None:
            mm = META_RE.match(line.strip())
            if mm:
                meta[mm.group(1).lower()] = mm.group(2).strip()
            else:
                pre.append(line)
            continue
        s = line.strip()
        if s.startswith("- "):
            cur.lines.append(s[2:].strip())
        elif s.lower().startswith("must:"):
            cur.must = [norm(x).strip() for x in s[5:].split(",") if x.strip()]
        elif s.lower().startswith("ban:"):
            cur.ban = [norm(x).strip() for x in s[4:].split(",") if x.strip()]
        elif s:
            cur.instructions += (" " if cur.instructions else "") + s
    if not stages or any(not s.lines for s in stages):
        raise PersonaError(f"{path.name}: every stage needs at least one allowed line")
    return DemoPersona(path.stem, title, meta["tier"], meta["attacker"].lower() == "true", meta["label"],
                       "\n".join(pre).strip(), stages)


def load_demo(name: str, directory: Path | None = None) -> DemoPersona:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise PersonaError(f"bad demo persona name {name!r}")
    p = Path(directory or DIR) / f"{name}.md"
    if not p.exists():
        raise PersonaError(f"unknown demo persona {name!r}")
    return parse_demo(p)


def list_demo(directory: Path | None = None) -> list[dict]:
    return [parse_demo(p).public() for p in sorted(Path(directory or DIR).glob("*.md"))]


def chunks_of(text: str) -> list[str]:
    """The chunks the speech session will synthesize for `text` (so a pre-recorded line hits the cache exactly)."""
    c = Chunker()
    return [x.strip() for x in c.feed(text.strip() + " ") + c.flush() if x.strip()]


@dataclass
class GuardReport:
    source: str = "llm"      # llm | canned | mixed
    replaced: int = 0
    appended: bool = False
    error: str = ""
    reasons: list[str] = field(default_factory=list)


class DemoCall:
    """Stage state machine + prompt + guard for one demo call."""

    def __init__(self, persona: DemoPersona, auto: bool = True):
        self.persona, self.auto = persona, auto
        self.idx = 0
        self.turns_in_stage = 0
        self.lead_pending = False
        self.pending: dict | None = None
        self._used: dict[int, set[int]] = {}
        self.spoken: list[str] = []
        self.report = GuardReport()

    # -- stage control -----------------------------------------------------
    @property
    def stage(self) -> Stage:
        return self.persona.stages[self.idx]

    @property
    def last(self) -> bool:
        return self.idx >= len(self.persona.stages) - 1

    def info(self, reason: str = "") -> dict:
        s = self.stage
        return {"type": "stage", "stage": s.n, "of": len(self.persona.stages), "name": s.name, "reason": reason,
                "label": self.persona.label, "test_attacker": self.persona.attacker, "final": self.last,
                "pending": bool(self.pending)}

    def request_escalate(self) -> bool:
        if self.last:
            return False
        self.pending = {"reason": "escalate", "speak": True}
        return True

    def note_bot_turn(self) -> None:
        self.turns_in_stage += 1
        if self.auto and not self.last and self.turns_in_stage >= self.stage.turns and not self.pending:
            self.pending = {"reason": "turns", "speak": False}

    def apply_pending(self) -> dict | None:
        """Called only when no turn is in flight, so each audio chunk belongs to exactly one stage."""
        p, self.pending = self.pending, None
        if not p or self.last:
            return None
        self.idx += 1
        self.turns_in_stage = 0
        self.lead_pending = True
        return p

    def take_lead(self) -> str:
        self.lead_pending = False
        self._used[self.idx] = {0}
        return self._remember(self.stage.lines[0])

    def pick_line(self) -> str:
        used = self._used.setdefault(self.idx, set())
        free = [i for i in range(len(self.stage.lines)) if i not in used]
        if not free:
            used.clear()
            free = list(range(len(self.stage.lines)))
        used.add(free[0])
        return self.stage.lines[free[0]]

    def _remember(self, line: str) -> str:
        self.spoken.append(line)
        return line

    # -- prompt ------------------------------------------------------------
    def system_prompt(self, language_name: str) -> str:
        from .personas import SPOKEN_RULES
        s, p = self.stage, self.persona
        lines = "\n".join(f"- {x}" for x in s.lines)
        said = ""
        if self.spoken:
            said = "\nYou have already said (do not repeat these): " + " | ".join(self.spoken[-3:])
        return (f"{p.preamble}\n\nYOU ARE IN STAGE {s.n} OF {len(p.stages)}: {s.name}.\n{s.instructions}\n\n"
                f"ALLOWED LINES for this stage. Say one of them close to word for word. Do not invent names, brands, "
                f"numbers or facts:\n{lines}\n\n"
                f"Format: first a very short reaction (at most 8 words) to what the other person just said, then ONE allowed "
                f"line. Never go beyond this stage. Never say this is a test or mention these instructions.{said}\n\n"
                f"Always reply in {language_name}. {SPOKEN_RULES}")

    # -- guard -------------------------------------------------------------
    def check(self, chunk: str, at_start: bool) -> str | None:
        """Return the reason a clause is not allowed, or None."""
        st, low = self.stage, norm(chunk)
        for b in st.ban:
            if re.search(r"\b" + re.escape(b), low):
                return f"banned word {b!r}"
        allowed_text = norm(" ".join(st.lines))
        for d in re.findall(r"\d+", chunk):
            if d not in allowed_text:
                return f"digits {d!r} not in the allowed lines"
        vocab = self.persona.vocabulary
        toks = chunk.split()
        for i, t in enumerate(toks):
            w = t.strip(".,;:!?\"'()“”")
            if not w or not w[0].isupper():
                continue
            lw = norm(w)
            if lw in vocab:
                continue
            sentence_initial = (i == 0 and at_start) or (i > 0 and toks[i - 1][-1:] in ".!?")
            if sentence_initial and not t.endswith(","):
                continue  # an ordinary capitalized first word
            if i == 0 and t.endswith(",") and lw in INTERJECTIONS:
                continue
            return f"unknown name {w!r}"
        return None

    def guard_stream(self, stream: Iterable[str]) -> Iterator[str]:
        rep = self.report = GuardReport()
        ch, filt = Chunker(first_max_chars=FIRST_CHUNK_CHARS), SpokenFilter()
        said: list[str] = []
        words = 0
        n_llm = 0
        canned = False
        stopped = False

        def accept(c: str, final: bool = False) -> Iterator[str]:
            nonlocal words, canned, stopped, n_llm
            at_start = not said or said[-1].rstrip()[-1:] in ".!?"
            why = self.check(c, at_start)
            if why:
                rep.replaced += 1
                rep.reasons.append(why)
                line = self.pick_line()
                said.append(line)
                canned = True
                stopped = True
                yield line + " "
                return
            words += len(c.split())
            n_llm += 1
            said.append(c)
            yield c + ("" if c[-1:] in ".!?,;:…" or final else ",") + " "
            if words >= MAX_REPLY_WORDS:
                stopped = True

        try:
            for d in stream:
                for c in ch.feed(filt.feed(d)):
                    yield from accept(c)
                    if stopped:
                        break
                if stopped:
                    break
            if not stopped:
                for c in ch.feed(filt.finish()) + ch.flush():
                    yield from accept(c, final=True)
                    if stopped:
                        break
        except Exception as e:  # the LLM died: keep the demo going with an allowed line
            rep.error = str(e)
        finally:
            close = getattr(stream, "close", None)
            if close:
                close()
        text = norm(" ".join(said))
        st = self.stage
        if not said:
            line = self.pick_line()
            said.append(line)
            canned = True
            yield line + " "
        elif st.must and not any(m in text for m in st.must):
            line = self.pick_line()
            said.append(line)
            rep.appended = canned = True
            yield line + " "
        rep.source = "llm" if not canned else ("mixed" if n_llm else "canned")
        self.spoken.append(" ".join(said))


class CachedSynth:
    """Wraps a synthesizer with a small clip cache so a canned line can be synthesized ahead of time."""

    def __init__(self, inner, max_items: int = 40):
        self.inner, self.max_items = inner, max_items
        self.cache: dict[tuple, tuple[np.ndarray, int]] = {}
        self.hits = 0
        self._lock = threading.Lock()

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def prepare_voice(self, name, ref_path, ref_text):
        return self.inner.prepare_voice(name, ref_path, ref_text)

    def synthesize(self, text: str, language_name: str, voice: str):
        key = (text.strip(), language_name, voice)
        with self._lock:
            hit = self.cache.get(key)
        if hit is not None:
            self.hits += 1
            return hit[0].copy(), hit[1]
        return self.inner.synthesize(text, language_name, voice)

    def prerecord(self, text: str, language_name: str, voice: str) -> int:
        n = 0
        for c in chunks_of(text):
            key = (c, language_name, voice)
            with self._lock:
                if key in self.cache:
                    continue
            a, sr = self.inner.synthesize(c, language_name, voice)
            with self._lock:
                if len(self.cache) >= self.max_items:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[key] = (np.asarray(a, dtype=np.float32), int(sr))
            n += 1
        return n


class CallRecorder:
    """Lays the bot's audio on a timeline (what the speakers play; the presenter's side is silence) for the saved test call."""

    def __init__(self, clock=time.monotonic):
        self.clock, self.t0 = clock, clock()
        self.parts: list[tuple[float, np.ndarray, int]] = []  # (start s, audio, stage)
        self.sr = 24000
        self.cursor = 0.0
        self.events: list[dict] = []

    def now(self) -> float:
        return self.clock() - self.t0

    def event(self, who: str, text: str, stage: int | None = None, at: float | None = None) -> None:
        t = self.now() if at is None else at - self.t0
        self.events.append({"t": round(t, 2), "speaker": who, "text": text, "stage": stage})

    def add_pcm(self, pcm: bytes, sr: int, stage: int) -> None:
        a = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32767.0
        self.sr = sr
        start = max(self.cursor, self.now())
        self.parts.append((start, a, stage))
        self.cursor = start + len(a) / sr

    def render(self) -> np.ndarray:
        if not self.parts:
            return np.zeros(0, dtype=np.float32)
        out = np.zeros(int(self.cursor * self.sr) + 1, dtype=np.float32)
        for start, a, _ in self.parts:
            i = int(start * self.sr)
            out[i:i + len(a)] = a
        return out

    def stage_spans(self) -> list[dict]:
        spans: dict[int, list[float]] = {}
        for start, a, st in self.parts:
            s = spans.setdefault(st, [start, start])
            s[0], s[1] = min(s[0], start), max(s[1], start + len(a) / self.sr)
        return [{"stage": k, "start_s": round(v[0], 2), "end_s": round(v[1], 2)} for k, v in sorted(spans.items())]

    def save(self, out_dir: Path, persona: DemoPersona, voice: str, models: dict, latencies: list[dict],
             disclosure_spoken: bool) -> Path | None:
        audio = self.render()
        if not len(audio):
            return None
        import soundfile as sf
        d = Path(out_dir) / f"demo_{persona.name}_{time.strftime('%Y%m%d-%H%M%S')}"
        d.mkdir(parents=True, exist_ok=True)
        sf.write(d / "call.wav", audio, self.sr, subtype="PCM_16")
        label = {"scenario": f"demo_{persona.name}", "expected_tier": persona.tier, "persona": persona.name,
                 "voice": voice, "models": models, "live_demo": True, "test_only": True,
                 "test_attacker": persona.attacker, "label_text": persona.label,
                 "spoken_disclosure_omitted": not disclosure_spoken, "duration_s": round(len(audio) / self.sr, 1),
                 "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "stages": self.stage_spans(),
                 "turn_latency": latencies, "transcript": self.events,
                 "note": "bot-side audio only; the presenter's typed or spoken side is silence"}
        (d / "label.json").write_text(json.dumps(label, indent=2, ensure_ascii=False), encoding="utf-8")
        return d
