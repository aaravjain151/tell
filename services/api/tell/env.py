"""One place that reads Tell's settings from the environment (D-013).

Every setting is named ``TELL_<X>``. The product used to be called Doublespeak, so ``DOUBLESPEAK_<X>`` is still
honoured as a fallback: ``TELL_<X>`` wins when both are set, an existing ``.env`` with the old names keeps working.
Imports only ``os`` (it is read by ``offline_guard`` at package import, before anything heavy).
"""
from __future__ import annotations

import os

PREFIX = "TELL_"
LEGACY_PREFIX = "DOUBLESPEAK_"


def legacy_name(name: str) -> str:
    """TELL_X -> DOUBLESPEAK_X (the deprecated spelling of the same setting)."""
    if not name.startswith(PREFIX):
        raise ValueError(f"Tell settings start with {PREFIX}: {name!r}")
    return LEGACY_PREFIX + name[len(PREFIX):]


def get(name: str, default: str | None = None) -> str | None:
    """Value of TELL_X, else of the legacy DOUBLESPEAK_X, else `default`. An empty TELL_X counts as set."""
    v = os.environ.get(name)
    if v is not None:
        return v
    v = os.environ.get(legacy_name(name))
    return default if v is None else v
