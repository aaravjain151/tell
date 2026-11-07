"""Run the full DoubleSpeak pipeline on every clip in ``test_audio/``.

Prints an aligned table of voice score, scam score, fused risk and level per
file so you can check how well real-vs-cloned and scam-vs-normal separate.

    python run_pipeline_tests.py [folder]

Default folder is ``test_audio/``. Drop labelled clips in there, e.g.
``real_normal_01.wav``, ``cloned_scam_giftcard.wav`` - the filename is printed
as-is so you can eyeball the scores against what you expect.

Models must be present locally (run ``download_models.py`` first). Ollama should
be running for the scam column; if it is not, the regex safety net is used and
the scam score still reflects obvious scam language.
"""

from __future__ import annotations

import sys
from pathlib import Path

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}


def _find_clips(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXTS)


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("test_audio")
    clips = _find_clips(folder)
    if not clips:
        print(f"No audio files found in {folder.resolve()}.")
        print("Add .wav/.mp3/.m4a/.flac/.ogg clips and run again.")
        return 1

    # Import here so the no-clips message is instant and does not load models.
    from doublespeak.detector import get_pipeline

    pipeline = get_pipeline()

    name_w = max(len("file"), *(len(c.name) for c in clips))
    header = f"{'file':<{name_w}}  {'voice':>6}  {'scam':>5}  {'risk':>5}  level"
    print(header)
    print("-" * len(header))

    for clip in clips:
        try:
            r = pipeline.run_file(str(clip))
            print(
                f"{clip.name:<{name_w}}  "
                f"{r.voice_score:>6.2f}  {r.scam_score:>5.2f}  "
                f"{r.risk:>5.2f}  {r.level}"
            )
        except Exception as exc:  # keep going across the whole folder
            print(f"{clip.name:<{name_w}}  ERROR: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
