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
MIN_SR, MAX_SR = 4_000, 192_000   # WAV sample rates accepted; anything else is refused before allocating
MAX_CHANNELS = 8


class AudioDecodeError(ValueError):
    pass


class AudioTooLong(AudioDecodeError):
    """Over the configured duration cap; the API maps this to 413 instead of 415."""


def _max_audio_s() -> float:
    from .limits import max_audio_s   # same DOUBLESPEAK_MAX_AUDIO_S setting and tolerant parsing as the API cap
    return max_audio_s()


def _refuse_if_too_long(n_frames: int, sr: int) -> None:
    """Pure arithmetic on header values: runs before any sample array is allocated."""
    cap = _max_audio_s()
    if n_frames / sr > cap:
        raise AudioTooLong(f"audio too long: limit is {cap:g} s")


def _wav_to_array(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data)) as w:
        sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        if not MIN_SR <= sr <= MAX_SR:
            raise AudioDecodeError(f"unsupported wav sample rate {sr} (accepted {MIN_SR}-{MAX_SR} Hz)")
        if not 1 <= ch <= MAX_CHANNELS:
            raise AudioDecodeError(f"unsupported wav channel count {ch}")
        n = min(n, len(data) // max(1, ch * sw))   # a header may claim more frames than the file holds
        _refuse_if_too_long(n, sr)
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


def _ffmpeg_cmd(exe: str) -> list[str]:
    # pipe-only protocol whitelist: playlist/concat text must not make ffmpeg open file: or http: URLs.
    # -t bounds the decoded output so a small compressed file cannot expand to gigabytes on stdout.
    return [exe, "-nostdin", "-protocol_whitelist", "pipe", "-loglevel", "error", "-i", "pipe:0",
            "-t", f"{_max_audio_s() + 1:g}", "-ac", "1", "-ar", str(TARGET_SR), "-f", "wav", "pipe:1"]


def _ffmpeg_to_wav(data: bytes) -> bytes:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise AudioDecodeError("non-wav audio needs ffmpeg installed locally (brew install ffmpeg)")
    p = subprocess.run(
        _ffmpeg_cmd(exe),
        input=data, capture_output=True, check=False,
    )
    if p.returncode != 0 or not p.stdout:
        raise AudioDecodeError(f"ffmpeg could not decode audio: {p.stderr.decode(errors='ignore')[:200]}")
    return p.stdout


def resample(x: np.ndarray, sr: int, target: int = TARGET_SR) -> np.ndarray:
    if sr == target:
        return x
    if sr <= 0:
        raise AudioDecodeError("invalid sample rate")
    n_out = int(round(len(x) * target / sr))
    if n_out > _max_audio_s() * target:   # checked before np.linspace/np.interp allocate
        raise AudioTooLong(f"audio too long: limit is {_max_audio_s():g} s")
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
