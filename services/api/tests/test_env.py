"""D-013: settings are TELL_*; the pre-rename DOUBLESPEAK_* names still work as a fallback."""
import pytest

from tell import env, limits, secure_store


def test_new_name_is_read(monkeypatch):
    monkeypatch.delenv("DOUBLESPEAK_HISTORY", raising=False)
    monkeypatch.setenv("TELL_HISTORY", "1")
    assert env.get("TELL_HISTORY") == "1" and secure_store.enabled()


def test_legacy_name_is_a_fallback(monkeypatch):
    monkeypatch.delenv("TELL_HISTORY", raising=False)
    monkeypatch.setenv("DOUBLESPEAK_HISTORY", "1")
    assert env.get("TELL_HISTORY") == "1" and secure_store.enabled()


def test_new_name_wins_over_legacy(monkeypatch):
    monkeypatch.setenv("TELL_MAX_AUDIO_S", "5")
    monkeypatch.setenv("DOUBLESPEAK_MAX_AUDIO_S", "99")
    assert limits.max_audio_s() == 5


def test_empty_new_name_counts_as_set(monkeypatch):
    monkeypatch.setenv("TELL_HISTORY", "")
    monkeypatch.setenv("DOUBLESPEAK_HISTORY", "1")
    assert not secure_store.enabled()


def test_default_when_neither_is_set(monkeypatch):
    monkeypatch.delenv("TELL_LLM_MODEL", raising=False)
    monkeypatch.delenv("DOUBLESPEAK_LLM_MODEL", raising=False)
    assert env.get("TELL_LLM_MODEL", "d") == "d"


def test_only_tell_names_are_accepted():
    with pytest.raises(ValueError):
        env.get("DOUBLESPEAK_HISTORY")


def test_package_reads_settings_only_through_env_helper():
    """No module reads a DOUBLESPEAK_ name directly; env.py is the one place that knows the legacy prefix."""
    from pathlib import Path
    pkg = Path(env.__file__).resolve().parent
    offenders = [p.name for p in pkg.rglob("*.py") if p.name != "env.py" and "DOUBLESPEAK_" in p.read_text()]
    assert offenders == []
