"""Part A.3 - extract features (--opus) then train the voice head (offline).

Thin runner that reuses the proven finetune/ scripts rather than duplicating
them: it calls finetune/extract_features.py --opus on the data pulled by
pull_real_audio.py + make_fakes.py, then finetune/train_head.py, and saves
models/pellav2_qwen.pt. The before/after table is printed by train_head.

    python training/pellav2-finetune/run_training.py

Prereqs: run pull_real_audio.py and make_fakes.py first so
training/pellav2-finetune/data/{real,fake}/<speaker>/ is populated. Fully
offline (models are already local).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (  # type: ignore  # noqa: E402
    BASE_WEIGHTS,
    PROJECT_ROOT,
    VOICE_DATA,
    VOICE_FEATURES,
    VOICE_OUT,
    VOICE_REAL,
    VOICE_FAKE,
)

PY = sys.executable
FINETUNE = PROJECT_ROOT / "finetune"


def _have_data() -> bool:
    return (VOICE_REAL.exists() and any(VOICE_REAL.rglob("*.wav"))
            and VOICE_FAKE.exists() and any(VOICE_FAKE.rglob("*.wav")))


def main() -> int:
    if not _have_data():
        print("Missing training data. Run pull_real_audio.py then make_fakes.py.",
              file=sys.stderr)
        return 1

    extract = [
        PY, str(FINETUNE / "extract_features.py"),
        "--weights", str(BASE_WEIGHTS),
        "--data", str(VOICE_DATA),
        "--out", str(VOICE_FEATURES),
        "--opus",
    ]
    print("Step 1/2: extract features (--opus)\n  " + " ".join(extract))
    if subprocess.run(extract).returncode != 0:
        print("Feature extraction failed.", file=sys.stderr)
        return 1

    train = [
        PY, str(FINETUNE / "train_head.py"),
        "--weights", str(BASE_WEIGHTS),
        "--features", str(VOICE_FEATURES),
        "--out", str(VOICE_OUT),
    ]
    print("\nStep 2/2: train the head\n  " + " ".join(train))
    if subprocess.run(train).returncode != 0:
        print("Training failed.", file=sys.stderr)
        return 1

    print(f"\nDone. Voice model saved to {VOICE_OUT}")
    print("Part C (engine.py) can now load it for the voice verdict.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
