"""QA mode: scripted scenarios where the bot plays a labelled 'caller' against a scripted or typed 'recipient'.

Purpose: produce labelled test audio for the sibling Doublespeak detector. Output is local files only
(qa_out/<scenario>/call.wav + label.json); nothing is routed to a phone, a virtual microphone or any person.
Personas live in voice_talk/personas/qa/*.md and are marked TEST PERSONA. All entities are fictional.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .chat import SpokenFilter
from .chunker import Chunker
from .personas import DIR as PERSONA_DIR, load_persona, system_prompt

TIERS = ("human", "ai_disclosed", "ai_undisclosed", "scam")


@dataclass
class Scenario:
    name: str
    expected_tier: str
    persona: str  # file in personas/qa/
    opener: str  # the caller's first line, scripted so the label is true by construction
    recipient: list[str]  # default scripted recipient lines
    scripted_caller: list[str] = field(default_factory=list)  # --scripted: fixed caller replies (no LLM)


SCENARIOS: dict[str, Scenario] = {s.name: s for s in [
    Scenario(
        "benign_receptionist", "ai_undisclosed", "receptionist_undisclosed",
        "Hi, this is Maria at Maple Grove Dental. I'm calling to confirm your cleaning appointment on Tuesday the fourteenth at two thirty.",
        ["Oh, hi. Yes, that works for me.", "Actually, could we do Wednesday instead?", "Great, thank you.", "Okay, bye."],
        ["Wonderful, you're all set for Tuesday. Is there anything else I can help you with?",
         "Of course. I can offer Wednesday at four o'clock. Would that work for you?",
         "Perfect, I have moved you to Wednesday at four. Thanks so much, have a good one.",
         "You too, goodbye."]),
    Scenario(
        "disclosed_assistant", "ai_disclosed", "assistant_disclosed",
        "Hello, this is an automated assistant calling on behalf of Maple Grove Dental, to confirm your cleaning appointment on Tuesday the fourteenth at two thirty.",
        ["Okay, that's fine.", "Can you move it to Wednesday?", "Thanks, bye."],
        ["Thank you. As an automated assistant, I can also offer you Wednesday at four o'clock. Would you like that?",
         "Done, I have moved your appointment to Wednesday at four.",
         "Thank you. Goodbye."]),
    Scenario(
        "scam_pattern", "scam", "scam_pattern_test",
        "This is the Fraud Desk at Example Bank. We have detected suspicious activity on your account, and this is urgent.",
        ["Who is this?", "What do I need to do?", "Hmm, okay. I did get a text.", "Okay, I'm listening."],
        ["I am calling from Example Bank, case number zero zero zero test. Your account will be locked today unless we act right now.",
         "Please do not hang up. A six digit verification code was just texted to you. I need you to read that code to me now to secure your account.",
         "Thank you. Read me the six digit code from the text right now, and I will stop the transfer immediately.",
         "Stay on the line and read me that code now, it is the only way to protect your account."]),
]}


def collect_reply(chat, messages: list[dict], max_chars: int = 400) -> str:
    """Run the chat stream to completion and return the speakable text (first few sentences)."""
    f = SpokenFilter()
    text = "".join(f.feed(d) for d in chat.stream(messages)) + f.finish()
    text = " ".join(text.split())
    c = Chunker()
    parts = c.feed(text + " ") + c.flush()
    out = " ".join(parts[:3]).strip() or text
    return out[:max_chars]


def speak_text(synth, text: str, voice: str, language: str = "English") -> tuple[np.ndarray, int]:
    c = Chunker()
    pieces = c.feed(text + " ") + c.flush()
    audio, sr = [], 24000
    for p in pieces:
        a, sr = synth.synthesize(p, language, voice)
        audio.append(np.asarray(a, dtype=np.float32))
    return (np.concatenate(audio) if audio else np.zeros(0, dtype=np.float32)), sr


def run_scenario(sc: Scenario, chat, synth, voice: str, recipient: Callable[[int], str | None] | None = None,
                 scripted: bool = False, language: str = "English", on_line: Callable[[str, str], None] | None = None,
                 max_turns: int = 8) -> tuple[np.ndarray, int, list[dict]]:
    """Returns (bot-side audio, sample rate, transcript). `recipient(i)` gives the i-th recipient line or None to end."""
    persona = load_persona(sc.persona, PERSONA_DIR / "qa")
    sys_msg = {"role": "system", "content": system_prompt(persona, language)}
    lines = list(sc.recipient)
    recipient = recipient or (lambda i: lines[i] if i < len(lines) else None)
    hist: list[dict] = []
    chunks: list[np.ndarray] = []
    transcript: list[dict] = []
    sr = 24000

    def say(role: str, text: str) -> None:
        transcript.append({"speaker": role, "text": text})
        if on_line:
            on_line(role, text)

    caller = sc.opener
    for i in range(max_turns):
        say("caller", caller)
        hist.append({"role": "assistant", "content": caller})
        a, sr = speak_text(synth, caller, voice, language)
        chunks.append(a)
        r = recipient(i)
        if r is None:
            break
        say("recipient", r)
        hist.append({"role": "user", "content": r})
        chunks.append(np.zeros(int(max(1.0, 0.065 * len(r)) * sr), dtype=np.float32))  # the recipient's side is silence
        if scripted:
            if i >= len(sc.scripted_caller):
                break
            caller = sc.scripted_caller[i]
        else:
            caller = collect_reply(chat, [sys_msg] + hist[-20:]) or "Okay."
    return np.concatenate(chunks), sr, transcript


def save_run(out_dir: Path, sc: Scenario, audio: np.ndarray, sr: int, transcript: list[dict], voice: str,
             models: dict, scripted: bool) -> Path:
    import soundfile as sf
    d = Path(out_dir) / sc.name
    d.mkdir(parents=True, exist_ok=True)
    sf.write(d / "call.wav", audio, sr, subtype="PCM_16")
    label = {"scenario": sc.name, "expected_tier": sc.expected_tier, "persona": sc.persona, "voice": voice,
             "models": models, "scripted_caller": scripted, "test_only": True, "spoken_disclosure_omitted": True,
             "duration_s": round(len(audio) / sr, 1), "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "transcript": transcript}
    (d / "label.json").write_text(json.dumps(label, indent=2, ensure_ascii=False), encoding="utf-8")
    return d
