"""Shadow layers: mechanics on synthetic signals, and proof they cannot change a verdict."""
from __future__ import annotations

import json
import math

import numpy as np

from doublespeak import pipeline
from doublespeak.signals import shadow
from tests.synth import make_call, to_wav_bytes

SR = 16_000


def _noise(sec, amp, seed=0):
    return (np.random.default_rng(seed).normal(0, amp, int(sec * SR))).astype(np.float32)


def _bursts(sec=10.0, period=1.0, on=0.6, amp=0.2, floor=0.0005, gated=False, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(sec * SR)) / SR
    carrier = np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 440 * t)
    x = amp * carrier * ((t % period) < on)
    if gated:
        return x.astype(np.float32)
    return (x + rng.normal(0, floor, t.size)).astype(np.float32)


def test_noise_floor_level_and_variability():
    quiet, loud = _bursts(floor=0.00005), _bursts(floor=0.01)
    assert shadow.noise_floor_dbfs(quiet)[0] < shadow.noise_floor_dbfs(loud)[0] - 20
    assert shadow.noise_floor_dbfs(loud)[0] > -60
    steady = shadow.noise_floor_variability_db(_noise(8, 0.01))[0]
    drift = np.concatenate([_noise(1, a, i) for i, a in enumerate([0.0005, 0.02, 0.001, 0.03, 0.0003, 0.02, 0.002, 0.01])])
    assert shadow.noise_floor_variability_db(drift)[0] > steady + 5
    assert math.isnan(shadow.noise_floor_variability_db(_noise(1, 0.01))[0])


def test_digital_zero_and_gating():
    gated = _bursts(gated=True)                       # exact zeros between bursts
    live = _bursts(floor=0.003)
    assert shadow.digital_zero_run_ms(gated)[0] >= 300
    assert shadow.digital_zero_run_ms(live)[0] < 1
    assert shadow.gate_transitions_per_min(gated)[0] > 30
    assert shadow.gate_transitions_per_min(live)[0] == 0


def test_modulation_ratio_syllabic_vs_steady():
    t = np.arange(10 * SR) / SR
    syll = (0.1 * (1 + np.sin(2 * np.pi * 5 * t)) * np.random.default_rng(1).normal(0, 1, t.size)).astype(np.float32)
    assert shadow.modulation_4_16_ratio(syll)[0] > 0.6
    assert shadow.modulation_4_16_ratio(_noise(10, 0.1, 2))[0] < 0.4
    assert math.isnan(shadow.modulation_4_16_ratio(_noise(0.5, 0.1))[0])


def test_spectral_flatness_white_vs_tonal():
    t = np.arange(4 * SR) / SR
    tone = (0.3 * np.sin(2 * np.pi * 1000 * t) + 0.001 * np.random.default_rng(3).normal(0, 1, t.size)).astype(np.float32)
    assert shadow.spectral_flatness_300_3400(_noise(4, 0.1))[0] > 0.8
    assert shadow.spectral_flatness_300_3400(tone)[0] < 0.1


def _utterances(amps):
    parts = []
    for a in amps:
        t = np.arange(int(0.8 * SR)) / SR
        parts += [(a * np.sin(2 * np.pi * 200 * t)).astype(np.float32), np.full(int(0.4 * SR), 1e-4, np.float32)]
    return np.concatenate(parts)


def test_loudness_consistency_even_vs_uneven():
    even = shadow.loudness_consistency_db(_utterances([0.2] * 6))[0]
    uneven = shadow.loudness_consistency_db(_utterances([0.02, 0.2, 0.05, 0.3, 0.01, 0.15]))[0]
    assert even < 1.0 < uneven
    assert math.isnan(shadow.loudness_consistency_db(_utterances([0.2, 0.2]))[0])


def test_persistence_band_run():
    s = [0.9, 0.3, 0.4, 0.25, 0.5, 0.1, 0.7]
    p = shadow.persistence(s)
    assert p["longest_run_0_2_0_6"][0] == 4          # 0.3 0.4 0.25 0.5
    assert abs(p["mean"][0] - np.mean(s)) < 1e-9
    assert p["min"][0] == 0.1 and abs(p["frac_gt_0_5"][0] - 2 / 7) < 1e-9
    assert math.isnan(shadow.persistence([0.5])["mean"][0])
    assert math.isnan(shadow.persistence(None)["min"][0])


def test_bandwidth_and_snr():
    wide = _noise(4, 0.1)
    spec = np.fft.rfft(wide)
    spec[int(len(wide) * 4000 / SR):] = 0
    narrow = np.fft.irfft(spec, n=len(wide)).astype(np.float32)
    assert shadow.bandwidth_hz(wide)[0] >= 7500
    assert 3500 <= shadow.bandwidth_hz(narrow)[0] <= 4300
    assert shadow.snr_db(_bursts(floor=0.0005))[0] > 40
    assert shadow.snr_db(_bursts(floor=0.05, amp=0.1))[0] < 15


def test_compute_all_is_json_safe_and_never_raises():
    out = shadow.compute_all(_bursts(), [{"t": i, "pella": 0.3, "hf": 0.4} for i in range(6)])
    json.dumps(out)
    assert out["persist_pella_longest_run_0_2_0_6"]["value"] == 6
    assert shadow.compute_all(np.zeros(10), None)["noise_floor_dbfs"]["value"] is None
    assert "error" in shadow.compute_all("not audio")


def test_verdict_bit_identical_with_shadow_on_or_off(monkeypatch):
    wav, text = to_wav_bytes(make_call("tts", seed=3)), "Hello, this is a call about your appointment."
    on = pipeline.analyze(wav, text)
    assert on.egress["context"]["shadow"]["noise_floor_dbfs"]["value"] is not None
    assert all("shadow" not in t.name for t in on.tells)
    monkeypatch.setattr(pipeline.shadow, "compute_all", lambda *a, **k: {})
    off = pipeline.analyze(wav, text)
    for f in ("tier", "p_ai", "p_scam", "confidence", "signature", "thresholds_version", "disclosed_ai"):
        assert getattr(on, f) == getattr(off, f), f
    key = lambda v: [(t.name, t.score, t.weight, t.applicable) for t in v.tells]
    assert key(on) == key(off)
    d_on, d_off = on.to_dict(), off.to_dict()
    for k in ("scores", "quadrant", "reasons", "tells"):
        assert d_on[k] == d_off[k], k
