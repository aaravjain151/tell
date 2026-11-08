import os

from tell import offline_guard

KEYS = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY", "DO_NOT_TRACK")


def clean(monkeypatch):
    for k in (*KEYS, "TELL_OFFLINE"):
        monkeypatch.delenv(k, raising=False)


def test_not_applied_unless_asked(monkeypatch):
    clean(monkeypatch)
    assert offline_guard.apply_from_env() is False
    assert not offline_guard.is_enforced() and "HF_HUB_OFFLINE" not in os.environ


def test_applied_from_env_and_overwrites_a_loose_shell(monkeypatch):
    clean(monkeypatch)
    monkeypatch.setenv("TELL_OFFLINE", "1")
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")          # a shell that tries to re-enable the network
    assert offline_guard.apply_from_env() is True
    assert all(os.environ[k] == "1" for k in KEYS) and offline_guard.is_enforced()


def test_enforce_is_idempotent(monkeypatch):
    clean(monkeypatch)
    offline_guard.enforce(); offline_guard.enforce()
    assert offline_guard.is_enforced()
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)           # leave the process as we found it
