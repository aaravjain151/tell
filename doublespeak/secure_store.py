"""Encrypted, local-only alert history.

Alerts are the only thing Tell persists, and each record holds only a
timestamp, a risk level, and plain-language reasons - never audio and never the
transcript.

Security:

* AES-256-GCM via the ``cryptography`` library.
* A fresh random 96-bit (12-byte) nonce per record.
* The 256-bit key is generated once and kept in the OS keychain via ``keyring``.
  It is never written to disk alongside the ciphertext.

File format (``alert_history.enc``): one record per line,
``base64(nonce):base64(ciphertext_with_tag)``. Append-only.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import keyring
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import config

_KEY_BYTES = 32  # AES-256
_NONCE_BYTES = 12  # 96-bit GCM nonce


@dataclass
class AlertRecord:
    """A stored alert. Deliberately contains no audio or transcript."""

    timestamp: str  # ISO-8601 UTC
    level: str  # "High" | "Medium" | "Low"
    reasons: list[str] = field(default_factory=list)


def _get_or_create_key() -> bytes:
    """Return the AES-256 key from the OS keychain, creating it on first use."""
    stored = keyring.get_password(config.KEYRING_SERVICE, config.KEYRING_USERNAME)
    if stored:
        key = base64.b64decode(stored)
        if len(key) == _KEY_BYTES:
            return key
    key = AESGCM.generate_key(bit_length=256)
    keyring.set_password(
        config.KEYRING_SERVICE,
        config.KEYRING_USERNAME,
        base64.b64encode(key).decode("ascii"),
    )
    return key


def _encrypt(key: bytes, plaintext: bytes) -> str:
    """Encrypt one record into a ``nonce:ciphertext`` base64 line."""
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return (
        base64.b64encode(nonce).decode("ascii")
        + ":"
        + base64.b64encode(ciphertext).decode("ascii")
    )


def _decrypt(key: bytes, line: str) -> bytes:
    """Decrypt one ``nonce:ciphertext`` base64 line back to plaintext bytes."""
    nonce_b64, ct_b64 = line.strip().split(":", 1)
    return AESGCM(key).decrypt(
        base64.b64decode(nonce_b64), base64.b64decode(ct_b64), None
    )


def save_alert(level: str, reasons: list[str]) -> AlertRecord:
    """Encrypt and append one alert (timestamp/level/reasons only)."""
    config.ensure_dirs()
    record = AlertRecord(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        level=level,
        reasons=list(reasons),
    )
    key = _get_or_create_key()
    line = _encrypt(key, json.dumps(asdict(record)).encode("utf-8"))
    with open(config.HISTORY_FILE, "a", encoding="ascii") as fh:
        fh.write(line + "\n")
    return record


def load_alerts() -> list[AlertRecord]:
    """Decrypt and return all stored alerts, newest first.

    Records that fail to decrypt (tampered or wrong key) are skipped.
    """
    if not config.HISTORY_FILE.exists():
        return []
    key = _get_or_create_key()
    out: list[AlertRecord] = []
    for line in config.HISTORY_FILE.read_text(encoding="ascii").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(_decrypt(key, line))
            out.append(AlertRecord(**data))
        except Exception:
            continue
    out.sort(key=lambda a: a.timestamp, reverse=True)
    return out


def wipe_all() -> None:
    """Delete the encrypted history file. The keychain key is left intact."""
    if config.HISTORY_FILE.exists():
        config.HISTORY_FILE.unlink()
