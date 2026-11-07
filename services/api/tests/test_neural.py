from tell.signals import neural
import numpy as np


def test_fake_label_index_known_cards():
    assert neural.fake_label_index({0: "real", 1: "fake"}) == 1                 # garystafford, Gustking
    assert neural.fake_label_index({0: "fake", 1: "real"}) == 0                 # MelodyMachine (reversed!)
    assert neural.fake_label_index({0: "bona-fide", 1: "spoof"}) == 1           # abhishtagatya
    assert neural.fake_label_index({"0": "LABEL_0", "1": "LABEL_1"}) is None    # unknown -> refuse, don't guess
    assert neural.fake_label_index({0: "main", 1: "fail"}) is None              # no substring false hits


def test_neural_not_applicable_without_models(monkeypatch):
    monkeypatch.delenv("HF_SPOOF_MODEL", raising=False)
    monkeypatch.delenv("ANTI_SPOOF_MODEL", raising=False)
    tells = neural.analyze(np.zeros(16000 * 5, dtype=np.float32), 5.0)
    assert all(not t.applicable for t in tells)


def test_neural_short_clip_skipped():
    assert not neural.analyze(np.zeros(16000, dtype=np.float32), 1.0)[0].applicable
