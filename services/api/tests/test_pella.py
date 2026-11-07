"""Pellav2 voter: pinned, verified, safely loaded, and never fatal. No real weights are needed for any of these."""
import os
import pickle

import numpy as np
import pytest

from doublespeak.signals import pella, windows

SR = 16_000


def tone(seconds, amp=0.1):
    t = np.arange(int(seconds * SR)) / SR
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(pella, "_model", None)
    monkeypatch.setattr(pella, "_error", "")
    for k in ("PELLA_MODEL", "PELLA_WEIGHTS", "PELLA_MAX_WINDOWS"):
        monkeypatch.delenv(k, raising=False)


def test_not_applicable_when_not_configured():
    t = pella.pella_vote(tone(8))
    assert not t.applicable and "PELLA_MODEL" in t.evidence


def test_degrades_when_weights_are_not_cached(monkeypatch):
    pytest.importorskip("torch"); pytest.importorskip("torchaudio"); pytest.importorskip("transformers"); pytest.importorskip("scipy")
    monkeypatch.setenv("PELLA_MODEL", pella.REPO)
    monkeypatch.setattr(pella, "weights_path", lambda: None)
    t = pella.pella_vote(tone(8))
    assert not t.applicable and "make models" in t.evidence


def _need_stack():
    for m in ("torch", "torchaudio", "transformers", "scipy"):
        pytest.importorskip(m)


def _pin(monkeypatch, data: bytes):
    import hashlib
    monkeypatch.setattr(pella, "SIZE", len(data))
    monkeypatch.setattr(pella, "SHA256", hashlib.sha256(data).hexdigest())


def test_refuses_weights_that_fail_the_hash_even_at_the_right_size(monkeypatch, tmp_path):
    _need_stack()
    bad = tmp_path / "evil.pt"
    bad.write_bytes(b"A" * 64)
    _pin(monkeypatch, b"B" * 64)                     # same size, so only the HASH can refuse it
    monkeypatch.setenv("PELLA_MODEL", str(bad))
    monkeypatch.setattr(pella, "safe_state_dict", lambda p: (_ for _ in ()).throw(AssertionError("must not even try to load")))
    t = pella.pella_vote(tone(8))
    assert not t.applicable and "SHA-256" in t.evidence


def test_verify_hashes_every_time_and_ignores_a_planted_marker(monkeypatch, tmp_path):
    f = tmp_path / "w.pt"
    f.write_bytes(b"pretend weights")
    _pin(monkeypatch, b"pretend weights")
    assert pella.verify(f) and not (tmp_path / "w.pt.ds-verified").exists()      # no marker is written any more
    (tmp_path / "w.pt.ds-verified").write_text(pella.SHA256)                     # an attacker plants one...
    f.write_bytes(b"pretend WEIGHTS")                                            # ...and swaps in same-size bytes
    assert not pella.verify(f)


def test_a_swap_between_the_hash_check_and_the_load_is_refused(monkeypatch, tmp_path):
    _need_stack()
    f = tmp_path / "w.pt"
    f.write_bytes(b"good weights!!!")
    _pin(monkeypatch, b"good weights!!!")
    monkeypatch.setenv("PELLA_MODEL", str(f))

    class Fake:
        def load_state_dict(self, sd): pass
        def to(self, d): return self
        def eval(self): return self

    def swap_during_load(path):
        path.write_bytes(b"evil  weights!!!")           # same size, replaced after the hash passed
        return {}
    monkeypatch.setattr(pella, "_build", lambda: Fake())
    monkeypatch.setattr(pella, "safe_state_dict", swap_during_load)
    t = pella.pella_vote(tone(8))
    assert not t.applicable and "changed while loading" in t.evidence


def test_backbone_config_bounds_and_pin():
    import types
    assert pella.check_config(types.SimpleNamespace(num_hidden_layers=24, hidden_size=1024)) == ""
    assert "out of bounds" in pella.check_config(types.SimpleNamespace(num_hidden_layers=10**9, hidden_size=1024))
    assert "out of bounds" in pella.check_config(types.SimpleNamespace(num_hidden_layers=24, hidden_size=10**9))
    assert "out of bounds" in pella.check_config(types.SimpleNamespace(num_hidden_layers="24", hidden_size=1024))
    assert len(pella.BACKBONE_REVISION) == 40 and len(pella.BACKBONE_CONFIG_SHA256) == 64


