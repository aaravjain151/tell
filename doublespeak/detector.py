"""End-to-end scam-call detection pipeline.

One module, one cached entry point. Given an audio clip it:

1. loads audio to 16 kHz mono float32, peak-normalised (:func:`load_audio`);
2. scores the voice for AI-cloning with pellav2 over rolling 4 s / 2 s windows,
   skipping silence, returning a mean + per-window scores;
3. transcribes with faster-whisper (VAD on, to stop hallucinations);
4. judges scam-talk with Ollama ``llama3.2:3b`` (JSON, temperature 0), with a
   regex rule engine as both a fallback and a safety net;
5. fuses the two signals into one risk level and returns a
   :class:`PipelineResult` dataclass.

Models are loaded once and cached (:func:`get_pipeline`). Audio and transcript
are held only in memory and are never written to disk by this module.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from . import config
from .deepfake import DeepfakeDetector, _preprocess
from .transcribe import Transcriber

_SR = config.SAMPLE_RATE


# --------------------------------------------------------------------------- #
# 1. Audio loading
# --------------------------------------------------------------------------- #


def load_audio(path: str) -> np.ndarray:
    """Load any audio file to a 16 kHz mono float32 array, peak-normalised.

    Downmix and resampling are handled by librosa. The signal is scaled so its
    maximum absolute sample is 1.0; a silent (all-zero) signal is returned
    unchanged to avoid dividing by zero. Nothing is written to disk.
    """
    import librosa

    wav, _ = librosa.load(path, sr=_SR, mono=True)
    wav = wav.astype(np.float32, copy=False)
    peak = float(np.max(np.abs(wav))) if wav.size else 0.0
    if peak > 0.0:
        wav = (wav / peak).astype(np.float32)
    return wav


# --------------------------------------------------------------------------- #
# 2. Voice (deepfake) check with rolling windows
# --------------------------------------------------------------------------- #


@dataclass
class VoiceResult:
    """Mean fake probability plus the per-window scores that produced it."""

    mean_probability: float
    per_window: list[float] = field(default_factory=list)


def _rms(x: np.ndarray) -> float:
    """Root-mean-square energy of a window."""
    return float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0


class VoiceChecker:
    """Scores AI-cloning over rolling 4 s / 2 s windows using pellav2.

    The pellav2 preprocessing (DC removal, 20 Hz high-pass, 4 s centre crop,
    -23 LUFS normalise, pad) is reused verbatim from :mod:`doublespeak.deepfake`,
    which is ported from the model author's reference inference script.
    """

    def __init__(self, detector: DeepfakeDetector | None = None) -> None:
        self._detector = detector or DeepfakeDetector()

    def _score_clip(self, clip: np.ndarray) -> float:
        """Preprocess and score one <=4 s clip, returning P(fake)."""
        import torch

        model = self._detector._ensure_model()  # cached after first call
        prepared = _preprocess(clip, self._detector.cfg)
        with torch.no_grad():
            x = torch.from_numpy(prepared)[None].to(self._detector._device)
            return float(torch.sigmoid(model(x)).item())

    def score(self, audio: np.ndarray) -> VoiceResult:
        """Return mean + per-window P(fake), skipping silent windows."""
        win = int(config.VOICE_WINDOW_SECONDS * _SR)
        hop = int(config.VOICE_HOP_SECONDS * _SR)

        # Short clips: a single centre crop (preprocessing crops to 4 s anyway).
        if audio.size <= win:
            if _rms(audio) < config.SILENCE_RMS:
                return VoiceResult(0.0, [])
            p = self._score_clip(audio)
            return VoiceResult(p, [p])

        scores: list[float] = []
        for start in range(0, audio.size - win + 1, hop):
            window = audio[start : start + win]
            if _rms(window) < config.SILENCE_RMS:
                continue  # skip silence
            scores.append(self._score_clip(window))

        if not scores:
            return VoiceResult(0.0, [])
        return VoiceResult(float(np.mean(scores)), scores)


# --------------------------------------------------------------------------- #
# 4. Scam-talk check (Ollama + regex safety net)
# --------------------------------------------------------------------------- #


@dataclass
class ScamResult:
    """Scam risk in 0.0-1.0 plus plain-language reasons."""

    risk: float
    reasons: list[str] = field(default_factory=list)


_SCAM_SYSTEM = (
    "You detect phone scams aimed at older people. Read the transcript and "
    "judge how likely it is a scam. Look for urgency, secrecy, emergencies "
    "(arrest, accident, kidnapping), and requests for money, gift cards, "
    "crypto, wire transfers, codes or PINs. Reply with ONLY a JSON object."
)

_SCAM_PROMPT = (
    'Transcript:\n"""\n{transcript}\n"""\n\n'
    'Return JSON: {{"risk": <integer 0-100>, "reasons": [<short plain '
    'sentences an older person understands>]}}.'
)

#: Pre-compile the rule table once.
_COMPILED_RULES = [
    (re.compile(pat, re.IGNORECASE), weight, reason)
    for pat, weight, reason in config.SCAM_RULES
]


def regex_scam_risk(transcript: str) -> ScamResult:
    """Score scam risk with the local regex rule engine (no network)."""
    text = transcript or ""
    total = 0.0
    reasons: list[str] = []
    for pattern, weight, reason in _COMPILED_RULES:
        if pattern.search(text):
            total += weight
            reasons.append(reason)
    return ScamResult(risk=min(total, 1.0), reasons=reasons)


class ScamChecker:
    """Ollama JSON scorer with a regex fallback and safety net."""

    def __init__(self, cfg: config.OllamaConfig = config.OLLAMA) -> None:
        self.cfg = cfg

    def _ollama_scam_risk(self, transcript: str) -> ScamResult | None:
        """Query the local LLM. Return None if unavailable or unparsable."""
        payload = {
            "model": self.cfg.model,
            "system": _SCAM_SYSTEM,
            "prompt": _SCAM_PROMPT.format(transcript=transcript),
            "stream": False,
            "format": "json",
            "options": {"temperature": self.cfg.temperature},
        }
        try:
            req = urllib.request.Request(
                f"{self.cfg.host}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.cfg.timeout) as resp:
                reply = json.loads(resp.read().decode("utf-8"))
            parsed = json.loads(reply.get("response", "{}"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return None

        try:
            risk = max(0, min(100, int(parsed.get("risk", 0)))) / 100.0
        except (TypeError, ValueError):
            risk = 0.0
        raw_reasons = parsed.get("reasons", [])
        reasons = (
            [str(r).strip() for r in raw_reasons if str(r).strip()]
            if isinstance(raw_reasons, list)
            else []
        )
        return ScamResult(risk=risk, reasons=reasons)

    def score(self, transcript: str) -> ScamResult:
        """Score a transcript, using regex as fallback and safety net."""
        text = (transcript or "").strip()
        if not text:
            return ScamResult(0.0, [])

        rules = regex_scam_risk(text)
        llm = self._ollama_scam_risk(text)

        if llm is None:
            # Ollama unavailable: rely on the regex rules.
            return rules

        # Safety net: if the rules are more alarmed than the LLM, trust them and
        # merge their reasons in. Otherwise keep the LLM's assessment.
        if rules.risk > llm.risk:
            merged = _dedupe(llm.reasons + rules.reasons)
            return ScamResult(risk=rules.risk, reasons=merged)
        return ScamResult(risk=llm.risk, reasons=_dedupe(llm.reasons))


def _dedupe(items: list[str]) -> list[str]:
    """Order-preserving de-duplication of reason strings."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


