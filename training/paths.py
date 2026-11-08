"""Shared paths for the training pipeline.

Importing this does NOT import ``doublespeak`` (so the download scripts can run
online without tripping the offline guard). Training/feature steps import torch
and the ``finetune`` helpers separately.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# --- Part A: voice ---
# Reuse the existing finetune/ machinery; put freshly-pulled training data in its
# own tree so it does not clobber the small demo set under finetune/data.
VOICE_DIR: Path = PROJECT_ROOT / "training" / "pellav2-finetune"
VOICE_DATA: Path = VOICE_DIR / "data"            # data/real/<spk>/, data/fake/<spk>/
VOICE_REAL: Path = VOICE_DATA / "real"
VOICE_FAKE: Path = VOICE_DATA / "fake"
VOICE_FEATURES: Path = VOICE_DIR / "features"
TEAM_REAL: Path = PROJECT_ROOT / "data" / "team_real"   # consented team voices

MODELS_DIR: Path = PROJECT_ROOT / "models"
BASE_WEIGHTS: Path = MODELS_DIR / "pellav2_detector.pt"
VOICE_OUT: Path = MODELS_DIR / "pellav2_qwen.pt"

# --- Part B: text ---
TEXT_DIR: Path = PROJECT_ROOT / "training" / "scam-text"
TEXT_PARQUET: Path = TEXT_DIR / "scam_text.parquet"
KEYWORDS_JSON: Path = PROJECT_ROOT / "models" / "keywords.json"
TEXT_MODEL: Path = PROJECT_ROOT / "models" / "scam_text_model.joblib"
OWN_SCRIPTS: Path = PROJECT_ROOT / "data" / "own_scripts"
SCAM_SCRIPTS: Path = PROJECT_ROOT / "data" / "scam_scripts.txt"

SAMPLE_RATE: int = 16_000
LABEL_REAL = 0   # voice: real person   | text: not scam
LABEL_FAKE = 1   # voice: AI-generated  | text: scam


def ensure_dirs() -> None:
    for d in (VOICE_REAL, VOICE_FAKE, VOICE_FEATURES, TEXT_DIR,
              TEAM_REAL, OWN_SCRIPTS, MODELS_DIR):
        d.mkdir(parents=True, exist_ok=True)
