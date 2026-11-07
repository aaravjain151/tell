"""Acoustic tells — numpy only, runs on a laptop CPU in well under a second for a 30 s clip.

Every function returns a Tell with score in [0,1] *toward AI* and a plain-English evidence line.
These are behavioral/physiological cues (pauses, breaths, pitch wander, noise floor) rather than
codec-artifact cues, because phone lines strip everything above ~3.4 kHz and those artifacts with it.

Calibration constants live in doublespeak/thresholds.py. The maps below are linear ramps between the
"clearly human" and "clearly TTS" anchors; outside the anchors the score saturates at 0.1 / 0.9.
"""
from __future__ import annotations

import numpy as np

from .. import thresholds as T
from ..types import Tell

SR = 16_000
FRAME = int(0.025 * SR)   # 25 ms
HOP = int(0.010 * SR)     # 10 ms


def _ramp(x: float, human_anchor: float, tts_anchor: float) -> float:
    """Map x to [0.1, 0.9] toward AI. Works whether human_anchor > tts_anchor or the reverse."""
    if human_anchor == tts_anchor:
        return 0.5
    t = (x - human_anchor) / (tts_anchor - human_anchor)  # 0 at human, 1 at tts
    return float(0.1 + 0.8 * min(1.0, max(0.0, t)))


def frames(x: np.ndarray) -> np.ndarray:
    if len(x) < FRAME:
        x = np.pad(x, (0, FRAME - len(x)))
    n = 1 + (len(x) - FRAME) // HOP
    idx = np.arange(FRAME)[None, :] + HOP * np.arange(n)[:, None]
    return x[idx]