# --------------------------------------------------------------------------- #
# 5. Fusion + levels
# --------------------------------------------------------------------------- #

LEVEL_HIGH = "High"
LEVEL_MEDIUM = "Medium"
LEVEL_LOW = "Low"


def fuse_risk(voice: float, scam: float) -> float:
    """Fuse voice and scam scores (both 0-1) into one risk (0-1)."""
    risk = config.VOICE_WEIGHT * voice + config.SCAM_WEIGHT * scam
    if voice > config.ESCALATE_VOICE_ABOVE and scam > config.ESCALATE_SCAM_ABOVE:
        risk = max(risk, config.ESCALATED_RISK_FLOOR)
    return float(min(max(risk, 0.0), 1.0))


def risk_level(risk: float) -> str:
    """Map a fused risk to a plain-language level."""
    if risk >= config.RISK_HIGH:
        return LEVEL_HIGH
    if risk >= config.RISK_MEDIUM:
        return LEVEL_MEDIUM
    return LEVEL_LOW


# --------------------------------------------------------------------------- #
# 6. Result + pipeline
# --------------------------------------------------------------------------- #


@dataclass
class PipelineResult:
    """Everything the UI needs from one run of the pipeline."""

    risk: float  # 0.0-1.0 fused
    level: str  # "High" | "Medium" | "Low"
    voice_score: float  # 0.0-1.0 mean fake probability
    scam_score: float  # 0.0-1.0
    reasons: list[str]  # plain language
    per_window_voice: list[float]
    transcript: str


class Pipeline:
    """Holds the cached models and runs the full detection on one clip."""

    def __init__(self) -> None:
        self._voice = VoiceChecker()
        self._transcriber = Transcriber()
        self._scam = ScamChecker()

    def run(self, audio: np.ndarray) -> PipelineResult:
        """Run voice + transcript + scam checks and fuse them."""
        voice = self._voice.score(audio)
        transcript = self._transcriber.transcribe(audio).text
        scam = self._scam.score(transcript)

        risk = fuse_risk(voice.mean_probability, scam.risk)
        level = risk_level(risk)

        reasons = list(scam.reasons)
        if voice.mean_probability > config.ESCALATE_VOICE_ABOVE:
            reasons.insert(0, "The voice may be an AI copy, not a real person.")
        if not reasons:
            reasons = ["Nothing in this clip looked like a scam."]

        return PipelineResult(
            risk=risk,
            level=level,
            voice_score=voice.mean_probability,
            scam_score=scam.risk,
            reasons=reasons,
            per_window_voice=voice.per_window,
            transcript=transcript,
        )

    def run_file(self, path: str) -> PipelineResult:
        """Convenience: load a file in memory and run the pipeline."""
        return self.run(load_audio(path))


@lru_cache(maxsize=1)
def get_pipeline() -> Pipeline:
    """Return the process-wide singleton pipeline (models loaded once)."""
    return Pipeline()