def test_old_torch_is_refused(monkeypatch, tmp_path):
    torch = pytest.importorskip("torch"); _need_stack()
    f = tmp_path / "w.pt"
    f.write_bytes(b"x" * 8)
    _pin(monkeypatch, b"x" * 8)
    monkeypatch.setenv("PELLA_MODEL", str(f))
    monkeypatch.setattr(torch, "__version__", "2.5.1")
    t = pella.pella_vote(tone(8))
    assert not t.applicable and "too old" in t.evidence


def test_safe_loader_refuses_a_pickle_that_would_run_code(tmp_path):
    torch = pytest.importorskip("torch")
    marker = tmp_path / "pwned"

    class Evil:
        def __reduce__(self):
            return (os.system, (f"touch {marker}",))

    f = tmp_path / "trap.pt"
    torch.save({"x": Evil()}, f)
    with pytest.raises(Exception):
        pella.safe_state_dict(f)
    assert not marker.exists()


def test_safe_loader_reads_plain_tensors(tmp_path):
    torch = pytest.importorskip("torch")
    f = tmp_path / "ok.pt"
    torch.save({"w": torch.ones(3)}, f)
    assert pella.safe_state_dict(f)["w"].tolist() == [1.0, 1.0, 1.0]


def test_vote_averages_the_windows_and_reports_the_highest(monkeypatch):
    pytest.importorskip("torch"); pytest.importorskip("torchaudio"); pytest.importorskip("transformers"); pytest.importorskip("scipy")
    monkeypatch.setenv("PELLA_MODEL", pella.REPO)
    monkeypatch.setattr(pella, "_model", object())
    seen = {}
    monkeypatch.setattr(pella, "score_windows", lambda chunks: (seen.setdefault("n", len(chunks)), [0.2, 0.9, 0.5][:len(chunks)])[1])
    t = pella.pella_vote(tone(20))
    assert t.applicable and seen["n"] == 3 and abs(t.score - (0.2 + 0.9 + 0.5) / 3) < 1e-9
    assert "3 windows" in t.evidence and "0.90" in t.evidence


def test_vote_skips_silence_and_survives_inference_errors(monkeypatch):
    pytest.importorskip("torch"); pytest.importorskip("torchaudio"); pytest.importorskip("transformers"); pytest.importorskip("scipy")
    monkeypatch.setenv("PELLA_MODEL", pella.REPO)
    monkeypatch.setattr(pella, "_model", object())
    assert not pella.pella_vote(np.zeros(8 * SR, dtype=np.float32)).applicable
    monkeypatch.setattr(pella, "score_windows", lambda chunks: (_ for _ in ()).throw(RuntimeError("boom")))
    t = pella.pella_vote(tone(8))
    assert not t.applicable and "failed" in t.evidence


def test_prep_gives_exactly_four_seconds_in_range():
    pytest.importorskip("scipy")
    for secs in (3.0, 4.0, 4.0):
        x = pella.prep(tone(secs, amp=0.02))
        assert x.dtype == np.float32 and len(x) == 4 * SR and np.isfinite(x).all() and np.abs(x).max() <= 1.0


@pytest.mark.parametrize("want,mps,expected", [
    ("", True, "mps"),          # default: MPS whenever it is there (#25)
    ("", False, "cpu"),
    ("auto", True, "mps"),
    ("mps", False, "cpu"),      # asked for MPS on a machine without it: fall back, never raise
    ("cpu", True, "cpu"),       # explicit CPU always wins
])
def test_device_prefers_mps_when_available(want, mps, expected):
    assert pella.pick_device(want, mps_available=mps) == expected


def test_load_logs_device_and_seconds(monkeypatch, tmp_path, caplog):
    torch = pytest.importorskip("torch")
    weights = tmp_path / "w.pt"
    weights.write_bytes(b"x")
    monkeypatch.setenv("PELLA_WEIGHTS", str(weights))
    monkeypatch.setenv("PELLA_DEVICE", "cpu")
    monkeypatch.setattr(pella, "verify", lambda p: True)
    monkeypatch.setattr(pella, "_build", lambda: torch.nn.Linear(1, 1))
    monkeypatch.setattr(pella, "safe_state_dict", lambda p: torch.nn.Linear(1, 1).state_dict())
    with caplog.at_level("INFO", logger="doublespeak.pella"):
        pella._load()
    assert pella._model is not None, pella._error
    assert any("loaded Pellav2 on cpu in" in r.getMessage() and r.getMessage().endswith("s") for r in caplog.records)
