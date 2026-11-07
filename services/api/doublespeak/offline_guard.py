"""Force the ML libraries offline once the models are cached (idea ported from teammate branch sam_dev1).

`DOUBLESPEAK_OFFLINE=1` makes Hugging Face / Transformers refuse to touch the network, so a voter can never
silently download weights, check for updates or send telemetry during a call. It must run before `transformers`
or `huggingface_hub` is imported, so `doublespeak/__init__.py` applies it at package import.

Run `make models` once (online) to fill the caches, then set DOUBLESPEAK_OFFLINE=1 for the demo. A model that is not
cached then degrades its voter to applicable=False instead of failing the request.
"""
from __future__ import annotations

import os

_OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "DO_NOT_TRACK": "1",
    "TOKENIZERS_PARALLELISM": "false",
}


def enforce() -> None:
    """Set the offline variables unconditionally (existing values are overwritten, so a loose shell cannot re-enable the network)."""
    os.environ.update(_OFFLINE_ENV)


def apply_from_env() -> bool:
    """Enforce when DOUBLESPEAK_OFFLINE=1. Returns whether it was applied."""
    if os.environ.get("DOUBLESPEAK_OFFLINE", "") == "1":
        enforce()
        return True
    return False


def is_enforced() -> bool:
    return os.environ.get("HF_HUB_OFFLINE") == "1" and os.environ.get("TRANSFORMERS_OFFLINE") == "1"