def frame_db(fr: np.ndarray) -> np.ndarray:
    rms = np.sqrt(np.mean(fr * fr, axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9)


def spectral_flatness(fr: np.ndarray) -> np.ndarray:
    """Flatness over 100 Hz–3.4 kHz only, so phone-band audio (zeros above 3.4 kHz) doesn't crush it."""
    spec = np.abs(np.fft.rfft(fr * np.hanning(fr.shape[1]), axis=1)) + 1e-9
    freqs = np.fft.rfftfreq(fr.shape[1], 1 / SR)
    band = (freqs >= 100) & (freqs <= 3400)
    spec = spec[:, band]
    return np.exp(np.mean(np.log(spec), axis=1)) / np.mean(spec, axis=1)


def band_limited(x: np.ndarray) -> tuple[bool, float]:
    """True when almost no energy sits above 4 kHz (phone-band audio or a <=8 kHz source)."""
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    total = np.sum(spec ** 2) + 1e-9
    hi = np.sum(spec[freqs > 4000] ** 2)
    ratio = float(hi / total)
    return ratio < T.BAND_LIMIT_RATIO, ratio


def segment(db: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Return (speech_mask, noise_floor_db, speech_threshold_db)."""
    floor = float(np.percentile(db, 10))
    peak = float(np.percentile(db, 95))
    thr = max(floor + 15.0, peak - 30.0)
    mask = db > thr
    # smooth: fill gaps < 60 ms, drop islands < 100 ms
    mask = _morph(mask, min_gap=6, min_run=10)
    return mask, floor, thr


def _morph(mask: np.ndarray, min_gap: int, min_run: int) -> np.ndarray:
    m = mask.copy()
    runs = _runs(m)
    for val, s, e in runs:
        if not val and e - s < min_gap and s > 0 and e < len(m):
            m[s:e] = True
    runs = _runs(m)
    for val, s, e in runs:
        if val and e - s < min_run:
            m[s:e] = False
    return m


def _runs(mask: np.ndarray) -> list[tuple[bool, int, int]]:
    out, start = [], 0
    for i in range(1, len(mask) + 1):
        if i == len(mask) or mask[i] != mask[start]:
            out.append((bool(mask[start]), start, i))
            start = i
    return out


def pauses_ms(mask: np.ndarray) -> list[float]:
    runs = _runs(mask)
    inner = runs[1:-1] if len(runs) > 2 else []
    return [10.0 * (e - s) for val, s, e in inner if not val and (e - s) * 10 >= 150]


# ---------------------------------------------------------------- tells

def pause_regularity(mask: np.ndarray) -> Tell:
    p = pauses_ms(mask)
    w = T.ACOUSTIC_WEIGHTS["pause_regularity"]
    if len(p) < 3:
        return Tell("pause_regularity", "acoustic", 0.5, w, f"only {len(p)} pauses found — need 3+", applicable=False)
    cv = float(np.std(p) / (np.mean(p) + 1e-9))
    score = _ramp(cv, T.PAUSE_CV_HUMAN, T.PAUSE_CV_TTS)
    desc = "metronomic" if cv < T.PAUSE_CV_TTS else ("varied" if cv > T.PAUSE_CV_HUMAN else "fairly even")
    return Tell("pause_regularity", "acoustic", score, w,
                f"{len(p)} pauses, lengths {desc} (CV {cv:.2f}; humans ≳{T.PAUSE_CV_HUMAN}, TTS ≲{T.PAUSE_CV_TTS})")


def breath_proxy(fr: np.ndarray, db: np.ndarray, mask: np.ndarray, floor: float, thr: float, dur_s: float) -> Tell:
    w = T.ACOUSTIC_WEIGHTS["breath_proxy"]
    if dur_s < T.BREATH_MIN_SECONDS:
        return Tell("breath_proxy", "acoustic", 0.5, w, f"clip too short for breath analysis ({dur_s:.1f}s < {T.BREATH_MIN_SECONDS:.0f}s)", applicable=False)
    flat = spectral_flatness(fr)
    onsets = [s for val, s, e in _runs(mask) if val]
    events = 0
    for s in onsets:
        lo, hi = max(0, s - 60), max(0, s - 3)  # 30–600 ms before onset (skip onset ramp/ringing)
        win_db, win_flat = db[lo:hi], flat[lo:hi]
        cand = (win_db > floor + 4) & (win_db < thr) & (win_flat > 0.35)
        if cand.sum() >= 10:  # ≥ 100 ms of noisy, low-level sound shortly before a phrase
            events += 1
    speech_s = max(1e-6, mask.sum() * 0.01)
    per10 = 10 * events / speech_s
    score = _ramp(per10, 1.2, 0.0)
    return Tell("breath_proxy", "acoustic", score, w,
                f"{events} breath-like events before phrases in {speech_s:.0f}s of speech"
                + (" — none at all" if events == 0 else ""))


def pitch_stability(fr: np.ndarray, mask: np.ndarray) -> Tell:
    w = T.ACOUSTIC_WEIGHTS["pitch_stability"]
    voiced = fr[mask]
    if len(voiced) < 50:
        return Tell("pitch_stability", "acoustic", 0.5, w, "not enough voiced frames", applicable=False)
    f0s = []
    lag_min, lag_max = SR // 400, SR // 70
    for f in voiced[::2]:
        f = f - f.mean()
        if np.sum(f * f) < 1e-6:
            continue
        ac = np.correlate(f, f, mode="full")[len(f) - 1:]
        ac = ac / (ac[0] + 1e-9)
        seg = ac[lag_min:lag_max]
        if len(seg) == 0:
            continue
        k = int(np.argmax(seg))
        if seg[k] > 0.5:
            f0s.append(SR / (lag_min + k))
    if len(f0s) < 30:
        return Tell("pitch_stability", "acoustic", 0.5, w, "pitch not trackable (noisy or unvoiced)", applicable=False)
    f0 = np.array(f0s)
    f0 = f0[(f0 > np.percentile(f0, 5)) & (f0 < np.percentile(f0, 95))]
    cv = float(np.std(f0) / (np.mean(f0) + 1e-9))
    score = _ramp(cv, T.F0_CV_HUMAN, T.F0_CV_TTS)
    desc = "unusually steady" if cv < T.F0_CV_TTS else ("natural wander" if cv > T.F0_CV_HUMAN else "moderate")
    return Tell("pitch_stability", "acoustic", score, w,
                f"pitch {desc} (F0 ≈ {np.mean(f0):.0f} Hz, variability {cv:.2f})")


def noise_floor(db: np.ndarray, mask: np.ndarray, floor: float) -> Tell:
    w = T.ACOUSTIC_WEIGHTS["noise_floor"]
    quiet = db[~mask]
    if len(quiet) < 20:
        return Tell("noise_floor", "acoustic", 0.5, w, "no silent stretches to measure", applicable=False)
    stationarity = float(np.std(quiet))
    score_level = _ramp(floor, T.NOISE_FLOOR_DB_HUMAN, T.NOISE_FLOOR_DB_TTS)
    score_stat = _ramp(stationarity, 3.0, 0.5)
    score = 0.6 * score_level + 0.4 * score_stat
    desc = "digital silence" if floor < T.NOISE_FLOOR_DB_TTS else ("room/line noise present" if floor > T.NOISE_FLOOR_DB_HUMAN else "very quiet background")
    return Tell("noise_floor", "acoustic", score, w,
                f"background is {desc} ({floor:.0f} dBFS, varies ±{stationarity:.1f} dB)")


def analyze(x: np.ndarray, dur_ms: int) -> tuple[list[Tell], dict]:
    """Run all acoustic tells. Returns (tells, context) where context has band_limited etc."""
    dur_s = dur_ms / 1000
    ctx: dict = {"duration_s": round(dur_s, 2)}
    if dur_s < T.MIN_AUDIO_SECONDS:
        ctx["too_short"] = True
        return [Tell("acoustic", "acoustic", 0.5, 1.0, f"clip too short ({dur_s:.1f}s < {T.MIN_AUDIO_SECONDS:.0f}s) — acoustic tells skipped", applicable=False)], ctx
    bl, ratio = band_limited(x)
    ctx["band_limited"] = bl
    ctx["high_band_ratio"] = round(ratio, 4)
    fr = frames(x)
    db = frame_db(fr)
    mask, floor, thr = segment(db)
    ctx["speech_ratio"] = round(float(mask.mean()), 3)
    tells = [
        pause_regularity(mask),
        breath_proxy(fr, db, mask, floor, thr, dur_s),
        pitch_stability(fr, mask),
        noise_floor(db, mask, floor),
    ]
    if bl:
        tells.append(Tell("band_limited", "acoustic", 0.5, 0.0,
                          "phone-band audio (no content above 4 kHz) — spectral tells disabled, behavioral tells only",
                          applicable=False))
    return tells, ctx
