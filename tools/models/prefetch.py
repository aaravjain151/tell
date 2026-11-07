#!/usr/bin/env python3
"""Download every local model once, while online, so the demo can run with DOUBLESPEAK_OFFLINE=1 (Wi-Fi off).

    make models            # or: ./.venv/bin/python tools/models/prefetch.py

Lives in tools/ on purpose: this is the only place that downloads model weights; the analysis package never does.
Models come from the same env names the API reads (.env.local, then .env, via python-dotenv).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env.local")
    load_dotenv(ROOT / ".env")


def main() -> int:
    load_env()
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    done, failed = [], []

    def step(name, fn):
        try:
            print(f"-> {name} ...", flush=True)
            fn()
            done.append(name)
        except Exception as e:  # noqa: BLE001
            failed.append((name, f"{type(e).__name__}: {e}"))

    hf = os.environ.get("HF_SPOOF_MODEL", "")
    if hf:
        from huggingface_hub import snapshot_download
        step(f"anti-spoof {hf}", lambda: snapshot_download(hf))
    size = os.environ.get("DOUBLESPEAK_WHISPER_MODEL", "base.en")
    from faster_whisper.utils import download_model
    step(f"faster-whisper {size}", lambda: download_model(size))
    for extra in sorted(Path(__file__).parent.glob("prefetch_*.py")):      # optional per-voter prefetchers
        ns: dict = {"__file__": str(extra)}
        step(extra.stem.replace("prefetch_", ""), lambda extra=extra, ns=ns: (exec(compile(extra.read_text(), str(extra), "exec"), ns), ns["main"]()))
    print("\ncached:", *done, sep="\n  ")
    if failed:
        print("\nFAILED:", *[f"{n}: {e}" for n, e in failed], sep="\n  ", file=sys.stderr)
        return 1
    print("\nNow set DOUBLESPEAK_OFFLINE=1 in .env and the app will refuse to touch the network for models.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
