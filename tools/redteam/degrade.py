#!/usr/bin/env python3
"""Push every clip through named channel conditions and back to 16 kHz mono WAV, IDENTICALLY for every class.

    python3 tools/redteam/degrade.py [DIR=data/calls] [--only opus8k,g711_mulaw8k] [--force] [--list]

Recursive (data/calls/<engine>/ and data/calls/human/...). For <stem>.wav writes <stem>.<condition>.wav and copies <stem>.txt.
Idempotent: skips existing outputs unless --force; never reads its own *.<condition>.wav outputs as inputs. Needs ffmpeg + numpy.
Deterministic: every random element (loss pattern, RIR tail, room noise) uses a fixed seed, so reruns give identical files.
No dataset or network is used; the room impulse response is synthesised with numpy.

Conditions
  opus8k                       libopus 12 kbps @ 8 kHz (same as tools/redteam/degrade.sh; eval label "opus-8k")
  amr_nb                       AMR-NB 12.2 kbps via ffmpeg libopencore_amrnb. UNAVAILABLE on many ffmpeg builds (Homebrew's
                               has the decoder only): then it is skipped with a message, never faked.
  g711_mulaw8k                 G.711 mu-law, 8 kHz
  g711_alaw8k                  G.711 A-law, 8 kHz
  opus_lowbitrate_with_loss    libopus 6 kbps @ 8 kHz, then ~7% packet loss in bursts (Gilbert-Elliott, 20 ms packets),
                               concealed by repeating the previous good packet with 6 dB/packet decay and a 2 ms crossfade.
                               This is OUR crude concealment applied after decode, not libopus's own PLC: a documented stand-in.
  speaker_rerecord_sim         replay through a loudspeaker and a room: synthetic RIR (direct + early reflections + RT60 0.45 s tail),
                               150 Hz high-pass, 4 kHz low-pass (8th order), room noise at ~35 dB SNR. Not a measured RIR.
  chain_pstn_voip              g711_mulaw8k -> opus_lowbitrate_with_loss
  chain_replay_call            speaker_rerecord_sim -> opus8k
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

SR = 16_000
PKT = 320            # 20 ms packets at 16 kHz


# --- ffmpeg helpers ---------------------------------------------------------------------------------------------------
def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *args], check=True)


def has_encoder(name: str) -> bool:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    return any(line.split()[1:2] == [name] for line in out.splitlines() if line.startswith(" "))


def read_wav(path: Path) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def write_wav(path: Path, x: np.ndarray) -> None:
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2")
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "x.raw"
        raw.write_bytes(pcm.tobytes())
        _ff("-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", str(raw), "-c:a", "pcm_s16le", str(path))


def through_codec(x: np.ndarray, enc: list[str], ext: str, codec_sr: int) -> np.ndarray:
    """x (16 kHz) -> ffmpeg encode at codec_sr -> decode -> 16 kHz."""
    with tempfile.TemporaryDirectory() as td:
        a, b = Path(td) / "in.wav", Path(td) / f"c.{ext}"
        write_wav(a, x)
        _ff("-i", str(a), "-ac", "1", "-ar", str(codec_sr), *enc, str(b))
        out = Path(td) / "out.wav"
        _ff("-i", str(b), "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", str(out))
        y = read_wav(out)
    return y


# --- numpy channel pieces ---------------------------------------------------------------------------------------------
def packet_loss(x: np.ndarray, p_gb: float = 0.04, p_bg: float = 0.5, seed: int = 1234) -> tuple[np.ndarray, float]:
    """Gilbert-Elliott bursty loss on 20 ms packets, with repeat-and-decay concealment. Returns (audio, loss_fraction)."""
    rng = np.random.default_rng(seed)
    n = len(x) // PKT
    y = x.copy()
    bad, lost, run = False, 0, 0
    last = np.zeros(PKT, np.float32)
    for i in range(n):
        bad = (rng.random() < p_gb) if not bad else (rng.random() >= p_bg)
        sl = slice(i * PKT, (i + 1) * PKT)
        if bad:
            run += 1
            lost += 1
            fill = last * (0.5 ** run)
            xf = int(0.002 * SR)
            ramp = np.linspace(0, 1, xf, dtype=np.float32)
            prev_tail = y[i * PKT - xf:i * PKT] if i * PKT >= xf else None
            y[sl] = fill
            if prev_tail is not None:
                y[i * PKT:i * PKT + xf] = prev_tail[-1] * (1 - ramp) + fill[:xf] * ramp
        else:
            run = 0
            last = x[sl].copy()
    return y, lost / max(1, n)


def synth_rir(rt60: float = 0.45, seed: int = 7, length_s: float = 0.6) -> np.ndarray:
    """Synthetic small-room impulse response: direct path, 6 early reflections, exponentially decaying Gaussian tail."""
    rng = np.random.default_rng(seed)
    n = int(length_s * SR)
    h = np.zeros(n)
    h[0] = 1.0
    for d_ms, g in zip(rng.uniform(3, 28, 6), rng.uniform(0.15, 0.5, 6)):
        h[int(d_ms * SR / 1000)] += g * rng.choice([-1, 1])
    t = np.arange(n) / SR
    tail = rng.normal(0, 1, n) * np.exp(-6.9078 * t / rt60)          # -60 dB at rt60
    tail[: int(0.005 * SR)] = 0
    h += 0.12 * tail
    return h


def bandlimit(x: np.ndarray, lo: float = 150.0, hi: float = 4000.0, order: int = 8) -> np.ndarray:
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    H = 1 / np.sqrt(1 + (f / hi) ** (2 * order)) * (1 / np.sqrt(1 + (lo / np.maximum(f, 1e-6)) ** (2 * 4)))
    return np.fft.irfft(X * H, n=len(x))


def speaker_rerecord(x: np.ndarray, snr_db: float = 35.0, seed: int = 11) -> np.ndarray:
    y = np.fft.irfft(np.fft.rfft(x, len(x) + 9600) * np.fft.rfft(synth_rir(), len(x) + 9600), n=len(x) + 9600)[: len(x)]
    y = bandlimit(y)
    rng = np.random.default_rng(seed)
    p = float(np.mean(y ** 2)) + 1e-12
    noise = bandlimit(rng.normal(0, 1, len(y)), 60.0, 6000.0, 2)
    y = y + noise * np.sqrt(p / 10 ** (snr_db / 10) / (np.mean(noise ** 2) + 1e-12))
    peak_in, peak = float(np.max(np.abs(x)) + 1e-9), float(np.max(np.abs(y)) + 1e-9)
    return (y * (peak_in / peak)).astype(np.float32)


# --- conditions -------------------------------------------------------------------------------------------------------
def c_opus8k(x): return through_codec(x, ["-c:a", "libopus", "-b:a", "12k"], "ogg", 8000)
def c_amr_nb(x): return through_codec(x, ["-c:a", "libopencore_amrnb", "-b:a", "12.2k"], "amr", 8000)
def c_mulaw(x): return through_codec(x, ["-c:a", "pcm_mulaw"], "wav", 8000)
def c_alaw(x): return through_codec(x, ["-c:a", "pcm_alaw"], "wav", 8000)
def c_opus_loss(x): return packet_loss(through_codec(x, ["-c:a", "libopus", "-b:a", "6k"], "ogg", 8000))[0]
def c_rerecord(x): return speaker_rerecord(x)
def c_chain_pstn(x): return c_opus_loss(c_mulaw(x))
def c_chain_replay(x): return c_opus8k(c_rerecord(x))


CONDITIONS = {
    "opus8k": (c_opus8k, "libopus"),
    "amr_nb": (c_amr_nb, "libopencore_amrnb"),
    "g711_mulaw8k": (c_mulaw, "pcm_mulaw"),
    "g711_alaw8k": (c_alaw, "pcm_alaw"),
    "opus_lowbitrate_with_loss": (c_opus_loss, "libopus"),
    "speaker_rerecord_sim": (c_rerecord, None),
    "chain_pstn_voip": (c_chain_pstn, "libopus"),
    "chain_replay_call": (c_chain_replay, "libopus"),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", nargs="?", default="data/calls")
    ap.add_argument("--only", help="comma-separated condition names")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        print("\n".join(CONDITIONS))
        return 0
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found (brew install ffmpeg)", file=sys.stderr)
        return 2
    names = [n.strip() for n in a.only.split(",")] if a.only else list(CONDITIONS)
    bad = [n for n in names if n not in CONDITIONS]
    if bad:
        print(f"unknown condition(s): {bad}; known: {list(CONDITIONS)}", file=sys.stderr)
        return 2
    active = []
    for n in names:
        need = CONDITIONS[n][1]
        if need and not has_encoder(need):
            print(f"SKIP {n}: this ffmpeg has no '{need}' encoder (document-only condition here)")
            continue
        active.append(n)
    suffixes = tuple(f".{n}" for n in CONDITIONS) + (".opus8k",)
    root = Path(a.dir)
    inputs = [p for p in sorted(root.rglob("*.wav")) if not p.stem.endswith(suffixes)]
    counts = {n: 0 for n in active}
    for f in inputs:
        x = None
        for n in active:
            out = f.with_name(f"{f.stem}.{n}.wav")
            if out.exists() and not a.force:
                continue
            x = read_wav(f) if x is None else x
            write_wav(out, CONDITIONS[n][0](x))
            txt = f.with_suffix(".txt")
            if txt.exists():
                shutil.copyfile(txt, out.with_suffix(".txt"))
            counts[n] += 1
    print(f"{len(inputs)} source clip(s) in {root}; written: " + ", ".join(f"{n}={c}" for n, c in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
