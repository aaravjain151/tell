"""learned_tells: interpretable features on synthetic signals, safe pinned loading, windowing, and the off switch."""
import hashlib
import json

import numpy as np
import pytest

from tell import pipeline, thresholds as T
from tell.signals import acoustic, learned, tell_features as TF
from tests.synth import make_call, to_wav_bytes

SR = 16_000


def tone(seconds, f0=150.0, amp=0.2, jitter=0.0, seed=0):
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    f = f0 * (1 + jitter * rng.standard_normal(n).cumsum() / np.sqrt(np.arange(1, n + 1)))
    ph = np.cumsum(2 * np.pi * f / SR)
    x = sum(np.sin(k * ph) / k for k in range(1, 12))
    gate = ((np.arange(n) % int(0.45 * SR)) < int(0.3 * SR)).astype(float)   # 300 ms "syllables", 150 ms gaps
    floor = 1e-4 * rng.standard_normal(n)
    return (amp * x / 3 * gate + floor).astype(np.float32)


# ---------------------------------------------------------------- features
def test_features_are_all_present_and_never_raise():
    for x in (np.zeros(4 * SR, np.float32), np.ones(10, np.float32), tone(4), np.full(4 * SR, np.nan, np.float32)):
        f = TF.window_features(x)
        assert set(f) == set(TF.FEATURE_NAMES)


def test_silence_gives_nan_voice_features():
    f = TF.window_features(np.zeros(4 * SR, np.float32))
    assert np.isnan(f["cpp_db"]) and np.isnan(f["f0_std_st"]) and f["digital_zero_frac"] == 1.0


def test_steady_tone_reads_as_steady_regular_voicing():
    steady = TF.window_features(tone(4))
    assert 0 <= steady["f0_std_st"] < 0.5                          # a fixed 150 Hz pitch has almost no spread
    assert steady["hnr_db"] > 5 and steady["cpp_db"] > 10            # perfectly periodic: noise-free, very regular voicing
    noisy = TF.window_features(tone(4) + np.random.default_rng(1).normal(0, 0.01, 4 * SR).astype(np.float32))
    assert noisy["hnr_db"] < steady["hnr_db"] and noisy["harm_valley_db"] < steady["harm_valley_db"]


def test_pitch_wander_raises_pitch_spread():
    a = TF.window_features(tone(4))
    b = TF.window_features(tone(4, jitter=0.02, seed=3))
    assert b["f0_std_st"] > a["f0_std_st"]


def test_pauses_are_measured():
    x = make_call("human", seconds=4.0, seed=2)
    f = TF.window_features(x)
    assert 0 < f["pause_share"] < 1 and f["max_gap_ms"] >= 0 and np.isfinite(f["pause_depth_db"])


def test_band_ratio_separates_wideband_from_phone_band():
    rng = np.random.default_rng(0)
    wide = rng.normal(0, 0.1, 4 * SR)
    X = np.fft.rfft(wide)
    X[np.fft.rfftfreq(len(wide), 1 / SR) > 3800] = 0
    narrow = np.fft.irfft(X, n=len(wide))
    assert TF.band_ratio_db(wide) > T.BAND_LIMIT_DB > TF.band_ratio_db(narrow)


# ---------------------------------------------------------------- band_limited (the user-facing line)
def test_band_limited_false_on_wideband_true_on_phone_band():
    x = make_call("human", seed=3)
    rng = np.random.default_rng(5)
    x = (x + rng.normal(0, 0.003, len(x))).astype(np.float32)        # wideband room noise: content above 5 kHz
    _, ctx = acoustic.analyze(x, 14000)
    assert ctx["band_limited"] is False and ctx["high_band_rel_db"] > T.BAND_LIMIT_DB
    _, ctx2 = acoustic.analyze(make_call("human", seed=3, phone_band=True), 14000)
    assert ctx2["band_limited"] is True


# ---------------------------------------------------------------- safe loading and pinning
D_EMB, LAYER = 4, 12


def _weights(extra=None, intercept=0.0):
    nf = len(TF.FEATURE_NAMES)
    doc = {"format": "tell-learned-tells/1", "version": "test",
           "models": {"interp": {"features": TF.FEATURE_NAMES, "median": [0.0] * nf, "mean": [0.0] * nf, "scale": [1.0] * nf,
                                 "clip": 5.0, "coef": [0.0] * nf, "intercept": 0.0},
                      "full": {"features": [], "median": [], "mean": [], "scale": [], "clip": 5.0, "coef": [1.0, 0.0],
                               "intercept": intercept,
                               "emb": {"layer": LAYER, "k": 2, "dim": D_EMB, "mean": [0.0] * D_EMB,
                                       "components": [[1.0, 0, 0, 0], [0, 1.0, 0, 0]], "z_mean": [0.0, 0.0], "z_scale": [1.0, 1.0]}}},
           "meaning": {}}
    if extra:
        extra(doc)
    return json.dumps(doc).encode()


def _extras(x, first=0.0):
    """What pella_vote_ex hands over: the same windows Pellav2 scored, with one embedding row per window."""
    from tell.signals import windows
    ws = windows.windows(x, SR, win_s=4.0, hop_s=2.0, max_n=16)
    emb = np.zeros((len(ws), D_EMB))
    emb[:, 0] = first
    return {"t": [float(t) for t, _ in ws], "emb": {LAYER: emb}, "p": [0.5] * len(ws)}


