"""SHADOW layers: computed and logged, never used.

Nothing here feeds p_ai, p_scam, tier, confidence, scores, quadrant, the stabiliser or the signature. The pipeline stores the
result under egress.context["shadow"] AFTER scorer.fuse() and outside the signed payload, exactly like Tell.detail. They exist
so we can measure, on real recordings, whether any of them is worth promoting later. With one human speaker and a handful of
clips, no number produced here supports a claim of generalisation.

Every feature is a pure numpy function of 16 kHz mono float PCM and returns (value, evidence). value is NaN when the window is
too short or too uniform to say anything; compute_all() turns NaN into None.
"""
from __future__ import annotations

import math

import numpy as np

SR = 16_000
FRAME = 320          # 20 ms
HOP = 160            # 10 ms
DB_FLOOR = -120.0    # exact digital silence reads as this, not -inf
NAN = float("nan")

Feat = tuple[float, str]


def _frame_db(x: np.ndarray, frame: int = FRAME, hop: int = HOP) -> np.ndarray:
    """Per-frame RMS in dBFS (full scale = 1.0)."""
    x = np.asarray(x, dtype=np.float64)
    if x.size < frame:
        return np.empty(0)
    n = 1 + (x.size - frame) // hop
    idx = np.arange(frame)[None, :] + hop * np.arange(n)[:, None]
    rms = np.sqrt(np.mean(x[idx] ** 2, axis=1))
    return np.maximum(20 * np.log10(np.maximum(rms, 1e-12)), DB_FLOOR)


def _welch_db(x: np.ndarray, nfft: int = 512) -> tuple[np.ndarray, np.ndarray]:
    """Long-term average power spectrum (Hann, 50% overlap) as (freqs, power). Empty if the signal is shorter than nfft."""
    x = np.asarray(x, dtype=np.float64)
    if x.size < nfft:
        return np.empty(0), np.empty(0)
    w = np.hanning(nfft)
    hop = nfft // 2
    n = 1 + (x.size - nfft) // hop
    idx = np.arange(nfft)[None, :] + hop * np.arange(n)[:, None]
    p = np.mean(np.abs(np.fft.rfft(x[idx] * w, axis=1)) ** 2, axis=0)
    return np.fft.rfftfreq(nfft, 1 / SR), p


# (a) noise floor ----------------------------------------------------------------------------------------------------
def noise_floor_dbfs(x: np.ndarray) -> Feat:
    """10th percentile of 20 ms frame RMS, dBFS. Lower = a cleaner floor than most rooms or phone lines have."""
    db = _frame_db(x)
    if db.size < 20:
        return NAN, "window too short for a floor estimate"
    v = float(np.percentile(db, 10))
    return v, f"10th percentile frame level {v:.1f} dBFS over {db.size} frames"


def noise_floor_variability_db(x: np.ndarray) -> Feat:
    """Std (dB) of the per-second 10th-percentile level across the window. Near 0 = a steady or absent floor."""
    db = _frame_db(x)
    seg = 100                                   # 1 s of 10 ms hops
    k = db.size // seg
    if k < 3:
        return NAN, "need >= 3 s for floor variability"
    floors = [float(np.percentile(db[i * seg:(i + 1) * seg], 10)) for i in range(k)]
    v = float(np.std(floors))
    return v, f"floor std {v:.1f} dB across {k} one-second segments"


# (b) digital zero and gating ----------------------------------------------------------------------------------------
def digital_zero_run_ms(x: np.ndarray) -> Feat:
    """Longest run of exactly-zero samples, ms. Real microphones are never exactly 0 for long; gated or padded TTS can be."""
    x = np.asarray(x)
    if x.size == 0:
        return NAN, "empty window"
    z = np.concatenate(([0], (x == 0).astype(np.int8), [0]))
    d = np.diff(z)
    starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
    longest = int((ends - starts).max()) if starts.size else 0
    frac = float(np.mean(x == 0))
    ms = 1000.0 * longest / SR
    return ms, f"longest exact-zero run {ms:.0f} ms; {100 * frac:.2f}% of samples exactly 0"


