"""One-time, online model download for Tell.

Run this ONCE on a trusted machine with internet access to download every model
into the local ``models/`` folder and the faster-whisper / transformers caches.
After this, the app runs 100% offline (HF_HUB_OFFLINE is enforced at runtime).

    python download_models.py

What it fetches:
  * pellav2 weights ``pellav2_detector.pt`` + ``config.json`` -> models/
  * the ``facebook/w2v-bert-2.0`` backbone -> Hugging Face cache
  * the faster-whisper ``base`` CTranslate2 model -> models/faster-whisper-base

This script intentionally does NOT import ``doublespeak`` (which would force
offline mode). It is the only part of the project permitted to use the network,
and only at install time - never at runtime.

The scam checker needs Ollama, installed separately, with the model pulled:
    ollama pull llama3.2:3b
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
MODELS_DIR = PROJECT_ROOT / "models"
HUB_REPO = "Sadanie/pellav2-audio-deepfake-detector"
BACKBONE = "facebook/w2v-bert-2.0"
WHISPER_SIZE = "base"


def fetch_pellav2() -> None:
    """Download pellav2 weights + config into models/."""
    from huggingface_hub import hf_hub_download

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading pellav2 weights from {HUB_REPO} ...")
    weights = hf_hub_download(HUB_REPO, "pellav2_detector.pt")
    cfg = hf_hub_download(HUB_REPO, "config.json")
    shutil.copy2(weights, MODELS_DIR / "pellav2_detector.pt")
    shutil.copy2(cfg, MODELS_DIR / "config.json")
    print(f"  -> {MODELS_DIR / 'pellav2_detector.pt'}")


def fetch_backbone() -> None:
    """Pre-cache the w2v-BERT backbone so it loads offline later."""
    from transformers import Wav2Vec2BertModel

    print(f"Downloading backbone {BACKBONE} (this is large) ...")
    Wav2Vec2BertModel.from_pretrained(BACKBONE)
    print("  -> cached in the Hugging Face cache")


def fetch_whisper() -> None:
    """Download the faster-whisper base model into models/faster-whisper-base."""
    from faster_whisper import download_model

    target = MODELS_DIR / "faster-whisper-base"
    print(f"Downloading faster-whisper '{WHISPER_SIZE}' model ...")
    download_model(WHISPER_SIZE, output_dir=str(target))
    print(f"  -> {target}")


def main() -> int:
    print("Tell one-time model download (requires internet).\n")
    try:
        fetch_pellav2()
        fetch_backbone()
        fetch_whisper()
    except Exception as exc:  # pragma: no cover - setup-time diagnostics
        print(f"\nDownload failed: {exc}", file=sys.stderr)
        return 1
    print(
        "\nDone. Models are local. The app will now run fully offline.\n"
        "Remember to install Ollama and run: ollama pull llama3.2:3b"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
