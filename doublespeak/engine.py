"""Part C - wire the two TRAINED models into the detection pipeline.

This is the "engine" the task spec refers to. It supplies:

  * the VOICE verdict from the fine-tuned pellav2 head (models/pellav2_qwen.pt
    or the committed head delta), via the existing config switch; and
  * the CONVERSATION verdict from the trained scam-text model
    (models/scam_text_model.joblib) with plain-English reasons drawn from
    models/keywords.json.

Ollama is consulted ONLY when the text model is unsure - a score in the
[0.3, 0.7] band - and never otherwise. Everything runs offline; the only
network call permitted is to a local Ollama on localhost.

Nothing here changes the pipeline's public contract: it still returns
``VoiceResult`` / ``ScamResult`` / ``PipelineResult``, so ``app.py`` and
``get_pipeline`` keep working unchanged. Use :func:`build_engine_pipeline` to
get a pipeline that prefers the trained models, with safe fallbacks when an
artifact is missing.
"""

from __future__ import annotations

import dataclasses
import json
import re
from functools import lru_cache
from pathlib import Path

from . import config
from .detector import (
    Pipeline,
    ScamChecker,
    ScamResult,
    VoiceChecker,
    _dedupe,
    regex_scam_risk,
)
from .deepfake import DeepfakeDetector

# Mid-range band where we defer to Ollama for a second opinion.
OLLAMA_LOW = 0.3
OLLAMA_HIGH = 0.7

TEXT_MODEL_PATH = config.PROJECT_ROOT / "models" / "scam_text_model.joblib"
KEYWORDS_PATH = config.PROJECT_ROOT / "models" / "keywords.json"


def _load_keywords() -> list[tuple[re.Pattern, float, str]]:
    """Load keywords.json into compiled (pattern, weight, reason) triples."""
    if not KEYWORDS_PATH.exists():
        return []
    try:
        data = json.loads(KEYWORDS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[tuple[re.Pattern, float, str]] = []
    for kw in data.get("keywords", []):
        phrase = str(kw.get("phrase", "")).strip()
        if not phrase:
            continue
        # Match the phrase as whole words, case-insensitive.
        pat = re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
        out.append((pat, float(kw.get("weight", 0.0)), str(kw.get("reason", ""))))
    return out


class TrainedScamChecker(ScamChecker):
    """Scam-text verdict from a trained model, with keyword reasons.

    Primary signal: the TF-IDF + logistic-regression model
    (``scam_text_model.joblib``). Reasons come from ``keywords.json`` (the
    phrases that actually fired in the transcript). Ollama is queried ONLY when
    the model's probability is in the uncertain band [0.3, 0.7]; outside it we
    trust the trained model. Falls back to the regex rule engine if the trained
    model is unavailable, so the app never breaks.
    """

    def __init__(self, cfg: config.OllamaConfig = config.OLLAMA) -> None:
        super().__init__(cfg)
        self._pipeline = self._load_text_model()
        self._keywords = _load_keywords()

    @staticmethod
    def _load_text_model():
        if not TEXT_MODEL_PATH.exists():
            return None
        try:
            from joblib import load

            bundle = load(TEXT_MODEL_PATH)
            return bundle.get("pipeline") if isinstance(bundle, dict) else bundle
        except Exception:
            return None

    def _keyword_reasons(self, text: str) -> list[str]:
        """Plain-English reasons for the phrases that fired, strongest first."""
        hits = [(w, reason) for pat, w, reason in self._keywords
                if reason and pat.search(text)]
        hits.sort(key=lambda t: t[0], reverse=True)
        return _dedupe([r for _, r in hits])[:5]

    def score(self, transcript: str) -> ScamResult:
        text = (transcript or "").strip()
        if not text:
            return ScamResult(0.0, [])

        if self._pipeline is None:
            # No trained model present: fall back to the regex rules.
            return regex_scam_risk(text)

        try:
            proba = float(self._pipeline.predict_proba([text])[0][1])
        except Exception:
            return regex_scam_risk(text)

        reasons = self._keyword_reasons(text)

        # Only ask Ollama when the trained model is genuinely unsure.
        if OLLAMA_LOW <= proba <= OLLAMA_HIGH:
            llm = self._ollama_scam_risk(text)
            if llm is not None:
                # Blend: average the two uncertain opinions, keep both reasons.
                blended = (proba + llm.risk) / 2.0
                merged = _dedupe(reasons + llm.reasons)
                return ScamResult(risk=blended,
                                  reasons=merged or ["This call sounds risky."])

        if not reasons and proba >= config.RISK_MEDIUM:
            reasons = ["The wording matches known scam calls."]
        return ScamResult(risk=proba, reasons=reasons)


def _finetuned_voice_checker() -> VoiceChecker:
    """VoiceChecker using the fine-tuned pellav2 head when available."""
    # active_weights_path / head-delta logic already lives in DeepfakeConfig +
    # DeepfakeDetector; we just request the fine-tuned head here.
    cfg = dataclasses.replace(config.DEEPFAKE, use_finetuned_head=True)
    return VoiceChecker(DeepfakeDetector(cfg))


class EnginePipeline(Pipeline):
    """Pipeline wired to the trained voice + text models."""

    def __init__(self) -> None:
        # Build the base Pipeline, then swap in the trained components.
        super().__init__()
        self._voice = _finetuned_voice_checker()
        self._scam = TrainedScamChecker()


@lru_cache(maxsize=1)
def build_engine_pipeline() -> EnginePipeline:
    """Process-wide singleton pipeline using the trained models."""
    return EnginePipeline()
