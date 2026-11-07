"""Pellav2 anti-spoof voter: a w2v-BERT 2.0 backbone with learned per-layer weighting and a linear head.

Model: https://huggingface.co/Sadanie/pellav2-audio-deepfake-detector (MIT). Architecture and preprocessing are ported
from the author's reference `pellav2_infer.py` (DC removal, 20 Hz high-pass, 4 s crop, -23 LUFS normalise, pad).
sigmoid(logit) = P(synthetic). The card does not document its training data, so treat scores as unproven until the wild
eval (`run_eval.py --wild`) says otherwise; the weight below is a placeholder.

Hardening versus the reference script:
  * the weights are pinned to one Hub revision and verified against a pinned SHA-256 before they are ever loaded;
  * they are read with PyTorch's restricted unpickler (`weights_only=True`), so a tampered .pt cannot run code;
  * this module never touches the network (`local_files_only`): `make models` (tools/models/prefetch_pella.py) downloads
    the weights and the backbone's small config once; the 2.3 GB backbone is NOT downloaded, the config alone is enough;
  * long calls are scored as at most PELLA_MAX_WINDOWS non-silent 4 s windows (signals/windows.py) to bound latency;
  * anything that goes wrong (missing deps, uncached model, hash mismatch, runtime error) makes the voter applicable=False.
Enable with PELLA_MODEL=Sadanie/pellav2-audio-deepfake-detector (or a path to the .pt, which must match the pinned hash).
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

import numpy as np

from ..types import Tell
from . import windows as win

log = logging.getLogger("doublespeak.pella")
W_PELLA = 4.0                       # 1.6 -> 4.0 (2026-11-07.2) from the wild eval, see pm/AUDITS.md; tier logic untouched
REPO, FILENAME = "Sadanie/pellav2-audio-deepfake-detector", "pellav2_detector.pt"
REVISION = "b668eb4dfe4719665692c73c1d70383680afff6b"
SHA256 = "d21aedfb52e2f87706c2753715a29665482b0f4a034800c31579df5d458559ac"
SIZE = 2_322_248_702
BACKBONE = "facebook/w2v-bert-2.0"  # config only, pinned and hashed like the weights
BACKBONE_REVISION = "da985ba0987f70aaeb84a80f2851cfac8c697a7b"
BACKBONE_CONFIG_SHA256 = "f5572bd5998b68182e9c328a43127ed21fed687f6910497136b91a4e3b0e3675"
MIN_TORCH = (2, 6)                  # weights_only had a bypass (CVE-2025-32434) before torch 2.6
MAX_LAYERS, MAX_HIDDEN = 64, 4096   # a poisoned config must not be able to demand terabytes
SR, CROP, TARGET_LUFS = 16_000, 4 * 16_000, -23.0
_model = None
_device = "cpu"
_error = ""


def _na(why: str) -> Tell:
    return Tell("neural_pella", "acoustic", 0.5, W_PELLA, why, applicable=False)


# ---------------------------------------------------------------- weights: locate, verify, load safely
def weights_path() -> Path | None:
    env = os.environ.get("PELLA_WEIGHTS", "")
    if env:
        return Path(env).expanduser()
    configured = os.environ.get("PELLA_MODEL", "")
    if configured.endswith(".pt"):
        return Path(configured).expanduser()
    try:
        from huggingface_hub import try_to_load_from_cache
        p = try_to_load_from_cache(REPO, FILENAME, revision=REVISION)
    except Exception:  # noqa: BLE001
        return None
    return Path(p) if isinstance(p, str) else None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _identity(real: Path) -> tuple:
    st = real.stat()
    return (st.st_ino, st.st_size, st.st_mtime_ns)


def verify(path: Path) -> bool:
    """True only if the file is byte-identical to the pinned weights. Hashed on EVERY load (a few seconds, once per process):
    an earlier version trusted a '.ds-verified' marker, which a same-size swap defeats (found in review)."""
    try:
        real = path.resolve()
        return real.stat().st_size == SIZE and _sha256(real) == SHA256
    except OSError:
        return False


def check_config(cfg) -> str:
    """Empty string if the backbone config is sane, else why not."""
    layers, hidden = getattr(cfg, "num_hidden_layers", None), getattr(cfg, "hidden_size", None)
    if not (isinstance(layers, int) and 1 <= layers <= MAX_LAYERS and isinstance(hidden, int) and 1 <= hidden <= MAX_HIDDEN):
        return f"backbone config out of bounds (layers={layers}, hidden={hidden})"
    return ""


def backbone_config():
    """The pinned backbone config: located in the local cache, hash-checked, bounds-checked, never downloaded here."""
    from huggingface_hub import try_to_load_from_cache
    from transformers import Wav2Vec2BertConfig
    p = try_to_load_from_cache(BACKBONE, "config.json", revision=BACKBONE_REVISION)
    if not isinstance(p, str):
        raise RuntimeError("backbone config not cached")
    if _sha256(Path(p)) != BACKBONE_CONFIG_SHA256:
        raise RuntimeError("backbone config does not match the pinned SHA-256")
    cfg = Wav2Vec2BertConfig.from_json_file(p)
    why = check_config(cfg)
    if why:
        raise RuntimeError(why)
    return cfg


def safe_state_dict(path: Path):
    """Tensors only. weights_only=True refuses to unpickle arbitrary objects, so a booby-trapped .pt raises instead of running."""
    import torch
    return torch.load(path, map_location="cpu", weights_only=True, mmap=True)


# ---------------------------------------------------------------- model
def _build():
    import torch
    import torch.nn as nn
    from transformers import Wav2Vec2BertModel

    class Detector(nn.Module):
        def __init__(self):
            super().__init__()
            cfg = backbone_config()
            self.backbone = Wav2Vec2BertModel(cfg)
            self.layer_weights = nn.Parameter(torch.zeros(cfg.num_hidden_layers + 1))
            self.head = nn.Linear(cfg.hidden_size, 1)

        @staticmethod
        def features(wav):
            import torchaudio.compliance.kaldi as K
            feats, lens = [], []
            with torch.autocast(device_type=wav.device.type, enabled=False):
                for x in wav.float():
                    nz = torch.nonzero(x).flatten()
                    n_s = int(nz[-1]) + 1 if len(nz) else len(x)
                    f = K.fbank(x[None, :max(n_s, 400)] * 32768.0, num_mel_bins=80, sample_frequency=SR, dither=0.0, window_type="povey")
                    f = (f - f.mean(0, keepdim=True)) / torch.sqrt(f.var(0, keepdim=True) + 1e-7)
                    n = f.shape[0] // 2 * 2
                    feats.append(f[:n].reshape(n // 2, 160))
                    lens.append(n // 2)
            F = max(lens)
            out = torch.zeros(len(feats), F, 160, device=wav.device)
            mask = torch.zeros(len(feats), F, dtype=torch.long, device=wav.device)
            for i, (f, n) in enumerate(zip(feats, lens)):
                out[i, :n] = f
                mask[i, :n] = 1
            return out, mask

        def forward(self, wav):
            feats, mask = self.features(wav)
            hs = self.backbone(input_features=feats, attention_mask=mask, output_hidden_states=True).hidden_states
            w = torch.softmax(self.layer_weights, dim=0)
            h = torch.stack(hs).mul(w[:, None, None, None]).sum(0)
            m = mask[:, :, None].float()
            h = (h * m).sum(1) / m.sum(1).clamp(min=1)
            return self.head(h).squeeze(-1)

    return Detector()


def _load():
    global _model, _device, _error
    if _model is not None or _error:
        return
    path = weights_path()
    if path is None or not path.exists():
        _error = "Pellav2 weights not cached; run `make models` while online"
        return
    try:
        import torch
        real = path.resolve()
        before = _identity(real)
    except Exception as e:  # noqa: BLE001
        _error = f"Pellav2 weights unreadable ({type(e).__name__})"
        return
    if tuple(int(x) for x in torch.__version__.split("+")[0].split(".")[:2]) < MIN_TORCH:
        _error = f"torch {torch.__version__} is too old for the safe weights loader (need >= {'.'.join(map(str, MIN_TORCH))})"
        log.error(_error)
        return
    if not verify(real):
        _error = "Pellav2 weights do not match the pinned SHA-256; refusing to load them"
        log.error(_error)
        return
    try:
        m = _build()
        m.load_state_dict(safe_state_dict(real))           # the SAME resolved path that was hashed
        if _identity(real) != before:                       # swapped between the check and the load
            raise RuntimeError("weights file changed while loading")
        want = os.environ.get("PELLA_DEVICE", "cpu")
        _device = "mps" if want in ("mps", "auto") and torch.backends.mps.is_available() else "cpu"
        _model = m.to(_device).eval()
        log.info("loaded Pellav2 on %s", _device)
    except Exception as e:  # noqa: BLE001 - missing deps, uncached backbone config, bad file: degrade, never raise
        _error = f"Pellav2 unavailable ({type(e).__name__}: {str(e)[:80]}); run `make models` while online"
        log.warning(_error)


# ---------------------------------------------------------------- audio -> scores
def prep(x: np.ndarray) -> np.ndarray:
    """Reference preprocessing for one window: DC removal, 20 Hz high-pass, centre-crop/pad to 4 s, -23 LUFS."""
    from scipy.signal import butter, sosfiltfilt
    x = x.astype(np.float32) - float(np.mean(x))
    if len(x) > 3 * SR // 100:
        x = sosfiltfilt(butter(2, 20.0, btype="highpass", fs=SR, output="sos"), x).astype(np.float32)
    if len(x) > CROP:
        off = (len(x) - CROP) // 2
        x = x[off:off + CROP]
    if len(x):
        gain = float(np.clip(TARGET_LUFS - _loudness(x), -40.0, 40.0))
        x = np.clip(x * 10 ** (gain / 20), -1.0, 1.0).astype(np.float32)
    if len(x) < CROP:
        x = np.concatenate([x, np.zeros(CROP - len(x), np.float32)])
    return x


def _loudness(x: np.ndarray) -> float:
    try:
        import pyloudnorm as pyln
        if len(x) >= int(0.4 * SR):
            v = pyln.Meter(SR).integrated_loudness(x.astype(np.float64))
            if np.isfinite(v):
                return float(v)
    except Exception:  # noqa: BLE001
        pass
    return float(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9) - 0.691)


def score_windows(chunks: list[np.ndarray]) -> list[float]:
    """P(synthetic) for each window (batched). Requires a loaded model."""
    import torch
    batch = torch.from_numpy(np.stack([prep(c) for c in chunks])).to(_device)
    with torch.no_grad():
        return [float(p) for p in torch.sigmoid(_model(batch)).cpu().tolist()]


def pella_vote(x16k: np.ndarray) -> Tell:
    if not os.environ.get("PELLA_MODEL"):
        return _na("no Pellav2 model configured (PELLA_MODEL)")
    try:
        import scipy  # noqa: F401
        import torch  # noqa: F401
        import torchaudio  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as e:
        return _na(f"Pellav2 needs torch, torchaudio, transformers and scipy ({e.name} missing)")
    _load()
    if _model is None:
        return _na(_error or "Pellav2 not loaded")
    ws = win.windows(x16k, SR, win_s=4.0, hop_s=2.0, max_n=int(os.environ.get("PELLA_MAX_WINDOWS", "3")))
    if not ws:
        return _na("no speech found for Pellav2 (all windows silent)")
    try:
        probs = score_windows([c for _, c in ws])
    except Exception as e:  # noqa: BLE001
        log.warning("Pellav2 inference failed: %s", e)
        return _na(f"Pellav2 inference failed ({type(e).__name__})")
    mean, mx = float(np.mean(probs)), float(np.max(probs))
    return Tell("neural_pella", "acoustic", mean, W_PELLA,
                f"Pellav2: P(synthetic) = {mean:.2f} over {len(probs)} window{'s' if len(probs) != 1 else ''} (highest {mx:.2f})")
