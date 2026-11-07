"""pellav2 AI-cloned-voice detector (fully offline).

Ported from the model author's reference ``pellav2_infer.py`` (see
https://huggingface.co/Sadanie/pellav2-audio-deepfake-detector) and adapted to:

* run on an **in-memory** float32 array instead of reading a WAV file, and
* load weights from a **local** path, so nothing is fetched at runtime.

The classifier is a ``facebook/w2v-bert-2.0`` backbone with learned per-layer
weighting and a linear head producing a single logit. ``sigmoid(logit)`` is the
probability that the clip is synthetic (AI-cloned).

Preprocessing matches the reference exactly: DC removal, 20 Hz high-pass,
centre-crop to 4 s, loudness normalisation to -23 LUFS, pad to 4 s.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import config
from .config import DeepfakeConfig

_SR = config.SAMPLE_RATE


@dataclass
class DeepfakeResult:
    """Outcome of running the detector on one clip."""

    probability: float  # P(fake), 0.0-1.0
    is_fake: bool


def _build_detector_class():
    """Return the ``Detector`` nn.Module class (imports torch lazily)."""
    import torch
    import torch.nn as nn

    class Detector(nn.Module):
        """w2v-BERT backbone + learned layer weighting + linear head."""

        def __init__(self) -> None:
            super().__init__()
            from transformers import Wav2Vec2BertModel

            self.backbone = Wav2Vec2BertModel.from_pretrained(config.DEEPFAKE.backbone)
            self.layer_weights = nn.Parameter(
                torch.zeros(self.backbone.config.num_hidden_layers + 1)
            )
            self.head = nn.Linear(self.backbone.config.hidden_size, 1)

        @staticmethod
        def features(wav):  # noqa: ANN001
            import torchaudio.compliance.kaldi as K

            feats, lens = [], []
            with torch.autocast(device_type=wav.device.type, enabled=False):
                for x in wav.float():
                    nz = torch.nonzero(x).flatten()
                    n_s = int(nz[-1]) + 1 if len(nz) else len(x)
                    f = K.fbank(
                        x[None, : max(n_s, 400)] * 32768.0,
                        num_mel_bins=80,
                        sample_frequency=_SR,
                        dither=0.0,
                        window_type="povey",
                    )
                    f = (f - f.mean(0, keepdim=True)) / torch.sqrt(
                        f.var(0, keepdim=True) + 1e-7
                    )
                    n = f.shape[0] // 2 * 2
                    feats.append(f[:n].reshape(n // 2, 160))
                    lens.append(n // 2)
            max_len = max(lens)
            out = torch.zeros(len(feats), max_len, 160, device=wav.device)
            mask = torch.zeros(len(feats), max_len, dtype=torch.long, device=wav.device)
            for i, (f, n) in enumerate(zip(feats, lens)):
                out[i, :n] = f
                mask[i, :n] = 1
            return out, mask

        def forward(self, wav):  # noqa: ANN001
            feats, mask = self.features(wav)
            hs = self.backbone(
                input_features=feats,
                attention_mask=mask,
                output_hidden_states=True,
            ).hidden_states
            w = torch.softmax(self.layer_weights, dim=0)
            h = torch.stack(hs).mul(w[:, None, None, None]).sum(0)
            m = mask[:, :, None].float()
            h = (h * m).sum(1) / m.sum(1).clamp(min=1)
            return self.head(h).squeeze(-1)

    return Detector


def _loudness(x: np.ndarray) -> float:
    """Integrated loudness (LUFS) with an RMS fallback. Matches reference."""
    try:
        import pyloudnorm as pyln

        if len(x) >= int(0.4 * _SR):
            v = pyln.Meter(_SR).integrated_loudness(x.astype(np.float64))
            if np.isfinite(v):
                return float(v)
    except Exception:
        pass
    return float(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9) - 0.691)


def _preprocess(wav: np.ndarray, cfg: DeepfakeConfig) -> np.ndarray:
    """Replicate the reference clip preprocessing on an in-memory array."""
    from scipy.signal import butter, sosfiltfilt

    crop = cfg.crop_seconds * _SR
    wav = np.asarray(wav, dtype=np.float32)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    wav = wav - wav.mean()
    if len(wav) > 3 * _SR // 100:
        wav = sosfiltfilt(
            butter(2, 20.0, btype="highpass", fs=_SR, output="sos"), wav
        )
    wav = wav.astype(np.float32)
    if len(wav) > crop:
        off = (len(wav) - crop) // 2
        wav = wav[off : off + crop]
    if len(wav):
        gain = float(np.clip(cfg.target_lufs - _loudness(wav), -40.0, 40.0))
        wav = np.clip(wav * 10 ** (gain / 20), -1.0, 1.0).astype(np.float32)
    if len(wav) < crop:
        wav = np.concatenate([wav, np.zeros(crop - len(wav), np.float32)])
    return wav


class DeepfakeDetector:
    """Loads pellav2 once (lazily) and scores in-memory clips."""

    def __init__(self, cfg: DeepfakeConfig = config.DEEPFAKE) -> None:
        self.cfg = cfg
        self._model = None
        self._device = None

    def _ensure_model(self):
        """Load backbone + local weights once. Raises if weights are missing.

        Weight selection when ``cfg.use_finetuned_head`` is set:
          1. a full fine-tuned checkpoint (``finetuned_weights_path``) if present;
          2. else the base backbone plus the tiny committed head delta
             (``finetuned_head_path``: layer_weights + head only, ~6 KB);
          3. else the base weights (safe fallback - never breaks inference).
        """
        if self._model is not None:
            return self._model
        import torch

        weights_path = self.cfg.active_weights_path
        if not weights_path.exists():
            raise FileNotFoundError(
                f"pellav2 weights not found at {weights_path}. Run the "
                "one-time setup to place 'pellav2_detector.pt' there (see README)."
            )
        device = "cpu"  # product targets CPU-only, offline machines
        Detector = _build_detector_class()
        model = Detector().to(device)
        state = torch.load(weights_path, map_location=device)
        model.load_state_dict(state)

        # Apply the lightweight head delta if requested and no full checkpoint
        # was used. This reconstructs the fine-tuned detector from base backbone
        # + the ~6 KB trained head, so the big file never needs shipping.
        if (
            self.cfg.use_finetuned_head
            and weights_path == self.cfg.weights_path
            and self.cfg.finetuned_head_path.exists()
        ):
            head = torch.load(self.cfg.finetuned_head_path, map_location=device)
            with torch.no_grad():
                model.layer_weights.copy_(head["layer_weights"])
                model.head.weight.copy_(head["head.weight"])
                model.head.bias.copy_(head["head.bias"])

        model.eval()
        self._model = model
        self._device = device
        return model

    def detect(self, audio: np.ndarray) -> DeepfakeResult:
        """Return P(fake) and a boolean flag for an in-memory clip."""
        import torch

        model = self._ensure_model()
        clip = _preprocess(audio, self.cfg)
        with torch.no_grad():
            x = torch.from_numpy(clip)[None].to(self._device)
            prob = float(torch.sigmoid(model(x)).item())
        return DeepfakeResult(
            probability=prob,
            is_fake=prob >= self.cfg.fake_threshold,
        )
