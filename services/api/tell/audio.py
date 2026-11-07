"""Decode uploaded audio into a mono float32 numpy array at 16 kHz. numpy + stdlib only.

WAV (PCM 8/16/24/32-bit) is decoded with the `wave` module. Anything else (webm/ogg/mp3 from
MediaRecorder) is converted through `ffmpeg` on the local machine via a pipe — nothing is written
to disk and nothing leaves the device. If ffmpeg is missing, raise a clear error so the UI can say
"record as WAV or install ffmpeg".
"""
from __future__ import annotations

import io
import shutil
import subprocess
import wave

import numpy as np

TARGET_SR = 16_000


class AudioDecodeError(ValueError):
    pass


def _wav_to_array(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data)) as w:
        sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if sw == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128
    elif sw == 2:
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    elif sw == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        i = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        i = np.where(i & 0x800000, i - 0x1000000, i)
        x = i.astype(np.float32) / 8388608
    elif sw == 4:
        x = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648
    else:
        raise AudioDecodeError(f"unsupported wav sample width {sw}")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def _ffmpeg_to_wav(data: bytes) -> bytes:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise AudioDecodeError("non-wav audio needs ffmpeg installed locally (brew install ffmpeg)")
    p = subprocess.run(
        [exe, "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", str(TARGET_SR), "-f", "wav", "pipe:1"],
        input=data, capture_output=True, check=False,
    )
    if p.returncode != 0 or not p.stdout:
        raise AudioDecodeError(f"ffmpeg could not decode audio: {p.stderr.decode(errors='ignore')[:200]}")
    return p.stdout


def resample(x: np.ndarray, sr: int, target: int = TARGET_SR) -> np.ndarray:
    if sr == target:
        return x
    n_out = int(round(len(x) * target / sr))
    src_t = np.linspace(0.0, 1.0, num=len(x), endpoint=False)
    dst_t = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(dst_t, src_t, x).astype(np.float32)


def decode(data: bytes) -> tuple[np.ndarray, int, int]:
    """Return (samples_16k_mono, original_sample_rate, duration_ms)."""
    if not data:
        raise AudioDecodeError("empty audio")
    if data[:4] == b"RIFF":
        x, sr = _wav_to_array(data)
    else:
        x, sr = _wav_to_array(_ffmpeg_to_wav(data))
    orig_sr = sr
    x = resample(x, sr)
    x = np.clip(x, -1.0, 1.0).astype(np.float32)
    return x, orig_sr, int(1000 * len(x) / TARGET_SR)