def gate_transitions_per_min(x: np.ndarray) -> Feat:
    """Hard gate events per minute: the level falls >= 25 dB between adjacent 10 ms frames and lands <= -75 dBFS (or digital zero)."""
    db = _frame_db(x, FRAME, HOP)
    if db.size < 50:
        return NAN, "window too short for gate transitions"
    drop = (db[:-1] - db[1:]) >= 25.0
    land = db[1:] <= -75.0
    n = int(np.sum(drop & land))
    minutes = (db.size * HOP / SR) / 60.0
    return n / minutes, f"{n} hard gate transition(s) in {minutes * 60:.1f} s"


# (c) modulation spectrum --------------------------------------------------------------------------------------------
def modulation_4_16_ratio(x: np.ndarray) -> Feat:
    """Share of envelope-fluctuation energy (0.5-50 Hz) that sits at 4-16 Hz, the syllable rate. 1.0 = pure syllabic rhythm."""
    x = np.asarray(x, dtype=np.float64)
    hop = 160
    if x.size < SR * 2:
        return NAN, "need >= 2 s for a modulation spectrum"
    n = x.size // hop
    env = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1))   # 100 Hz envelope
    env = env - env.mean()
    spec = np.abs(np.fft.rfft(env * np.hanning(env.size))) ** 2
    f = np.fft.rfftfreq(env.size, d=hop / SR)
    total = spec[(f >= 0.5) & (f <= 50)].sum()
    if total <= 1e-18:
        return NAN, "flat envelope"
    v = float(spec[(f >= 4) & (f <= 16)].sum() / total)
    return v, f"{100 * v:.0f}% of envelope modulation energy at 4-16 Hz"


# (d) long-term spectral flatness ------------------------------------------------------------------------------------
def spectral_flatness_300_3400(x: np.ndarray) -> Feat:
    """Geometric / arithmetic mean of the long-term power spectrum in 300-3400 Hz. 1 = white, near 0 = peaky or tonal."""
    f, p = _welch_db(x)
    if f.size == 0:
        return NAN, "window too short"
    m = (f >= 300) & (f <= 3400)
    q = p[m] + 1e-20
    v = float(np.exp(np.mean(np.log(q))) / np.mean(q))
    return v, f"long-term flatness {v:.3f} in 300-3400 Hz"


# (e) loudness consistency -------------------------------------------------------------------------------------------
def loudness_consistency_db(x: np.ndarray) -> Feat:
    """Std (dB) of mean level across consecutive utterances split at pauses. LUFS-like: unweighted, no gating blocks."""
    db = _frame_db(x)
    if db.size < 100:
        return NAN, "window too short"
    thr = max(np.percentile(db, 10) + 10.0, np.percentile(db, 95) - 30.0)
    act = db >= thr
    levels, i, n = [], 0, act.size
    while i < n:
        if not act[i]:
            i += 1
            continue
        j = i
        gap = 0
        end = i
        while j < n and gap < 15:               # a pause of >= 150 ms ends the utterance
            if act[j]:
                gap, end = 0, j
            else:
                gap += 1
            j += 1
        if end - i + 1 >= 30:                   # >= 300 ms of material
            seg = db[i:end + 1]
            seg = seg[seg >= thr]
            levels.append(10 * np.log10(np.mean(10 ** (seg / 10))))
        i = end + 1
    if len(levels) < 3:
        return NAN, f"only {len(levels)} utterance(s); need >= 3"
    v = float(np.std(levels))
    return v, f"level std {v:.1f} dB across {len(levels)} utterances"


