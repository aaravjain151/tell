from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TTS_DIRS = {"0.6B": "Qwen3-TTS-12Hz-0.6B-Base", "1.7B": "Qwen3-TTS-12Hz-1.7B-Base"}


@dataclass
class Config:
    host: str = "127.0.0.1"  # loopback only; run.py refuses anything else
    port: int = 8765
    tts_model: str = field(default_factory=lambda: os.environ.get("VT_TTS", "0.6B"))
    backend: str = field(default_factory=lambda: os.environ.get("VT_BACKEND", "ollama"))
    llm_model: str | None = field(default_factory=lambda: os.environ.get("VT_LLM_MODEL"))
    models_dir: Path = ROOT / "models"
    voices_dir: Path = ROOT / "voices"
    outputs_dir: Path = ROOT / "outputs"  # created only when the user ticks "save audio"

    @property
    def tts_path(self) -> Path:
        return self.models_dir / TTS_DIRS[self.tts_model]
