"""Shared paths for the fine-tuning pipeline.

Importing this does NOT import ``doublespeak`` (so ``make_dataset.py`` can run
online). The feature/training scripts import ``doublespeak`` separately and run
offline.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

MODELS_DIR: Path = PROJECT_ROOT / "models"
BASE_WEIGHTS: Path = MODELS_DIR / "pellav2_detector.pt"
FINETUNED_WEIGHTS: Path = MODELS_DIR / "pellav2_detector_finetuned.pt"

# Seed audio already in the repo.
DATA_CALLS: Path = PROJECT_ROOT / "data" / "calls"
HUMAN_DIR: Path = DATA_CALLS / "human"
QWEN_DIR: Path = DATA_CALLS / "qwen3tts"
GRADIUM_DIRS = [DATA_CALLS / "gradium", DATA_CALLS / "gradium_stock"]
TEST_AUDIO_DIR: Path = PROJECT_ROOT / "test_audio"

SAMPLE_RATE: int = 16_000
LABEL_REAL = 0
LABEL_FAKE = 1
