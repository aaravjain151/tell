"""Part A.1 - pull REAL speech for the voice model (online, run once).

Downloads LibriSpeech (openslr/librispeech_asr, "clean" config) from Hugging
Face, picks 40 speakers x 15 clips each (4-12 s), and writes them as 16 kHz mono
WAV to training/pellav2-finetune/data/real/<speaker_id>/. Also copies the team's
consented recordings from data/team_real/<name>/ into the same real tree.

This is a DOWNLOAD step: it needs the network and the `datasets` package
(``pip install datasets``). Everything after this is offline.

    python training/pellav2-finetune/pull_real_audio.py
        [--speakers 40] [--per-speaker 15] [--min-sec 4] [--max-sec 12]
        [--split train.clean.100]

Licence: LibriSpeech is CC BY 4.0 over public-domain LibriVox audio. Team
recordings are contributed with consent. See DATA_SOURCES.md.
"""

from __future__ import annotations

import argparse
import sys
import wave
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import SAMPLE_RATE, TEAM_REAL, VOICE_REAL, ensure_dirs  # type: ignore  # noqa: E402

HF_DATASET = "openslr/librispeech_asr"
HF_CONFIG = "clean"


def _resample_mono(wav: np.ndarray, sr: int) -> np.ndarray:
    import librosa

    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr != SAMPLE_RATE:
        wav = librosa.resample(wav.astype(np.float32), orig_sr=sr,
                               target_sr=SAMPLE_RATE)
    return wav.astype(np.float32)


def save_wav(path: Path, wav: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm16 = (np.clip(wav, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm16.tobytes())


def copy_team_recordings() -> int:
    """Copy consented team recordings into the real tree. Returns clip count."""
    import librosa

    if not TEAM_REAL.exists():
        return 0
    n = 0
    for person_dir in sorted(p for p in TEAM_REAL.iterdir() if p.is_dir()):
        spk = f"team_{person_dir.name}"
        for i, src in enumerate(sorted(person_dir.rglob("*"))):
            if src.suffix.lower() not in {".wav", ".flac", ".mp3", ".m4a", ".ogg"}:
                continue
            try:
                wav, sr = librosa.load(str(src), sr=None, mono=True)
            except Exception as exc:
                print(f"  ! team clip {src.name}: {exc}", file=sys.stderr)
                continue
            save_wav(VOICE_REAL / spk / f"{i:03d}.wav", _resample_mono(wav, sr))
            n += 1
    if n:
        print(f"Copied {n} consented team clips into {VOICE_REAL}")
    return n


def pull_librispeech(n_speakers: int, per_speaker: int,
                     min_sec: float, max_sec: float, split: str) -> int:
    try:
        from datasets import load_dataset
    except ImportError:
        print("The 'datasets' package is required for this download step.\n"
              "Install it once (online):  pip install datasets soundfile",
              file=sys.stderr)
        raise SystemExit(2)

    print(f"Streaming {HF_DATASET} [{HF_CONFIG}] split={split} from Hugging Face...")
    # Stream so we don't pull the whole corpus; stop once quotas are filled.
    ds = load_dataset(HF_DATASET, HF_CONFIG, split=split, streaming=True)

    kept: dict[str, int] = defaultdict(int)
    written = 0
    for ex in ds:
        if len(kept) >= n_speakers and all(
            kept[s] >= per_speaker for s in kept
        ):
            break
        spk = str(ex.get("speaker_id", ex.get("speaker", "unknown")))
        if spk not in kept and len(kept) >= n_speakers:
            continue  # speaker quota full
        if kept[spk] >= per_speaker:
            continue  # this speaker's clip quota full
        audio = ex["audio"]
        wav = np.asarray(audio["array"], dtype=np.float32)
        sr = int(audio["sampling_rate"])
        dur = len(wav) / sr
        if not (min_sec <= dur <= max_sec):
            continue
        wav = _resample_mono(wav, sr)
        save_wav(VOICE_REAL / f"libri_{spk}" / f"{kept[spk]:03d}.wav", wav)
        kept[spk] += 1
        written += 1
        if written % 50 == 0:
            print(f"  {written} clips / {len(kept)} speakers so far")

    print(f"LibriSpeech: wrote {written} clips across {len(kept)} speakers.")
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--speakers", type=int, default=40)
    ap.add_argument("--per-speaker", type=int, default=15)
    ap.add_argument("--min-sec", type=float, default=4.0)
    ap.add_argument("--max-sec", type=float, default=12.0)
    ap.add_argument("--split", default="train.clean.100")
    args = ap.parse_args()

    ensure_dirs()
    n_team = copy_team_recordings()
    n_libri = pull_librispeech(args.speakers, args.per_speaker,
                               args.min_sec, args.max_sec, args.split)
    total = n_team + n_libri
    if total == 0:
        print("No real clips collected.", file=sys.stderr)
        return 1
    print(f"\nReal audio ready in {VOICE_REAL} "
          f"({n_libri} LibriSpeech + {n_team} team clips).")
    print("Next: python training/pellav2-finetune/make_fakes.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
