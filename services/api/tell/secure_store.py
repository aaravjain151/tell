"""Opt-in, encrypted, local-only alert history (T-016).

Off unless TELL_HISTORY=1. Each record is one JSON object, encrypted with AES-256-GCM
(fresh 96-bit nonce) and stored as one base64 line: ``b64(nonce):b64(ciphertext+tag)``. Append-only.

The 256-bit key lives in the OS keychain (``keyring``, service "tell") and is NEVER written
to disk. A key stored by an older checkout under the legacy service "doublespeak" is read and copied to "tell" on
first use (the legacy item is left in place), so existing encrypted files stay readable after the rename (D-013).
There is deliberately no file fallback. If ``cryptography``/``keyring`` is missing or the
keychain is unavailable or locked, history is simply off and callers get a status string.

A record holds ONLY: timestamp, tier, p_ai, p_scam, thresholds_version and the names of the top 3
tells that fired. Never audio, never transcript, never evidence strings (they quote the caller).
``record_from_verdict`` builds it from an allowlist, so nothing else can slip in.
No network code lives here.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import env as _env

log = logging.getLogger("tell.secure_store")

KEYRING_SERVICE = "tell"
LEGACY_KEYRING_SERVICE = "doublespeak"   # pre-D-013 name: read-only fallback so existing encrypted data stays readable
KEYRING_USER = "history-key"
HISTORY_FILE = "alert_history.enc"
READ_CAP = 200
_KEY_BYTES = 32
_NONCE_BYTES = 12

KeyProvider = Callable[[], bytes]


class HistoryUnavailable(Exception):
    """History cannot run (missing dependency, keychain unavailable/locked)."""


def enabled() -> bool:
    return _env.get("TELL_HISTORY") == "1"


def data_dir() -> Path:
    env = _env.get("TELL_DATA_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[3] / "data" / "history"


def history_path() -> Path:
    return data_dir() / HISTORY_FILE


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise HistoryUnavailable("cryptography not installed") from e
    return AESGCM


def _stored_key(keyring, service: str) -> bytes | None:
    stored = keyring.get_password(service, KEYRING_USER)
    if stored:
        key = base64.b64decode(stored)
        if len(key) == _KEY_BYTES:
            return key
    return None


def keyring_key_provider() -> bytes:
    """Fetch (or create on first use) the AES key in the OS keychain. Raises HistoryUnavailable.

    Order: service "tell"; else the legacy "doublespeak" key, copied to "tell" (never a fresh key while an old one
    exists, or every existing encrypted file would become unreadable); else a new key under "tell"."""
    AESGCM = _aesgcm()
    try:
        import keyring
    except ImportError as e:
        raise HistoryUnavailable("keyring not installed") from e
    try:
        key = _stored_key(keyring, KEYRING_SERVICE)
        if key:
            return key
        key = _stored_key(keyring, LEGACY_KEYRING_SERVICE)
        if key:
            try:
                keyring.set_password(KEYRING_SERVICE, KEYRING_USER, base64.b64encode(key).decode("ascii"))
            except Exception as e:  # noqa: BLE001 — the copy is best effort; the legacy key still works next time
                log.warning("could not copy the history key to the new keychain name: %s", type(e).__name__)
            return key
        key = AESGCM.generate_key(bit_length=256)
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, base64.b64encode(key).decode("ascii"))
        return key
    except Exception as e:  # noqa: BLE001 — locked/missing backend, etc.
        raise HistoryUnavailable(f"keychain unavailable ({type(e).__name__})") from e


def record_from_verdict(v) -> dict:
    """The ONLY way a record is built: an allowlist of numeric/enum/name fields from the verdict."""
    fired = [t for t in v.tells if t.applicable and t.score >= 0.5]
    fired.sort(key=lambda t: t.score * t.weight, reverse=True)
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tier": str(v.tier),
        "p_ai": round(float(v.p_ai), 2),
        "p_scam": round(float(v.p_scam), 2),
        "thresholds_version": str(v.thresholds_version),
        "tells": [str(t.name) for t in fired[:3]],
    }


def _encrypt(key: bytes, plaintext: bytes) -> str:
    nonce = os.urandom(_NONCE_BYTES)
    ct = _aesgcm()(key).encrypt(nonce, plaintext, None)
    return base64.b64encode(nonce).decode("ascii") + ":" + base64.b64encode(ct).decode("ascii")


def _decrypt(key: bytes, line: str) -> bytes:
    n, c = line.strip().split(":", 1)
    return _aesgcm()(key).decrypt(base64.b64decode(n), base64.b64decode(c), None)


def _ensure_dir() -> Path:
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def append(record: dict, key_provider: KeyProvider | None = None) -> None:
    """Encrypt and append one record. Raises HistoryUnavailable or OSError."""
    key = (key_provider or keyring_key_provider)()
    line = _encrypt(key, json.dumps(record, sort_keys=True).encode("utf-8"))
    _ensure_dir()
    fd = os.open(history_path(), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, (line + "\n").encode("ascii"))
    finally:
        os.close(fd)


def record_verdict(v, key_provider: KeyProvider | None = None) -> str:
    """Pipeline hook: append a record only when enabled. Never raises. Returns a status string."""
    if not enabled():
        return "disabled"
    try:
        append(record_from_verdict(v), key_provider)
        return "ok"
    except HistoryUnavailable as e:
        return f"unavailable: {e}"
    except Exception as e:  # noqa: BLE001 — history must never fail an analysis
        log.warning("history write failed: %s", type(e).__name__)
        return f"unavailable: write failed ({type(e).__name__})"


def _lines() -> list[str]:
    p = history_path()
    if not p.exists():
        return []
    return [ln for ln in p.read_text(encoding="ascii", errors="replace").splitlines() if ln.strip()]


def read_all(key_provider: KeyProvider | None = None, limit: int = READ_CAP) -> tuple[list[dict], int]:
    """Return (records newest first, capped at `limit`; number of skipped corrupt/tampered lines)."""
    lines = _lines()
    if not lines:
        return [], 0
    key = (key_provider or keyring_key_provider)()
    out: list[dict] = []
    skipped = 0
    for line in lines:
        try:
            out.append(json.loads(_decrypt(key, line)))
        except HistoryUnavailable:
            raise
        except Exception:  # noqa: BLE001 — GCM auth failure, bad base64, bad JSON
            skipped += 1
    out.reverse()
    return out[:limit], skipped


def count() -> int:
    return len(_lines())


def wipe() -> int:
    """Delete the history file; returns how many records it held. The keychain key is left alone."""
    n = count()
    try:
        history_path().unlink()
    except FileNotFoundError:
        pass
    return n


def status(key_provider: KeyProvider | None = None) -> dict:
    """{enabled, available, reason, count}. Touches the keychain only when history is enabled."""
    on = enabled()
    available, reason = True, ""
    try:
        _aesgcm()
        if key_provider is None:
            try:
                import keyring  # noqa: F401
            except ImportError as e:
                raise HistoryUnavailable("keyring not installed") from e
        if on:
            (key_provider or keyring_key_provider)()
    except HistoryUnavailable as e:
        available, reason = False, str(e)
    return {"enabled": on, "available": available, "reason": reason, "count": count()}
