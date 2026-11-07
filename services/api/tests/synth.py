"""Synthetic audio fixtures for tests and eval. These validate the *mechanics* of each acoustic tell
(the pipeline reacts the right way to breath, pause variance, pitch wander, noise floor). They are not
a substitute for real Gradium/ElevenLabs clips — see tools/redteam for those.
"""
from __future__ import annotations

import io
import wave

import numpy as np

SR = 16_000


def _phrase(f0_track: np.ndarray, sr: int = SR) -> np.ndarray:
    """Glottal-ish pulse train (sawtooth) at a time-varying F0, with a two-formant-ish envelope."""
    phase = np.cumsum(2 * np.pi * f0_track / sr)
    saw = 2 * ((phase / (2 * np.pi)) % 1.0) - 1.0
    # crude vocal-tract colouring: low-pass by running mean
    k = np.ones(8) / 8
    voiced = np.convolve(saw, k, mode="same")
    env = np.ones_like(voiced)
    n_att = int(0.03 * sr)
    env[:n_att] = np.linspace(0, 1, n_att)
    env[-n_att:] = np.linspace(1, 0, n_att)
    return 0.3 * voiced * env


def make_call(kind: str, seconds: float = 14.0, seed: int = 0, sr: int = SR, phone_band: bool = False) -> np.ndarray:
    """kind: 'human' | 'tts'. Returns float32 mono samples."""
    rng = np.random.default_rng(seed)
    out = []
    t_total = 0.0
    base_f0 = 120 + 40 * rng.random()
    while t_total < seconds:
        if kind == "human":
            dur = rng.uniform(0.5, 1.8)
            pause = float(np.clip(rng.lognormal(-0.7, 0.7), 0.15, 2.5))   # messy, long-tailed pauses
            n = int(dur * sr)
            walk = np.cumsum(rng.normal(0, 0.8, n)) / np.sqrt(np.arange(1, n + 1))
            f0 = base_f0 * (1 + 0.28 * np.sin(np.linspace(0, rng.uniform(2, 6), n)) + 0.04 * walk)
            breath = rng.normal(0, 0.012, int(0.3 * sr)) * np.hanning(int(0.3 * sr))
            seg = np.concatenate([breath, _phrase(f0, sr)])
        else:
            dur = rng.uniform(1.4, 1.8)
            pause = 0.42 + rng.normal(0, 0.015)
            n = int(dur * sr)
            f0 = base_f0 * (1 + 0.03 * np.sin(np.linspace(0, 3, n)))
            seg = _phrase(f0, sr)
        out.append(seg)
        out.append(np.zeros(int(max(0.1, pause) * sr)))
        t_total += len(seg) / sr + pause
    x = np.concatenate(out)[: int(seconds * sr)]
    if kind == "human":
        x = x + rng.normal(0, 0.0025, len(x))      # ≈ -52 dBFS room/line noise, slightly non-stationary
        x = x + 0.0015 * np.sin(2 * np.pi * 0.3 * np.arange(len(x)) / sr) * rng.normal(0, 1, len(x))
    else:
        x = x + rng.normal(0, 0.00002, len(x))     # digital-silence floor
    if phone_band:
        x = _lowpass(x, 3400, sr)
    return np.clip(x, -1, 1).astype(np.float32)


def _lowpass(x: np.ndarray, cutoff: float, sr: int) -> np.ndarray:
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    # raised-cosine roll-off (cutoff-400 → cutoff+200 Hz) to avoid brick-wall pre-ringing
    ramp = np.clip((freqs - (cutoff - 400)) / 600.0, 0, 1)
    spec *= 0.5 * (1 + np.cos(np.pi * ramp))
    return np.fft.irfft(spec, n=len(x))


def to_wav_bytes(x: np.ndarray, sr: int = SR) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()
