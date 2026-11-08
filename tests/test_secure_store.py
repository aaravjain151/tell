"""Tests for the encrypted alert store.

These prove the on-disk file is unreadable without the key: the plaintext
reasons/level never appear in the ciphertext, decryption with the real key
recovers them, and decryption with a wrong key fails.

The tests use an in-memory keyring backend and a temp data dir so they never
touch the real OS keychain or the user's history file. Run with::

    pytest tests/
"""

from __future__ import annotations

import base64
import importlib
import os
import tempfile

import keyring
from keyring.backend import KeyringBackend


class _MemKeyring(KeyringBackend):
    """In-memory keyring so tests never touch the real OS keychain."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self._store: dict = {}

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def delete_password(self, service, username):
        self._store.pop((service, username), None)


def _fresh_store(tmpdir: str):
    """Import secure_store with a temp data dir and in-memory keyring."""
    os.environ["DOUBLESPEAK_DATA_DIR"] = tmpdir
    keyring.set_keyring(_MemKeyring())
    # Reload config + store so the env var takes effect.
    from doublespeak import config as cfg

    importlib.reload(cfg)
    from doublespeak import secure_store

    importlib.reload(secure_store)
    return secure_store


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        store = _fresh_store(tmp)
        store.wipe_all()
        store.save_alert("High", ["Asked you to buy gift cards", "Pressured you"])
        store.save_alert("Medium", ["Told you to keep it secret"])

        alerts = store.load_alerts()
        assert len(alerts) == 2
        # Newest first.
        assert alerts[0].timestamp >= alerts[1].timestamp
        levels = {a.level for a in alerts}
        assert levels == {"High", "Medium"}
        assert any("gift cards" in r for a in alerts for r in a.reasons)


def test_record_contains_no_audio_or_transcript_fields():
    with tempfile.TemporaryDirectory() as tmp:
        store = _fresh_store(tmp)
        store.wipe_all()
        rec = store.save_alert("High", ["x"])
        # Only the three allowed fields exist.
        assert set(vars(rec)) == {"timestamp", "level", "reasons"}


def test_file_is_unreadable_without_key():
    with tempfile.TemporaryDirectory() as tmp:
        store = _fresh_store(tmp)
        store.wipe_all()
        secret = "Asked you to buy gift cards urgently"
        store.save_alert("High", [secret])

        raw = store.config.HISTORY_FILE.read_text(encoding="ascii")
        # Ciphertext on disk must not leak the plaintext reason or level words.
        assert secret not in raw
        assert "gift cards" not in raw
        assert "High" not in raw
        # Format is nonce:ciphertext base64 lines.
        assert ":" in raw


def test_wrong_key_cannot_decrypt():
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    with tempfile.TemporaryDirectory() as tmp:
        store = _fresh_store(tmp)
        store.wipe_all()
        store.save_alert("High", ["secret reason"])

        line = store.config.HISTORY_FILE.read_text(encoding="ascii").splitlines()[0]
        nonce_b64, ct_b64 = line.split(":", 1)
        nonce = base64.b64decode(nonce_b64)
        ciphertext = base64.b64decode(ct_b64)

        wrong_key = AESGCM.generate_key(bit_length=256)
        try:
            AESGCM(wrong_key).decrypt(nonce, ciphertext, None)
            raise AssertionError("decryption with the wrong key should fail")
        except InvalidTag:
            pass  # expected


def test_wipe_all_clears_history():
    with tempfile.TemporaryDirectory() as tmp:
        store = _fresh_store(tmp)
        store.save_alert("Low", ["nothing"])
        store.wipe_all()
        assert store.load_alerts() == []