# (f) call-level persistence -----------------------------------------------------------------------------------------
def persistence(scores: list[float] | None) -> dict[str, Feat]:
    """From per-window neural scores over a call: mean, min, fraction > 0.5, longest run (windows) inside the 0.2-0.6 band.
    The band is the failure we saw: an AI voice scored 0.24-0.47 for a whole call."""
    s = [float(v) for v in (scores or []) if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if len(s) < 3:
        return {k: (NAN, "need >= 3 scored windows") for k in ("mean", "min", "frac_gt_0_5", "longest_run_0_2_0_6")}
    a = np.asarray(s)
    best = cur = 0
    for v in a:
        cur = cur + 1 if 0.2 <= v <= 0.6 else 0
        best = max(best, cur)
    return {
        "mean": (float(a.mean()), f"mean window score {a.mean():.2f} over {a.size} windows"),
        "min": (float(a.min()), f"lowest window score {a.min():.2f}"),
        "frac_gt_0_5": (float(np.mean(a > 0.5)), f"{100 * np.mean(a > 0.5):.0f}% of windows above 0.5"),
        "longest_run_0_2_0_6": (float(best), f"longest run in the 0.2-0.6 band: {best} window(s)"),
    }


# (g) channel descriptors --------------------------------------------------------------------------------------------
def bandwidth_hz(x: np.ndarray) -> Feat:
    """Highest frequency whose smoothed long-term power is >= 6 dB above the spectrum's 5th percentile and within 50 dB of its
    90th percentile. ~3400-4000 = phone band. A flat spectrum reads as Nyquist."""
    f, p = _welch_db(x)
    if f.size == 0:
        return NAN, "window too short"
    db = 10 * np.log10(np.convolve(p + 1e-20, np.ones(3) / 3, mode="same"))
    if np.percentile(db, 50) - np.percentile(db, 5) < 3.0:      # flat spectrum: energy all the way to Nyquist
        return float(f[-1]), f"flat spectrum, energy up to Nyquist ({f[-1]:.0f} Hz)"
    thr = max(np.percentile(db, 5) + 6.0, np.percentile(db, 90) - 50.0)   # above the floor AND within 50 dB of the passband
    above = np.where(db > thr)[0]
    v = float(f[above.max()]) if above.size else 0.0
    return v, f"energy up to about {v:.0f} Hz"


def snr_db(x: np.ndarray) -> Feat:
    """Rough SNR: mean power of the loudest 30% of frames over the 10th-percentile frame power. Clipped to 0-90 dB."""
    db = _frame_db(x)
    if db.size < 20:
        return NAN, "window too short"
    pw = 10 ** (db / 10)
    top = pw[db >= np.percentile(db, 70)].mean()
    noise = max(10 ** (np.percentile(db, 10) / 10), 1e-12)
    v = float(np.clip(10 * np.log10(top / noise), 0.0, 90.0))
    return v, f"signal-to-floor about {v:.0f} dB"


# (h) Qwen3-TTS cues (docs/QWEN-CUES.md) -- paired against one real speaker, same scripts. SHADOW only. ----------------
def _speech_mask(db: np.ndarray) -> np.ndarray:
    """Boolean speech mask over 10 ms hops: above max(p10 + 8, p95 - 35) dB, gaps < 120 ms filled, blips < 80 ms dropped."""
    thr = max(np.percentile(db, 10) + 8.0, np.percentile(db, 95) - 35.0)
    m = db >= thr

    def runs(b):
        d = np.diff(np.concatenate(([0], b.astype(np.int8), [0])))
        return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))
    for s, e in runs(~m):
        if e - s < 12 and s > 0 and e < m.size:
            m[s:e] = True
    for s, e in runs(m):
        if e - s < 8:
            m[s:e] = False
    return m


