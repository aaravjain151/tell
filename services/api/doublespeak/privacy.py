"""The privacy guarantee, made executable.

- `record_egress(kind, nbytes)` is the ONLY sanctioned way to note an outbound request. Anything
  that tries to send caller audio raises; the meter the UI shows comes from `report()`.
- `sign(payload)` produces an HMAC receipt bound to the clip's hash, so a verdict can be verified
  later without the audio ever being stored.
- `tests/test_privacy.py` additionally scans the signals/scorer modules for network imports.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading

_lock = threading.Lock()
_state = {"external_requests": 0, "bytes_sent_external": 0, "caller_audio_bytes_sent": 0}


class AudioEgressError(RuntimeError):
    pass


def record_egress(kind: str, nbytes: int) -> None:
    """kind ∈ {"text", "verdict_tts"}; "audio" is forbidden by construction."""
    if kind == "audio":
        raise AudioEgressError("caller audio must never leave the device")
    with _lock:
        _state["external_requests"] += 1
        _state["bytes_sent_external"] += int(nbytes)


def report() -> dict:
    with _lock:
        return dict(_state)


def reset() -> None:
    with _lock:
        for k in _state:
            _state[k] = 0


def audio_fingerprint(data: bytes | None) -> str:
    return hashlib.sha256(data).hexdigest()[:16] if data else "no-audio"


def sign(payload: dict, audio_fp: str) -> str:
    key = os.environ.get("DOUBLESPEAK_SIGNING_KEY", "change-me-local").encode()
    canon = json.dumps({**payload, "audio_fp": audio_fp}, sort_keys=True, separators=(",", ":")).encode()
    return "ds1:" + audio_fp + ":" + hmac.new(key, canon, hashlib.sha256).hexdigest()[:32]


def verify(payload: dict, signature: str) -> bool:
    try:
        _, fp, _ = signature.split(":")
    except ValueError:
        return False
    return hmac.compare_digest(sign(payload, fp), signature)
