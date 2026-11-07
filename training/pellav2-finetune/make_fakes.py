"""Part A.2 - generate the FAKE class with Qwen3-TTS (online, run once).

For every speaker collected under data/real/<speaker_id>/, use ONE real clip as
a ~3-second voice reference and synthesise 15 clips with varied text (half
everyday sentences, half lines from data/scam_scripts.txt). Clones are written
to data/fake/<same_speaker_id>/ so the detector trains on matched real/fake
pairs per voice.

Model selection (per the official QwenLM/Qwen3-TTS README):
  * default: Qwen3-TTS-12Hz-1.7B-Base
  * if GPU memory < 8 GB (or no GPU): the 0.6B variant

    python training/pellav2-finetune/make_fakes.py [--per-speaker 15]
        [--ref-seconds 3] [--model auto|1.7b|0.6b]

Install Qwen3-TTS once, online, from the official repo and follow its README:
    git clone https://github.com/QwenLM/Qwen3-TTS && pip install -e Qwen3-TTS
This script imports whatever TTS entry point that install exposes; if none is
found it explains what to install and exits without writing anything.

SCOPE / SAFETY (hard limit): the synthetic clips produced here are NEGATIVE-
CLASS TRAINING EXAMPLES for the deepfake *detector* only. The reference voices
must be public-domain (LibriSpeech) or consented team members (see
DATA_SOURCES.md). This tool must not be used to impersonate a person to a
listener; it writes training data to disk and nothing else.
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (  # type: ignore  # noqa: E402
    SAMPLE_RATE,
    SCAM_SCRIPTS,
    VOICE_FAKE,
    VOICE_REAL,
    ensure_dirs,
)

EVERYDAY = [
    "Hello, I wanted to check in and see how your day has been going so far.",
    "The library is open until six in the evening on weekdays this month.",
    "We are planning to meet for lunch near the park if the weather stays nice.",
    "Could you please remind me what time the appointment is scheduled for.",
    "I finished reading that book you recommended and really enjoyed the ending.",
    "The bus was a little late today but I still made it to work on time.",
    "Let us catch up over coffee sometime next week when you are free.",
    "Thank you for your help earlier, it made a real difference to my afternoon.",
]


def _load_scam_lines() -> list[str]:
    if not SCAM_SCRIPTS.exists():
        return []
    out = []
    for ln in SCAM_SCRIPTS.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            out.append(ln)
    return out


def _scripts_for(per_speaker: int) -> list[str]:
    """Half everyday, half scam lines, cycled to length."""
    scam = _load_scam_lines() or EVERYDAY
    half = per_speaker // 2
    pick = []
    for i in range(half):
        pick.append(EVERYDAY[i % len(EVERYDAY)])
    for i in range(per_speaker - half):
        pick.append(scam[i % len(scam)])
    return pick


def save_wav(path: Path, wav: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm16 = (np.clip(wav, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm16.tobytes())


def _pick_model(choice: str) -> str:
    """Resolve 'auto' to the 1.7B or 0.6B model by available GPU memory."""
    name_17 = "Qwen3-TTS-12Hz-1.7B-Base"
    name_06 = "Qwen3-TTS-12Hz-0.6B-Base"
    if choice == "1.7b":
        return name_17
    if choice == "0.6b":
        return name_06
    try:
        import torch

        if torch.cuda.is_available():
            gb = torch.cuda.get_device_properties(0).total_memory / 1e9
            return name_17 if gb >= 8 else name_06
    except Exception:
        pass
    return name_06  # no GPU -> smaller model


def _load_tts(model_name: str):
    """Load the Qwen3-TTS clone function from whatever the install exposes.

    Returns a callable ``clone(reference_wav_path, text) -> (np.ndarray, sr)``
    or None if Qwen3-TTS is not installed. We probe a few likely entry points
    so this keeps working across the repo's API without pinning one private
    signature.
    """
    try:
        import qwen3_tts  # type: ignore
    except Exception:
        return None

    # Preferred: a high-level pipeline/model object with a clone/generate method.
    for factory in ("load_model", "Qwen3TTS", "TTS", "pipeline"):
        obj = getattr(qwen3_tts, factory, None)
        if obj is None:
            continue
        try:
            model = obj(model_name) if callable(obj) else obj
        except Exception:
            continue
        for meth in ("clone", "generate", "synthesize", "tts"):
            fn = getattr(model, meth, None)
            if callable(fn):
                def clone(ref: str, text: str, _fn=fn):
                    out = _fn(text=text, reference=ref)
                    if isinstance(out, tuple):
                        wav, sr = out
                    else:
                        wav, sr = out, SAMPLE_RATE
                    return np.asarray(wav, dtype=np.float32), int(sr)
                return clone
    return None


def _first_ref_clip(speaker_dir: Path, ref_seconds: float) -> Path | None:
    for w in sorted(speaker_dir.glob("*.wav")):
        return w  # first clip; preprocessing trims to ref_seconds downstream
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--per-speaker", type=int, default=15)
    ap.add_argument("--ref-seconds", type=float, default=3.0)
    ap.add_argument("--model", choices=["auto", "1.7b", "0.6b"], default="auto")
    args = ap.parse_args()

    ensure_dirs()
    if not VOICE_REAL.exists() or not any(VOICE_REAL.iterdir()):
        print("No real speakers found. Run pull_real_audio.py first.",
              file=sys.stderr)
        return 1

    model_name = _pick_model(args.model)
    print(f"Qwen3-TTS model: {model_name}")
    clone = _load_tts(model_name)
    if clone is None:
        print(
            "Qwen3-TTS is not installed. Install it once (online) from the\n"
            "official repo and follow its README, then re-run:\n"
            "    git clone https://github.com/QwenLM/Qwen3-TTS\n"
            "    pip install -e Qwen3-TTS\n"
            "No fakes were written.", file=sys.stderr,
        )
        return 2

    import librosa

    scripts = _scripts_for(args.per_speaker)
    speakers = [d for d in sorted(VOICE_REAL.iterdir()) if d.is_dir()]
    total = 0
    for spk_dir in speakers:
        ref = _first_ref_clip(spk_dir, args.ref_seconds)
        if ref is None:
            continue
        for i, text in enumerate(scripts):
            try:
                wav, sr = clone(str(ref), text)
                if sr != SAMPLE_RATE:
                    wav = librosa.resample(wav, orig_sr=sr, target_sr=SAMPLE_RATE)
                save_wav(VOICE_FAKE / spk_dir.name / f"{i:03d}.wav", wav)
                total += 1
            except Exception as exc:
                print(f"  ! clone {spk_dir.name}/{i}: {exc}", file=sys.stderr)
        print(f"  {spk_dir.name}: {len(scripts)} clones")

    if total == 0:
        print("No fakes generated.", file=sys.stderr)
        return 1
    print(f"\nWrote {total} fake clips across {len(speakers)} speakers to "
          f"{VOICE_FAKE}")
    print("Next: python finetune/extract_features.py "
          f"--weights models/pellav2_detector.pt --data {VOICE_FAKE.parent} "
          "--out training/pellav2-finetune/features --opus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