def _runs(b: np.ndarray) -> list[tuple[int, int]]:
    d = np.diff(np.concatenate(([0], b.astype(np.int8), [0])))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def cepstral_peak_prominence_db(x: np.ndarray) -> Feat:
    """Median cepstral peak prominence (dB) over active 40 ms frames, 100-3400 Hz. High = very regular, noise-free voicing.
    Qwen3-TTS read ~3 dB higher than the same speaker's real recordings (Praat CPPS; this is a simpler cousin)."""
    x = np.asarray(x, dtype=np.float64)
    n_f = 640
    if x.size < SR * 2:
        return NAN, "need >= 2 s for cepstral prominence"
    db = _frame_db(x, FRAME, HOP)
    thr = np.percentile(db, 95) - 25.0
    n = 1 + (x.size - n_f) // HOP
    idx = np.arange(n_f)[None, :] + HOP * np.arange(n)[:, None]
    keep = np.where(db[:n] >= thr)[0] if db.size >= n else np.where(db >= thr)[0]
    keep = keep[keep < n][::2]
    if keep.size < 20:
        return NAN, "too few active frames"
    sp = np.abs(np.fft.rfft(x[idx[keep]] * np.hanning(n_f), n=1024, axis=1)) + 1e-9
    f = np.fft.rfftfreq(1024, 1 / SR)
    band = (f >= 100) & (f <= 3400)
    ls = 20 * np.log10(sp[:, band])
    ceps = 20 * np.log10(np.abs(np.fft.rfft(ls - ls.mean(axis=1, keepdims=True), n=2048, axis=1)) + 1e-9)
    df_ = f[1] - f[0]
    q = np.arange(ceps.shape[1]) / (2048 * df_)                     # quefrency, seconds
    lo, hi = np.searchsorted(q, 1 / 400), np.searchsorted(q, 1 / 70)
    reg = (q >= 0.001) & (q <= 0.016)
    out = []
    for c in ceps:
        a, b = np.polyfit(q[reg], c[reg], 1)
        pk = lo + int(np.argmax(c[lo:hi]))
        out.append(c[pk] - (a * q[pk] + b))
    v = float(np.median(out))
    return v, f"median cepstral peak prominence {v:.1f} dB over {keep.size} frames"


def onset_sharpness_db(x: np.ndarray) -> Feat:
    """Median largest 10 ms level rise (dB) at speech onsets that follow a >= 120 ms gap. Real mouths and rooms ramp in; Qwen3-TTS
    starts words ~2x more abruptly (about 20 vs 9 dB / 10 ms in our pairs)."""
    db = _frame_db(x, FRAME, HOP)
    if db.size < 300:
        return NAN, "window too short"
    m = _speech_mask(db)
    rises = []
    for s, e in _runs(m):
        if e - s >= 15 and s >= 12:
            seg = db[max(s - 2, 0):s + 8]
            rises.append(float(np.max(np.diff(seg))))
    if len(rises) < 3:
        return NAN, f"only {len(rises)} onset(s); need >= 3"
    v = float(np.median(rises))
    return v, f"median onset rise {v:.1f} dB per 10 ms over {len(rises)} onsets"


def _f0_track_st(x: np.ndarray) -> np.ndarray:
    """Crude numpy autocorrelation F0 (70-400 Hz, 40 ms frames, 10 ms hop) in semitones re 100 Hz; NaN where unvoiced."""
    x = np.asarray(x, dtype=np.float64)
    n_f = 640
    n = 1 + (x.size - n_f) // HOP
    if n < 20:
        return np.empty(0)
    idx = np.arange(n_f)[None, :] + HOP * np.arange(n)[:, None]
    fr = x[idx] * np.hanning(n_f)
    fr -= fr.mean(axis=1, keepdims=True)
    ac = np.fft.irfft(np.abs(np.fft.rfft(fr, n=2048, axis=1)) ** 2, axis=1)
    ac = ac / (ac[:, :1] + 1e-12)
    lo, hi = int(SR / 400), int(SR / 70)
    seg = ac[:, lo:hi]
    k = np.argmax(seg, axis=1)
    pk = seg[np.arange(n), k]
    db = _frame_db(x, FRAME, HOP)[:n]
    ok = (pk > 0.5) & (db >= np.percentile(db, 95) - 30.0)
    f0 = SR / (lo + k.astype(float))
    return np.where(ok, 12 * np.log2(f0 / 100.0), np.nan)


def f0_rate_st_per_s(x: np.ndarray) -> Feat:
    """Mean |F0 change| in semitones per second between adjacent voiced 10 ms frames (jumps > 3 st dropped). Qwen3-TTS pitch moves
    more slowly (about 25 vs 31 st/s on the same speaker and scripts)."""
    s = _f0_track_st(x)
    if s.size < 100 or np.isfinite(s).sum() < 100:
        return NAN, "too little voiced speech"
    d = np.diff(s)
    d = d[np.isfinite(d)]
    d = d[np.abs(d) < 3.0]
    if d.size < 50:
        return NAN, "too few adjacent voiced frames"
    v = float(np.mean(np.abs(d)) / 0.01)
    return v, f"mean pitch movement {v:.1f} semitones/s over {d.size} frame pairs"


