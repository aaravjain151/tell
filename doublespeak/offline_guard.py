"""Enforce fully-offline operation for all ML libraries.

This module must be imported *before* ``transformers``, ``huggingface_hub``,
``torch`` or ``faster_whisper`` so the offline environment variables are set in
time. It is imported first by :mod:`doublespeak.config`.

Hard rule for this product: nothing may reach the network at runtime. The one
and only permitted connection is to a local Ollama server on ``localhost:11434``
(handled in :mod:`doublespeak.scam_analyzer`).
"""

from __future__ import annotations

import os

#: Environment variables that force Hugging Face / Transformers to never touch
#: the network. Set unconditionally so a fresh process is always offline.
_OFFLINE_ENV: dict[str, str] = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    # Belt-and-braces: disable telemetry, update checks and implicit tokens.
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
    "DISABLE_TELEMETRY": "1",
    "DO_NOT_TRACK": "1",
    "TOKENIZERS_PARALLELISM": "false",
}


def enforce_offline() -> None:
    """Set the offline environment variables in-process.

    Idempotent: safe to call many times. Existing values are overwritten so a
    misconfigured shell cannot accidentally re-enable network access.
    """
    for key, value in _OFFLINE_ENV.items():
        os.environ[key] = value


# Apply immediately on import so merely importing this module makes the process
# offline, regardless of import order elsewhere.
enforce_offline()
