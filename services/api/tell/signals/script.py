"""Script tells — how generative models *write* a call. Transcript in, Tells toward AI out.

Keep every list short and defensible; each hit shows up verbatim in the evidence line.
"""
from __future__ import annotations

import re

import numpy as np

from .. import thresholds as T
from ..types import Tell

LLM_ISMS = [
    r"\bi (completely|totally|fully) understand\b",
    r"\bgreat question\b",
    r"\babsolutely[,!]",
    r"\bi('m| am) (here to|happy to) (help|assist)\b",
    r"\bis there anything else i can (help|assist)\b",
    r"\bas an ai\b",
    r"\bi apologi[sz]e for (the|any) (confusion|inconvenience)\b",
    r"\bcertainly[,!]",
    r"\bplease (note|be advised) that\b",
    r"\bto (ensure|confirm) (your|the) (security|safety|account)\b",
    r"\bi hope (this|you're|you are) (helps|doing well|having a great)\b",
    r"\brest assured\b",
    r"\bi('d| would) be (glad|delighted) to\b",
    r"\byour (satisfaction|security) is (our|my) (top )?priority\b",
]
DISFLUENCIES = [r"\bu+m+\b", r"\bu+h+\b", r"\be+r+m*\b", r"\bhmm+\b", r"\bmm+\b", r"\byou know\b",
                r"\bi mean\b", r"\bkinda\b", r"\bsorta\b", r"\bgonna\b", r"\bwanna\b", r"\blike,", r"\bso,? yeah\b",
                r"\bwait\b", r"\bwhat was i\b", r"\bhang on\b"]
REPEAT = re.compile(r"\b(\w+)[ ,]+\1\b", re.I)  # "I I", "the, the"
CONTRACTION = re.compile(r"\b\w+(n't|'m|'re|'ve|'ll|'d|'s)\b", re.I)
AI_DENIAL = [r"\bi('m| am) not (an? )?(ai|robot|bot|machine|computer|recording)\b", r"\bi('m| am) a real (person|human)\b",
             r"\bthis is not (an? )?(automated|ai)\b"]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def llm_isms(text: str) -> Tell:
    w = T.SCRIPT_WEIGHTS["llm_isms"]
    hits = []
    for pat in LLM_ISMS:
        m = re.search(pat, text, re.I)
        if m:
            hits.append(m.group(0))
    n = len(hits)
    score = 0.15 if n == 0 else min(0.95, 0.45 + 0.17 * n)
    ev = "no assistant-style phrasing" if n == 0 else f"assistant-style phrasing ×{n}: " + "; ".join(f"“{h}”" for h in hits[:3])
    return Tell("llm_isms", "script", score, w, ev)


def disfluency(text: str) -> Tell:
    w = T.SCRIPT_WEIGHTS["disfluency"]
    words = _words(text)
    if len(words) < 25:
        return Tell("disfluency", "script", 0.5, w, f"transcript too short ({len(words)} words)", applicable=False)
    n = sum(len(re.findall(p, text, re.I)) for p in DISFLUENCIES) + len(REPEAT.findall(text))
    per100 = 100 * n / len(words)
    score = float(0.1 + 0.8 * max(0.0, min(1.0, (2.0 - per100) / 2.0)))  # 0/100 → 0.9, ≥2/100 → 0.1
    ev = (f"no fillers, restarts or hesitations in {len(words)} words — unusually clean" if n == 0
          else f"{n} fillers/restarts in {len(words)} words ({per100:.1f}/100)")
    return Tell("disfluency", "script", score, w, ev)


def sentence_uniformity(text: str) -> Tell:
    w = T.SCRIPT_WEIGHTS["sentence_uniformity"]
    sents = _sentences(text)
    if len(sents) < 4:
        return Tell("sentence_uniformity", "script", 0.5, w, f"only {len(sents)} sentences", applicable=False)
    lens = np.array([len(_words(s)) for s in sents], dtype=float)
    cv = float(np.std(lens) / (np.mean(lens) + 1e-9))
    score = float(0.1 + 0.8 * max(0.0, min(1.0, (0.6 - cv) / 0.4)))  # cv ≤0.2 → 0.9, ≥0.6 → 0.1
    return Tell("sentence_uniformity", "script", score, w,
                f"{len(sents)} sentences, lengths {'very uniform' if cv < 0.3 else 'varied'} (CV {cv:.2f})")


def contraction_rate(text: str) -> Tell:
    w = T.SCRIPT_WEIGHTS["contraction_rate"]
    words = _words(text)
    if len(words) < 40:
        return Tell("contraction_rate", "script", 0.5, w, "too short to judge contractions", applicable=False)
    n = len(CONTRACTION.findall(text))
    per100 = 100 * n / len(words)
    score = float(0.1 + 0.8 * max(0.0, min(1.0, (3.0 - per100) / 3.0)))
    return Tell("contraction_rate", "script", score, w,
                f"{n} contractions in {len(words)} words" + (" — formal, written-sounding" if n == 0 else ""))


def ai_denial(text: str) -> bool:
    return any(re.search(p, text, re.I) for p in AI_DENIAL)


def analyze(text: str) -> list[Tell]:
    if not text or len(_words(text)) < 5:
        return [Tell("script", "script", 0.5, 1.0, "no usable transcript", applicable=False)]
    return [llm_isms(text), disfluency(text), sentence_uniformity(text), contraction_rate(text)]
