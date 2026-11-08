"""Shadow layers: mechanics on synthetic signals, and proof they cannot change a verdict."""
from __future__ import annotations

import json
import math

import numpy as np

from tell import pipeline
from tell.signals import shadow
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


def test_live_tick_gets_call_persistence_and_stable_is_unchanged(monkeypatch):
    from tell import live

    def tick(i):
        return {"tier": "human", "p_ai": 0.3, "p_scam": 0.0, "confidence": 0.5, "disclosed_ai": False, "tells": [],
                "transcript": "hello there", "reasons": [],
                "egress": {"context": {"voice_windows": [{"t": 0.0, "pella": 0.3 + 0.01 * i, "hf": 0.4}]}}}

    def run():
        tr, outs, ds = live.StableTracker(), [], []
        for i in range(5):
            d = tick(i)
            outs.append(tr.observe(d, 3.0 * i, 3.0 * i + 3.0))
            ds.append(d)
        return outs, ds

    outs_on, ds = run()
    sh = ds[-1]["egress"]["context"]["shadow"]
    assert sh["call_persist_pella_longest_run_0_2_0_6"]["value"] == 5
    assert sh["call_persist_hf_frac_gt_0_5"]["value"] == 0.0

    def boom(_):
        raise RuntimeError("shadow off")
    monkeypatch.setattr(live.shadow, "persistence", boom)
    outs_off, ds_off = run()
    assert outs_on == outs_off                                  # the displayed stable answer cannot depend on shadow
    assert "shadow" not in ds_off[-1]["egress"]["context"] or not ds_off[-1]["egress"]["context"]["shadow"]


# --- Qwen3-TTS cue layers (docs/QWEN-CUES.md): mechanics on synthetic signals only -------------------------------------
def _voiced(sec=6.0, f0=120.0, vib_hz=0.0, vib_st=0.0, noise=0.0, seed=0, nh=25):
    """Harmonic 'voice' at f0 with optional vibrato (semitones) and additive noise relative to the voice RMS."""
    t = np.arange(int(sec * SR)) / SR
    f = f0 * 2 ** (vib_st * np.sin(2 * np.pi * vib_hz * t) / 12)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = sum(np.sin(k * ph) / k for k in range(1, nh + 1))
    x = 0.2 * x / np.sqrt(np.mean(x ** 2)) * (1 + 0.3 * np.sin(2 * np.pi * 4 * t))
    return (x + noise * 0.2 * np.random.default_rng(seed).normal(0, 1, t.size)).astype(np.float32)


def test_qwen_cpp_clean_harmonics_beat_noisy_ones():
    clean, noisy = _voiced(noise=0.0), _voiced(noise=1.5)
    c, n = shadow.cepstral_peak_prominence_db(clean)[0], shadow.cepstral_peak_prominence_db(noisy)[0]
    assert c > n + 3.0
    assert math.isnan(shadow.cepstral_peak_prominence_db(_voiced(sec=1.0))[0])


def test_qwen_onset_sharpness_abrupt_vs_ramped():
    sec, per, on = 12.0, 1.5, 0.9
    t = np.arange(int(sec * SR)) / SR
    ph = t % per
    carrier = np.sin(2 * np.pi * 220 * t) + 0.4 * np.sin(2 * np.pi * 440 * t)
    abrupt = (ph < on).astype(float)
    ramp_db = np.clip(-50 + 50 * ph / 0.6, -50, 0)                     # 50 dB over 600 ms, about 8 dB per 10 ms
    ramped = np.where(ph < on, 10 ** (ramp_db / 20), 0.0)
    rng = np.random.default_rng(0)
    mk = lambda env: (0.2 * env * carrier + rng.normal(0, 0.0005, t.size)).astype(np.float32)
    a, r = shadow.onset_sharpness_db(mk(abrupt))[0], shadow.onset_sharpness_db(mk(ramped))[0]
    assert a > r + 8.0
    assert math.isnan(shadow.onset_sharpness_db(mk(abrupt)[: SR])[0])


def test_qwen_f0_rate_fast_vs_slow_pitch_movement():
    fast = shadow.f0_rate_st_per_s(_voiced(vib_hz=4.0, vib_st=2.0))[0]
    slow = shadow.f0_rate_st_per_s(_voiced(vib_hz=0.4, vib_st=2.0))[0]
    flat = shadow.f0_rate_st_per_s(_voiced())[0]
    assert fast > 3 * slow > 0 and flat < slow
    assert math.isnan(shadow.f0_rate_st_per_s(_noise(3, 0.1))[0])


def test_qwen_long_pause_rate():
    def talk(gap):
        t = np.arange(int(0.9 * SR)) / SR
        seg = (0.2 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
        z = np.random.default_rng(1).normal(0, 1e-4, int(gap * SR)).astype(np.float32)
        return np.concatenate([seg, z] * 8)
    assert shadow.long_pause_per_min(talk(0.6))[0] > 20
    assert shadow.long_pause_per_min(talk(0.2))[0] == 0
    assert math.isnan(shadow.long_pause_per_min(_noise(2, 0.01))[0])


def test_qwen_lowmid_balance_tracks_spectral_tilt():
    t = np.arange(4 * SR) / SR
    low = (0.2 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    mid = (0.2 * np.sin(2 * np.pi * 700 * t)).astype(np.float32)
    assert shadow.lowmid_balance_db(mid)[0] > shadow.lowmid_balance_db(low)[0] + 15
    assert math.isnan(shadow.lowmid_balance_db(low[:2000])[0])


def test_qwen_cues_are_logged_and_json_safe():
    out = shadow.compute_all(_voiced(sec=8.0), None)
    json.dumps(out)
    for k in ("qwen_cpp_db", "qwen_onset_sharpness_db", "qwen_f0_rate_st_s", "qwen_long_pause_per_min", "qwen_lowmid_balance_db"):
        assert k in out and "evidence" in out[k]
    assert out["qwen_cpp_db"]["value"] is not None