@pytest.fixture
def pinned(monkeypatch, tmp_path):
    def make(raw: bytes, pin: bytes | None = None):
        p = tmp_path / "w.json"
        p.write_bytes(raw)
        monkeypatch.setattr(learned, "WEIGHTS", p)
        monkeypatch.setattr(learned, "SHA256", hashlib.sha256(pin if pin is not None else raw).hexdigest())
        monkeypatch.setattr(learned, "_cache", None)
        monkeypatch.setattr(learned, "_error", "")
        monkeypatch.setenv("TELL_LEARNED_TELLS", "1")
        return p
    return make


def test_scores_every_pellav2_window_and_averages_logits(pinned):
    pinned(_weights())
    x = tone(10)
    t = learned.learned_vote(x, _extras(x, first=2.0))            # logit 2 in every window
    assert t.applicable and abs(t.score - 1 / (1 + np.exp(-2.0))) < 1e-9 and t.name == "learned_tells"
    assert len(t.detail["windows"]) == 4                           # 10 s -> 4 windows of 4 s at a 2 s hop
    assert t.weight == T.ACOUSTIC_WEIGHTS["learned_tells"]


def test_it_votes_both_ways(pinned):
    pinned(_weights())
    x = tone(10)
    t = learned.learned_vote(x, _extras(x, first=-3.0))           # well inside the human range: a vote toward human
    assert t.applicable and abs(t.score - 1 / (1 + np.exp(3.0))) < 1e-9


def test_needs_the_pellav2_embedding(pinned):
    pinned(_weights())
    x = tone(10)
    assert "Pellav2" in learned.learned_vote(x, None).evidence
    bad = _extras(x)
    bad["emb"][LAYER] = bad["emb"][LAYER][:2]                       # rows do not line up with the windows
    assert not learned.learned_vote(x, bad).applicable


def test_refuses_weights_that_fail_the_hash(pinned):
    pinned(_weights(), pin=b"something else")
    x = tone(10)
    t = learned.learned_vote(x, _extras(x))
    assert not t.applicable and "SHA-256" in t.evidence


def test_refuses_malformed_or_hostile_weights(pinned):
    nf = len(TF.FEATURE_NAMES)
    for bad in (b"not json", _weights(lambda d: d.update(format="pickle")),
                _weights(lambda d: d["models"]["interp"].update(coef=[1.0])),
                _weights(lambda d: d["models"]["interp"].update(features=["__import__"] * nf)),
                _weights(lambda d: d["models"]["interp"].update(scale=[0.0] * nf)),
                _weights(lambda d: d["models"]["full"]["emb"].update(k=10 ** 6)),
                _weights(lambda d: d["models"]["full"]["emb"].update(z_scale=[float("nan"), 1.0])),
                _weights(lambda d: d["models"].pop("full"))):
        pinned(bad)
        x = tone(10)
        assert not learned.learned_vote(x, _extras(x, first=5.0)).applicable


def test_refuses_oversized_weights(pinned, monkeypatch):
    pinned(_weights())
    monkeypatch.setattr(learned, "MAX_BYTES", 10)
    x = tone(10)
    assert not learned.learned_vote(x, _extras(x, first=5.0)).applicable


def test_shipped_weights_match_the_pin_and_are_small():
    raw = learned.WEIGHTS.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == learned.SHA256 and len(raw) < 2_000_000
    assert b"pickle" not in raw.lower()
    w = learned.parse(raw)
    assert set(w["models"]) == {"interp", "full"} and w["models"]["full"]["emb"]["layer"] == 12


def test_shipped_model_runs_on_a_real_shaped_input(monkeypatch):
    monkeypatch.setenv("TELL_LEARNED_TELLS", "1")
    monkeypatch.setattr(learned, "_cache", None)
    monkeypatch.setattr(learned, "_error", "")
    x = make_call("human", seed=1)
    from tell.signals import windows
    ws = windows.windows(x, SR, win_s=4.0, hop_s=2.0, max_n=16)
    ex = {"t": [float(t) for t, _ in ws], "emb": {12: np.zeros((len(ws), 1024))}, "p": [0.5] * len(ws)}
    t = learned.learned_vote(x, ex)
    assert 0.0 <= t.score <= 1.0 and len(t.detail["windows"]) == len(ws)


# ---------------------------------------------------------------- the off switch
def test_off_adds_nothing_and_verdict_is_bit_identical(monkeypatch):
    monkeypatch.setenv("TELL_LEARNED_TELLS", "0")
    assert learned.learned_vote(tone(10)) is None and learned.layers_needed() == ()
    wav = to_wav_bytes(make_call("tts", seed=4))
    a = pipeline.analyze(wav, "hello there")
    from tell.signals import neural
    monkeypatch.setattr(neural.learned, "learned_vote", lambda *a, **k: None)
    b = pipeline.analyze(wav, "hello there")
    assert (a.tier, a.p_ai, a.p_scam, a.confidence, a.signature) == (b.tier, b.p_ai, b.p_scam, b.confidence, b.signature)
    assert all(t.name != "learned_tells" for t in a.tells)
