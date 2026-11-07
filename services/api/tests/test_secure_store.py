"""Opt-in encrypted history. Offline: a fake key provider stands in for the OS keychain."""
import builtins
import os
import stat

import pytest
from fastapi.testclient import TestClient

from doublespeak import main, pipeline, secure_store as ss
from doublespeak.types import Tell, Verdict

SENTINEL = "ZXQ-SENTINEL-7731-wire-the-gift-cards"
KEY = bytes(range(32))
client = TestClient(main.app)


@pytest.fixture(autouse=True)
def hist(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUBLESPEAK_DATA_DIR", str(tmp_path / "h"))
    monkeypatch.setenv("DOUBLESPEAK_HISTORY", "1")
    monkeypatch.setattr(ss, "keyring_key_provider", lambda: KEY)
    return tmp_path / "h"


def verdict(p=0.8, tier="scam", evidence=SENTINEL):
    tells = [Tell("urgency", "intent", 0.9, 1.0, evidence), Tell("payment_rails", "intent", 0.8, 1.0, evidence),
             Tell("secrecy", "intent", 0.7, 1.0, evidence), Tell("llm_isms", "script", 0.6, 0.5, evidence),
             Tell("weak", "script", 0.2, 1.0, evidence), Tell("na", "acoustic", 0.99, 1.0, evidence, applicable=False)]
    return Verdict(tier=tier, p_ai=p, p_scam=0.912345, confidence=0.7, disclosed_ai=False, headline=SENTINEL,
                   advice=SENTINEL, tells=tells, thresholds_version="v9", transcript=SENTINEL,
                   cost={"x": SENTINEL}, egress={"x": SENTINEL})


def test_round_trip():
    assert ss.record_verdict(verdict()) == "ok"
    recs, skipped = ss.read_all()
    assert skipped == 0 and len(recs) == 1
    r = recs[0]
    assert set(r) == {"ts", "tier", "p_ai", "p_scam", "thresholds_version", "tells"}
    assert r["tier"] == "scam" and r["p_scam"] == 0.91 and r["thresholds_version"] == "v9"
    assert r["tells"] == ["urgency", "payment_rails", "secrecy"]  # top 3 fired, not weak/inapplicable


def test_newest_first():
    for p in (0.1, 0.2, 0.3):
        ss.record_verdict(verdict(p=p))
    assert [r["p_ai"] for r in ss.read_all()[0]] == [0.3, 0.2, 0.1]


def test_sentinel_never_stored():
    ss.record_verdict(verdict())
    assert SENTINEL.encode() not in ss.history_path().read_bytes()
    plain = str(ss.read_all()[0]).encode()
    assert SENTINEL.encode() not in plain and b"wire" not in plain
    assert SENTINEL not in str(ss.record_from_verdict(verdict()))


def test_tamper_detected_and_skipped():
    ss.record_verdict(verdict(p=0.1))
    ss.record_verdict(verdict(p=0.2))
    p = ss.history_path()
    lines = p.read_text().splitlines()
    n, c = lines[0].split(":")
    flipped = "A" if c[4] != "A" else "B"
    lines[0] = f"{n}:{c[:4]}{flipped}{c[5:]}"
    lines.append("garbage-not-a-record")
    p.write_text("\n".join(lines) + "\n")
    recs, skipped = ss.read_all()
    assert [r["p_ai"] for r in recs] == [0.2] and skipped == 2


def test_wrong_key_reads_nothing(monkeypatch):
    ss.record_verdict(verdict())
    monkeypatch.setattr(ss, "keyring_key_provider", lambda: bytes(32))
    recs, skipped = ss.read_all()
    assert recs == [] and skipped == 1


def test_fresh_nonce_per_record():
    ss.record_verdict(verdict())
    ss.record_verdict(verdict())
    nonces = [ln.split(":")[0] for ln in ss.history_path().read_text().splitlines()]
    assert len(set(nonces)) == 2


def test_permissions(hist):
    ss.record_verdict(verdict())
    assert stat.S_IMODE(os.stat(hist).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(ss.history_path()).st_mode) == 0o600


def test_disabled_by_default(monkeypatch, hist):
    monkeypatch.delenv("DOUBLESPEAK_HISTORY")
    assert ss.record_verdict(verdict()) == "disabled"
    assert not hist.exists()
    assert client.get("/history").json()["status"] == "disabled"
    assert client.get("/history/status").json()["enabled"] is False


@pytest.mark.parametrize("missing", ["cryptography", "keyring"])
def test_missing_dependency_degrades(monkeypatch, missing, hist):
    monkeypatch.undo()  # drop the fake provider so the real one runs
    monkeypatch.setenv("DOUBLESPEAK_DATA_DIR", str(hist))
    monkeypatch.setenv("DOUBLESPEAK_HISTORY", "1")
    real = builtins.__import__

    def fake(name, *a, **k):
        if name.split(".")[0] == missing:
            raise ImportError(missing)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    out = ss.record_verdict(verdict())
    assert out.startswith("unavailable") and missing in out
    st = ss.status()
    assert st["enabled"] and not st["available"] and missing in st["reason"]
    assert not hist.exists()  # no plaintext fallback, nothing on disk


def test_locked_keychain_degrades(monkeypatch, hist):
    def locked():
        raise ss.HistoryUnavailable("keychain unavailable (KeyringLocked)")
    monkeypatch.setattr(ss, "keyring_key_provider", locked)
    assert ss.record_verdict(verdict()).startswith("unavailable")
    assert not hist.exists()
    assert client.get("/history/status").json()["available"] is False


def test_write_failure_never_fails_analysis(monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(ss, "append", boom)
    v = pipeline.analyze(None, "Hello, this is your bank. Act now and buy gift cards.")
    assert v.tier


def test_pipeline_appends_only_derived_fields():
    pipeline.analyze(None, f"Hello it is the bank, {SENTINEL}, act now immediately")
    recs, _ = ss.read_all()
    assert len(recs) == 1 and SENTINEL not in str(recs)
    assert SENTINEL.encode() not in ss.history_path().read_bytes()


def test_wipe_and_api():
    for _ in range(3):
        ss.record_verdict(verdict())
    st = client.get("/history/status").json()
    assert st == {"enabled": True, "available": True, "reason": "", "count": 3}
    assert len(client.get("/history").json()["records"]) == 3
    assert client.delete("/history").json() == {"deleted": 3}
    assert client.get("/history").json()["records"] == [] and ss.count() == 0


def test_read_cap():
    for _ in range(205):
        ss.append(ss.record_from_verdict(verdict()), lambda: KEY)
    assert len(ss.read_all()[0]) == 200
    assert len(client.get("/history").json()["records"]) == 200