def long_pause_per_min(x: np.ndarray) -> Feat:
    """Pauses of >= 300 ms inside the speech span, per minute of that span. Same speaker read the same scripts with ~2-3x as many
    long pauses as Qwen3-TTS. Depends on the noise floor (the speech mask is relative), so a channel property as much as a style one."""
    db = _frame_db(x, FRAME, HOP)
    if db.size < 500:
        return NAN, "need >= 5 s"
    m = _speech_mask(db)
    r = _runs(m)
    if len(r) < 4:
        return NAN, "too few speech runs"
    span = (r[-1][1] - r[0][0]) * 0.01
    gaps = [(r[i + 1][0] - r[i][1]) * 10 for i in range(len(r) - 1)]
    n = sum(g >= 300 for g in gaps)
    v = 60.0 * n / span
    return v, f"{n} pause(s) >= 300 ms in {span:.1f} s of speech span"


def lowmid_balance_db(x: np.ndarray) -> Feat:
    """10*log10 of energy in 500-1000 Hz over 100-500 Hz, active frames. A long-term spectral shape of the voice plus the mic: probably
    mostly recorder (Qwen sits ~5 dB higher than the real recording of the same voice). Logged to see if it replicates."""
    x = np.asarray(x, dtype=np.float64)
    db = _frame_db(x, FRAME, HOP)
    if db.size < 300:
        return NAN, "window too short"
    n = db.size
    idx = np.arange(FRAME)[None, :] + HOP * np.arange(n)[:, None]
    act = np.where(db >= np.percentile(db, 95) - 20.0)[0]
    if act.size < 50:
        return NAN, "too few active frames"
    p = np.mean(np.abs(np.fft.rfft(x[idx[act]] * np.hanning(FRAME), n=512, axis=1)) ** 2, axis=0)
    f = np.fft.rfftfreq(512, 1 / SR)
    v = float(10 * np.log10(p[(f >= 500) & (f < 1000)].sum() / (p[(f >= 100) & (f < 500)].sum() + 1e-20) + 1e-20))
    return v, f"500-1000 Hz is {v:+.1f} dB relative to 100-500 Hz"


FEATURES = {
    "noise_floor_dbfs": noise_floor_dbfs,
    "noise_floor_std_db": noise_floor_variability_db,
    "digital_zero_run_ms": digital_zero_run_ms,
    "gate_transitions_per_min": gate_transitions_per_min,
    "modulation_4_16_ratio": modulation_4_16_ratio,
    "spectral_flatness_300_3400": spectral_flatness_300_3400,
    "loudness_std_db": loudness_consistency_db,
    "bandwidth_hz": bandwidth_hz,
    "snr_db": snr_db,
    "qwen_cpp_db": cepstral_peak_prominence_db,
    "qwen_onset_sharpness_db": onset_sharpness_db,
    "qwen_f0_rate_st_s": f0_rate_st_per_s,
    "qwen_long_pause_per_min": long_pause_per_min,
    "qwen_lowmid_balance_db": lowmid_balance_db,
}


def _pack(v: float, ev: str) -> dict:
    ok = isinstance(v, float) and math.isfinite(v)
    return {"value": round(v, 4) if ok else None, "evidence": ev}


def compute_all(x: np.ndarray, voice_windows: list[dict] | None = None) -> dict:
    """{feature: {"value": float|None, "evidence": str}}. `voice_windows` is pipeline.voice_windows() output
    ([{"t":..,"pella":..,"hf":..}]); persistence is computed per voter. Never raises."""
    out: dict = {}
    try:
        x = np.asarray(x, dtype=np.float32)
        for name, fn in FEATURES.items():
            out[name] = _pack(*fn(x))
        for voter in ("pella", "hf"):
            sc = [w[voter] for w in (voice_windows or []) if voter in w]
            for k, (v, ev) in persistence(sc).items():
                out[f"persist_{voter}_{k}"] = _pack(v, ev)
    except Exception as e:  # shadow must never break an analysis
        out["error"] = {"value": None, "evidence": f"shadow failed: {type(e).__name__}"}
    return out
