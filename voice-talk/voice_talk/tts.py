"""Speech synthesis: Qwen3-TTS Base voice cloning, one cached clone prompt per voice.

qwen-tts 0.1.1 exposes no streaming *output* (its `non_streaming_mode` flag only
changes how text is fed in), so latency is controlled by sentence/clause chunking.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Protocol

import numpy as np


class Synthesizer(Protocol):
    def prepare_voice(self, name: str, ref_path: Path, ref_text: str) -> None: ...
    def synthesize(self, text: str, language_name: str, voice: str) -> tuple[np.ndarray, int]: ...


class Qwen3Synth:
    def __init__(self, model_dir: Path, device: str | None = None):
        self.model_dir = Path(model_dir)
        self.device = device
        self.model = None
        self._prompts: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()
        self._warm = False

    def load(self) -> None:
        import torch
        from qwen_tts import Qwen3TTSModel

        if not self.model_dir.exists():
            raise FileNotFoundError(f"{self.model_dir} not found; run: python setup_models.py")
        # Prefer an NVIDIA GPU (CUDA build of torch), then Apple MPS, then CPU.
        # VT_TTS_DEVICE=cpu|cuda|mps overrides the automatic choice.
        want = os.environ.get("VT_TTS_DEVICE", "").strip().lower()
        if want:
            dev = want
        elif torch.cuda.is_available():
            dev = "cuda"
        elif torch.backends.mps.is_available():
            dev = "mps"
        else:
            dev = "cpu"
        dev = self.device or dev
        self.device = dev
        self.model = Qwen3TTSModel.from_pretrained(
            str(self.model_dir), dtype=torch.bfloat16 if dev != "cpu" else torch.float32,
            attn_implementation="sdpa", device_map=dev)

    def prepare_voice(self, name: str, ref_path: Path, ref_text: str) -> None:
        mtime = Path(ref_path).stat().st_mtime
        with self._lock:
            hit = self._prompts.get(name)
            if hit and hit[0] == mtime:
                return  # ONE cached clone prompt per reference voice
            prompt = self.model.create_voice_clone_prompt(ref_audio=str(ref_path), ref_text=ref_text)
            self._prompts[name] = (mtime, prompt)
            if not self._warm:  # first MPS call compiles kernels (~3 s); pay it before the session starts
                self.model.generate_voice_clone(text="Hi.", language="English", voice_clone_prompt=prompt, max_new_tokens=40)
                self._warm = True

    def forget_voice(self, name: str) -> None:
        self._prompts.pop(name, None)

    def synthesize(self, text: str, language_name: str, voice: str) -> tuple[np.ndarray, int]:
        prompt = self._prompts[voice][1]
        max_new = int(min(1800, 24 + 4.2 * len(text)))  # 12 Hz codec: bound runaway generation
        with self._lock:
            wavs, sr = self.model.generate_voice_clone(
                text=text, language=language_name, voice_clone_prompt=prompt, max_new_tokens=max_new)
        return np.asarray(wavs[0], dtype=np.float32), int(sr)
