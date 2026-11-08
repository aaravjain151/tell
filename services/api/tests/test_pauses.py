"""Call-level pause features (signals/pauses.py) and the optional pause stacker in learned_tells. Synthetic audio only."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from tell.signals import learned, pauses as PZ
from tests.test_learned import _extras, _weights, tone

SR = 16_000
ROOT = Path(__file__).resolve().parents[3]


def speech(gaps_ms, run_s=1.0, amp=0.2, seed=0):
    """Harmonic 'speech' runs of run_s seconds separated by the given gaps, over a faint noise floor."""
    rng = np.random.default_rng(seed)
    ph = np.cumsum(np.full(int(run_s * SR), 2 * np.pi * 140 / SR))
    run = amp * sum(np.sin(k * ph) / k for k in range(1, 10)) / 3
    parts = [run]
    for g in gaps_ms:
        parts += [np.zeros(int(g * SR / 1000)), run]
    x = np.concatenate(parts)
    return (x + 1e-4 * rng.standard_normal(x.size)).astype(np.float32)


GAPS = [200, 500, 200, 600, 200, 400, 200]          # 3 long (>= 300 ms) pauses in 8 s of speech + 2.3 s of gaps


def test_counts_long_pauses_per_minute_and_their_length():
    f = PZ.call_pause_features(speech(GAPS))
    span = 8 * 1.0 + sum(GAPS) / 1000
    assert f["long_pause_per_min"] == pytest.approx(60 * 3 / span, rel=0.05)
    assert f["long_pause_median_ms"] == pytest.approx(500, abs=30)
    assert f["pause_share"] == pytest.approx(sum(GAPS) / 1000 / span, abs=0.03)
    assert f["speech_run_median_s"] == pytest.approx(1.0, abs=0.05)
    assert 0.3 < f["pause_cv"] < 0.7


def test_fewer_shorter_pauses_read_lower():
    human = PZ.call_pause_features(speech([600, 450, 700, 500, 650, 400, 550]))
    tts = PZ.call_pause_features(speech([250, 320, 250, 250, 330, 250, 250]))
    assert human["long_pause_per_min"] > tts["long_pause_per_min"]
    assert human["long_pause_median_ms"] > tts["long_pause_median_ms"]


def test_level_does_not_matter():
    a, b = PZ.call_pause_features(speech(GAPS, amp=0.2)), PZ.call_pause_features(speech(GAPS, amp=0.02))
    assert a["long_pause_per_min"] == pytest.approx(b["long_pause_per_min"])


@pytest.mark.parametrize("x", [np.zeros(SR * 10, np.float32), speech([400, 400], run_s=0.8), np.zeros(10, np.float32)])
def test_too_little_speech_is_nan_never_raises(x):
    f = PZ.call_pause_features(x)
    assert set(f) == set(PZ.PAUSE_FEATURES) and all(np.isnan(v) for v in f.values())
    assert "not enough speech" in PZ.describe(f)


# ---------------------------------------------------------------- the stacker inside learned_tells
@pytest.fixture
def pinned(monkeypatch, tmp_path):
    def make(raw: bytes):
        p = tmp_path / "w.json"
        p.write_bytes(raw)
        monkeypatch.setattr(learned, "WEIGHTS", p)
        monkeypatch.setattr(learned, "SHA256", hashlib.sha256(raw).hexdigest())
        monkeypatch.setattr(learned, "_cache", None)
        monkeypatch.setattr(learned, "_error", "")
        monkeypatch.setenv("TELL_LEARNED_TELLS", "1")
    return make


def _with_pauses(coef=None, head_coef=1.0, intercept=0.0, feats=PZ.PAUSE_FEATURES):
    n = len(feats)
    block = {"features": list(feats), "median": [0.0] * n, "mean": [0.0] * n, "scale": [1.0] * n, "clip": 5.0,
             "coef": coef if coef is not None else [0.0] * n, "head_coef": head_coef, "intercept": intercept}
    return _weights(extra=lambda d: d.update(pauses=block))


def test_neutral_block_is_identical_to_no_block(pinned):
    x = speech(GAPS + [300, 500])
    pinned(_weights())
    plain = learned.learned_vote(x, _extras(x, first=1.5))
    pinned(_with_pauses())
    stacked = learned.learned_vote(x, _extras(x, first=1.5))
    assert stacked.score == plain.score and "pauses:" in stacked.evidence
    assert stacked.detail["pauses"]["long_pause_per_min"] > 0 and "pauses" not in plain.detail


def test_many_long_pauses_pull_toward_human(pinned):
    x = speech([600, 650, 700, 600, 550, 700, 650])
    pinned(_with_pauses())
    base = learned.learned_vote(x, _extras(x, first=0.5)).score
    pinned(_with_pauses(coef=[-0.05, 0, 0, 0, 0]))                 # learned sign: more long pauses -> human
    t = learned.learned_vote(x, _extras(x, first=0.5))
    assert t.applicable and t.score < base and "toward human" in t.evidence


def test_head_coef_and_intercept_apply_to_the_mean_logit(pinned):
    x = tone(10)                                                    # 300/150 ms gating: no long pauses
    pinned(_with_pauses(head_coef=2.0, intercept=-1.0))
    t = learned.learned_vote(x, _extras(x, first=1.0))
    assert t.score == pytest.approx(1 / (1 + np.exp(-(2.0 * 1.0 - 1.0))))


@pytest.mark.parametrize("bad", [
    dict(feats=("long_pause_per_min", "not_a_feature")),
    dict(head_coef=0.0),
    dict(head_coef=-1.0),
    dict(coef=[0.0, 0.0]),
])
def test_refuses_bad_pause_blocks(pinned, bad):
    pinned(_with_pauses(**bad))
    x = speech(GAPS)
    t = learned.learned_vote(x, _extras(x))
    assert not t.applicable and "unavailable" in t.evidence


def test_training_export_block_is_accepted_by_the_runtime():
    sys.path.insert(0, str(ROOT / "training" / "learned_tells"))
    import pauses as TP                                             # training/learned_tells/pauses.py
    rng = np.random.default_rng(0)
    n = 200
    y = np.repeat([0, 1], n // 2)
    h = rng.normal(y * 2.0 - 1.0, 1.0)
    P = rng.normal(0, 1, (n, len(PZ.PAUSE_FEATURES)))
    P[:, 0] += (1 - y) * 1.5                                        # humans: more long pauses
    P[rng.random(P.shape) < 0.1] = np.nan
    s = TP.Stacker().fit(h, P, y, np.ones(n))
    b = s.block()
    assert b["head_coef"] > 0 and b["coef"][0] < 0                  # head kept, long pauses read toward human
    pz = learned.parse_pauses(json.loads(json.dumps(b)))
    x = speech(GAPS)
    rt, _ = learned.call_logit(0.7, pz, x)
    f = PZ.call_pause_features(x)
    ref = s.decision(np.array([0.7]), np.array([[f[k] for k in PZ.PAUSE_FEATURES]]))[0]
    assert rt == pytest.approx(ref, abs=1e-4)                       # runtime == training decision (6-dp rounding)
