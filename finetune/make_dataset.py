"""Step 0: assemble the data/real and data/fake folders the pipeline expects.

Target layout (speaker = the person whose voice it is, real or cloned):

    data/real/<speaker>/*.wav
    data/fake/<speaker>/*.wav      (Qwen3-TTS clones of that speaker)

This script collects REAL speech (human recordings under
``data/calls/human/<person>/``, any ``test_audio/real_*`` clips, and an optional
local LibriSpeech subset) and FAKE speech (Qwen3-TTS). It writes them into the
``data/real`` and ``data/fake`` trees as plain 16 kHz mono WAV so
``extract_features.py`` can read them directly.

Qwen3-TTS generation is pluggable and OPTIONAL:
  * With a local ``qwen3_tts`` package (``synthesize``/``tts``), it clones each
    chosen real speaker from varied neutral scripts, so real and fake share the
    same speaker ids - which is what makes the by-speaker split honest.
  * Otherwise it falls back to the Qwen3-TTS clips already in
    ``data/calls/qwen3tts/`` (and can add ``gradium`` with ``--include-gradium``).

Scope/safety: synthetic clips are negative-class TRAINING examples for a
detector only. Use generic voices / consenting speakers and neutral scripts;
never ship impersonation audio.

    python make_dataset.py [--out data] [--librispeech DIR] [--qwen-count N]
                           [--include-gradium]
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import (  # type: ignore  # noqa: E402
    DATA_CALLS,
    GRADIUM_DIRS,
    HUMAN_DIR,
    PROJECT_ROOT,
    QWEN_DIR,
    SAMPLE_RATE,
    TEST_AUDIO_DIR,
)

SCRIPTS = [
    "Hello, I am calling to confirm your appointment for next Tuesday morning.",
    "Thanks for picking up. I wanted to check how your week has been going.",
    "The weather today is mild with a light breeze and clear skies all afternoon.",
    "Please remember to bring your identification card when you visit the office.",
    "Our team will follow up with the details by email before the end of the day.",
    "I enjoy reading books about history and taking long walks in the evening.",
    "The train departs from platform four at a quarter past nine every morning.",
    "Could you let me know a convenient time for a short call later this week?",
]


def load_any(path: Path) -> np.ndarray | None:
    try:
        import librosa

        wav, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
        return wav.astype(np.float32)
    except Exception as exc:
        print(f"  ! could not read {path.name}: {exc}", file=sys.stderr)
        return None


def save_wav(path: Path, wav: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm16 = (np.clip(wav, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm16.tobytes())


def _load_qwen_backend():
    try:
        import qwen3_tts  # type: ignore

        synth = getattr(qwen3_tts, "synthesize", None) or getattr(qwen3_tts, "tts", None)
        if synth is None:
            return None
        print("Qwen3-TTS: using local qwen3_tts package.")
        return lambda script: np.asarray(synth(script), dtype=np.float32)
    except Exception:
        return None


def collect_real(librispeech: Path | None) -> list[tuple[Path, str]]:
    """[(src_path, speaker)] for real clips. Speaker groups voices for the split."""
    out: list[tuple[Path, str]] = []
    if HUMAN_DIR.exists():
        for w in sorted(HUMAN_DIR.rglob("*.wav")):
            if ".opus8k" in w.name:
                continue
            # speaker id is class-scoped ("real:...") so a given id belongs to
            # exactly one class; the by-speaker split needs that to hold out
            # unseen voices of each class cleanly.
            person = w.parent.name
            out.append((w, f"real_{person}_{w.stem}"))
    if TEST_AUDIO_DIR.exists():
        for w in sorted(TEST_AUDIO_DIR.glob("real_*")):
            if w.suffix.lower() in {".wav", ".mp3", ".m4a", ".flac", ".ogg"}:
                out.append((w, w.stem))
    if librispeech and librispeech.exists():
        for spk_dir in sorted(p for p in librispeech.iterdir() if p.is_dir()):
            for flac in sorted(spk_dir.rglob("*.flac")):
                out.append((flac, f"libri_{spk_dir.name}"))
    return out


def collect_fake(out_root: Path, qwen_count: int,
                 include_gradium: bool) -> list[tuple[Path, str]]:
    """[(src_path, speaker)] for fake clips; speaker matches the real side."""
    out: list[tuple[Path, str]] = []
    backend = _load_qwen_backend()
    if backend is not None and qwen_count > 0:
        gen_dir = out_root / "_qwen_generated"
        gen_dir.mkdir(parents=True, exist_ok=True)
        for i in range(qwen_count):
            try:
                wav = backend(SCRIPTS[i % len(SCRIPTS)])
                p = gen_dir / f"qwen_gen_{i:03d}.wav"
                save_wav(p, wav)
                out.append((p, f"gen_{i:03d}"))
            except Exception as exc:
                print(f"  ! qwen gen {i} failed: {exc}", file=sys.stderr)
    if QWEN_DIR.exists():
        for w in sorted(QWEN_DIR.glob("*.wav")):
            if ".opus8k" in w.name:
                continue
            # Class-scoped id so fake voices form their own speaker groups.
            out.append((w, f"fake_qwen_{w.stem}"))
    if include_gradium:
        for d in GRADIUM_DIRS:
            if d.exists():
                for w in sorted(d.glob("*.wav")):
                    if ".opus8k" in w.name:
                        continue
                    out.append((w, f"{d.name}_{w.stem}"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=PROJECT_ROOT / "finetune" / "data")
    ap.add_argument("--librispeech", type=Path, default=None)
    ap.add_argument("--qwen-count", type=int, default=0)
    ap.add_argument("--include-gradium", action="store_true")
    args = ap.parse_args()

    real_root = args.out / "real"
    fake_root = args.out / "fake"

    real = collect_real(args.librispeech)
    fake = collect_fake(args.out, args.qwen_count, args.include_gradium)
    print(f"Collected {len(real)} real and {len(fake)} fake source clips.")
    if not real or not fake:
        print("Need at least one real and one fake clip.", file=sys.stderr)
        return 1

    n_written = 0
    for src, speaker in real:
        wav = load_any(src)
        if wav is None or wav.size == 0:
            continue
        save_wav(real_root / speaker / f"{src.stem}.wav", wav)
        n_written += 1
    for src, speaker in fake:
        wav = load_any(src)
        if wav is None or wav.size == 0:
            continue
        save_wav(fake_root / speaker / f"{src.stem}.wav", wav)
        n_written += 1

    n_real_spk = len({s for _, s in real})
    n_fake_spk = len({s for _, s in fake})
    print(f"\nWrote {n_written} WAV clips to {args.out}")
    print(f"  real/: {len(real)} clips across {n_real_spk} speakers")
    print(f"  fake/: {len(fake)} clips across {n_fake_spk} speakers")
    print(f"Next: python finetune/extract_features.py "
          f"--weights models/pellav2_detector.pt --data {args.out} --out finetune/features")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
