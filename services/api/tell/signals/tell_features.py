"""Interpretable voice tells per 4 s window: numpy only, no models, no I/O. Used by signals/learned.py (the learned_tells
voter) and by the offline study that fitted its weights (training/learned_tells/, docs/LEARNED-TELLS.md), so training and
inference run the SAME code.

window_features(x) -> {name: float}; NaN when the window cannot say anything (too little voicing, no pause, ...). The model
imputes NaN with the training median, so a missing feature votes neither way.

Why these: modern TTS is a codec language model plus a neural vocoder (or flow matching). What that tends to leave in the
waveform, and what we measure for it:
  * voicing that is too regular  -> HNR, cepstral peak prominence, jitter/shimmer proxies, harmonic-valley depth, how exactly
    harmonic the partials are (instantaneous-frequency deviation), group-delay spread (vocoder phase);
  * prosody that is too smooth   -> F0 spread/range/rate, micro-prosody residual, F0-loudness coupling, envelope roughness;
  * pauses that are too clean    -> pause depth, pause noise texture (flatness, level wobble), pause share;
  * the channel                  -> noise floor, SNR, 4-8 kHz vs 1-4 kHz, exact digital zeros (recorder/line, NOT voice: they are
    kept so the study can show how much of a separation is channel, see CHANNEL_FEATURES).
"""
from __future__ import annotations

import math

import numpy as np

SR = 16_000
NF, HOP, NFFT = 640, 160, 1024          # 40 ms frames, 10 ms hop
NAN = float("nan")

FEATURE_NAMES = [
    "f0_std_st", "f0_range_st", "f0_rate_st_s", "f0_micro_st", "jitter_pct", "shimmer_db", "f0_energy_corr",
    "hnr_db", "cpp_db", "harm_valley_db", "harm_if_dev", "group_delay_ms",
    "env_roughness_db", "mod_4_16", "spectral_flux", "spectral_tilt_db", "lowmid_balance_db", "speech_flatness",
    "pause_share", "max_gap_ms", "pause_depth_db", "pause_flatness", "pause_wobble_db", "breath_rate",
    "noise_floor_dbfs", "snr_db", "hi_band_rel_db", "digital_zero_frac",
]
CHANNEL_FEATURES = {"noise_floor_dbfs", "snr_db", "hi_band_rel_db", "digital_zero_frac"}


def _frames(x: np.ndarray, n: int = NF, hop: int = HOP) -> np.ndarray:
    if x.size < n:
        x = np.pad(x, (0, n - x.size))
    k = 1 + (x.size - n) // hop
    return x[np.arange(n)[None, :] + hop * np.arange(k)[:, None]]


def _runs(b: np.ndarray) -> list[tuple[int, int]]:
    d = np.diff(np.concatenate(([0], b.astype(np.int8), [0])))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def _nanmed(a) -> float:
    a = np.asarray(a, dtype=np.float64)
    a = a[np.isfinite(a)]
    return float(np.median(a)) if a.size else NAN


def band_ratio_db(x: np.ndarray, lo=(1000.0, 4000.0), hi=(4000.0, 8000.0)) -> float:
    """10*log10(energy in `hi` / energy in `lo`) of the long-term spectrum. About -10 to -25 dB for wideband speech, below
    about -40 dB once a phone codec (8 kHz sampling) has removed everything above 4 kHz."""
    x = np.asarray(x, dtype=np.float64)
    if x.size < 512:
        return NAN
    fr = _frames(x, 512, 256) * np.hanning(512)
    p = np.mean(np.abs(np.fft.rfft(fr, axis=1)) ** 2, axis=0)
    f = np.fft.rfftfreq(512, 1 / SR)
    a = p[(f >= lo[0]) & (f < lo[1])].sum()
    b = p[(f >= hi[0]) & (f < hi[1])].sum()
    return float(10 * np.log10((b + 1e-20) / (a + 1e-20)))


def window_features(x: np.ndarray) -> dict[str, float]:
    """All tells for one window (ideally 4 s of 16 kHz mono float in [-1, 1]). Never raises; NaN for what it cannot measure."""
    out = {n: NAN for n in FEATURE_NAMES}
    try:
        _compute(np.asarray(x, dtype=np.float64), out)
    except Exception:  # noqa: BLE001 - a feature must never break an analysis
        pass
    return out


def _compute(x: np.ndarray, out: dict) -> None:
    if x.size < SR:                                     # < 1 s: nothing reliable
        return
    out["digital_zero_frac"] = float(np.mean(x == 0))
    out["hi_band_rel_db"] = band_ratio_db(x)
    x = x - x.mean()
    fr = _frames(x)
    nfr = fr.shape[0]
    rms = np.sqrt(np.mean(fr ** 2, axis=1))
    db = np.maximum(20 * np.log10(np.maximum(rms, 1e-12)), -120.0)
    p95, p10 = np.percentile(db, 95), np.percentile(db, 10)
    out["noise_floor_dbfs"] = float(p10)
    thr = max(p10 + 8.0, p95 - 35.0)
    sp = db >= thr
    for s, e in _runs(~sp):                              # fill < 120 ms gaps, drop < 80 ms blips
        if e - s < 12 and s > 0 and e < nfr:
            sp[s:e] = True
    for s, e in _runs(sp):
        if e - s < 8:
            sp[s:e] = False
    if sp.sum() < 30:                                    # < 0.3 s of speech: leave everything NaN except the channel bits
        return
    pw = 10 ** (db / 10)
    out["snr_db"] = float(np.clip(10 * np.log10(pw[db >= np.percentile(db, 70)].mean() / max(10 ** (p10 / 10), 1e-12)), 0, 90))

    win = np.hanning(NF)
    X = np.fft.rfft(fr * win, n=NFFT, axis=1)
    mag = np.abs(X) + 1e-12
    f = np.fft.rfftfreq(NFFT, 1 / SR)
    band = (f >= 100) & (f <= 3400)
    lsd = 20 * np.log10(mag)

    # ---- F0 by normalised autocorrelation (70-400 Hz)
    frw = fr * win
    ac = np.fft.irfft(np.abs(np.fft.rfft(frw, n=2048, axis=1)) ** 2, axis=1)
    ac = ac / (ac[:, :1] + 1e-12)
    lo, hi = int(SR / 400), int(SR / 70)
    seg = ac[:, lo:hi]
    k = np.argmax(seg, axis=1)
    r = seg[np.arange(nfr), k]
    voiced = (r > 0.5) & sp & (db >= p95 - 30.0)
    period = (lo + k).astype(np.float64)
    f0 = SR / period
    st = 12 * np.log2(f0 / 100.0)
    if voiced.sum() >= 20:
        v = st[voiced]
        out["f0_std_st"] = float(np.std(v))
        out["f0_range_st"] = float(np.percentile(v, 95) - np.percentile(v, 5))
        both = voiced[1:] & voiced[:-1]
        d = np.diff(st)[both]
        d = d[np.abs(d) < 3.0]
        if d.size >= 10:
            out["f0_rate_st_s"] = float(np.mean(np.abs(d)) / 0.01)
        dp = np.abs(np.diff(period))[both] / period[1:][both]
        dp = dp[np.abs(np.diff(st)[both]) < 1.0]
        if dp.size >= 10:
            out["jitter_pct"] = float(100 * np.mean(dp))
        dd = np.abs(np.diff(db))[both]
        if dd.size >= 10:
            out["shimmer_db"] = float(np.median(dd))
        res = []
        for s, e in _runs(voiced):
            if e - s >= 7:
                seg_st = st[s:e]
                sm = np.convolve(np.pad(seg_st, 2, mode="edge"), np.ones(5) / 5, mode="valid")
                res.extend((seg_st - sm).tolist())
        if len(res) >= 20:
            out["f0_micro_st"] = float(np.std(res))
        if np.std(db[voiced]) > 1e-6 and np.std(v) > 1e-6:
            out["f0_energy_corr"] = float(np.corrcoef(v, db[voiced])[0, 1])
        rr = np.clip(r[voiced], 1e-4, 1 - 1e-4)
        out["hnr_db"] = float(np.median(10 * np.log10(rr / (1 - rr))))

        # ---- harmonic structure on voiced frames (subsample for speed)
        idx = np.where(voiced)[0][::2]
        valley, ifdev, gd = [], [], []
        n = np.arange(NF)
        Xn = np.fft.rfft(fr[idx] * win * n, n=NFFT, axis=1)        # for group delay
        # second analysis 1 ms later for instantaneous frequency
        d_s = 16
        fr2 = _frames(np.pad(x, (0, d_s))[d_s:])[: nfr][idx]
        X2 = np.fft.rfft(fr2 * win, n=NFFT, axis=1)
        df = SR / NFFT
        for j, i in enumerate(idx):
            f0i = f0[i]
            ks = np.arange(1, int(3400 // f0i) + 1)
            ks = ks[ks * f0i >= 100]
            if ks.size < 4:
                continue
            hb = np.round(ks * f0i / df).astype(int)
            vb = np.round((ks + 0.5) * f0i / df).astype(int)
            vb = vb[vb < mag.shape[1]]
            # local peak search +-1 bin so a slightly-off F0 does not read as a valley
            pk = np.array([lsd[i, max(b - 1, 0):b + 2].max() for b in hb])
            valley.append(float(np.mean(pk[: vb.size]) - np.mean(lsd[i, vb])) if vb.size else NAN)
            # instantaneous frequency of the first harmonics (phase advance over 1 ms)
            kk = ks[:6]
            bins = np.array([max(b - 1, 0) + int(np.argmax(mag[i, max(b - 1, 0):b + 2])) for b in hb[:6]])
            dphi = np.angle(X2[j, bins]) - np.angle(X[i, bins]) - 2 * np.pi * bins * df * d_s / SR
            dphi = (dphi + np.pi) % (2 * np.pi) - np.pi
            inst = bins * df + dphi * SR / (2 * np.pi * d_s)
            est = np.median(inst / kk)
            if est > 0:
                ifdev.append(float(np.mean(np.abs(inst / kk - est)) / est))
            # group delay (samples) in 300-3400 Hz over bins with real energy; robust spread
            m = (f >= 300) & (f <= 3400)
            g = np.real(Xn[j, m] * np.conj(X[i, m])) / (mag[i, m] ** 2)
            strong = mag[i, m] > np.median(mag[i, m])
            if strong.sum() >= 10:
                gs = g[strong]
                gd.append(float(np.median(np.abs(gs - np.median(gs)))) * 1000.0 / SR)
        out["harm_valley_db"] = _nanmed(valley)
        out["harm_if_dev"] = _nanmed(ifdev)
        out["group_delay_ms"] = _nanmed(gd)

    # ---- cepstral peak prominence on active frames
    act = np.where(db >= p95 - 25.0)[0][::2]
    if act.size >= 15:
        ls = lsd[act][:, band]
        ceps = 20 * np.log10(np.abs(np.fft.rfft(ls - ls.mean(axis=1, keepdims=True), n=2048, axis=1)) + 1e-9)
        q = np.arange(ceps.shape[1]) / (2048 * df_band(f))
        qlo, qhi = np.searchsorted(q, 1 / 400), np.searchsorted(q, 1 / 70)
        reg = (q >= 0.001) & (q <= 0.016)
        A = np.vstack([q[reg], np.ones(reg.sum())]).T
        coef, *_ = np.linalg.lstsq(A, ceps[:, reg].T, rcond=None)          # one line fit per frame, vectorised
        pk = qlo + np.argmax(ceps[:, qlo:qhi], axis=1)
        base = coef[0] * q[pk] + coef[1]
        out["cpp_db"] = float(np.median(ceps[np.arange(len(pk)), pk] - base))

    # ---- spectral shape and dynamics on speech frames
    spm = mag[sp][:, band]
    out["speech_flatness"] = float(np.median(np.exp(np.mean(np.log(spm), axis=1)) / np.mean(spm, axis=1)))
    pspec = (mag[sp] ** 2).mean(axis=0)
    e_lo = pspec[(f >= 100) & (f < 1000)].sum()
    e_hi = pspec[(f >= 1000) & (f <= 3400)].sum()
    out["spectral_tilt_db"] = float(10 * np.log10((e_hi + 1e-20) / (e_lo + 1e-20)))
    out["lowmid_balance_db"] = float(10 * np.log10((pspec[(f >= 500) & (f < 1000)].sum() + 1e-20) /
                                                   (pspec[(f >= 100) & (f < 500)].sum() + 1e-20)))
    nm = mag[:, band] / (np.linalg.norm(mag[:, band], axis=1, keepdims=True) + 1e-12)
    flux = np.linalg.norm(np.diff(nm, axis=0), axis=1)
    both_sp = sp[1:] & sp[:-1]
    if both_sp.sum() >= 10:
        out["spectral_flux"] = float(np.mean(flux[both_sp]))
    rough = []
    for s, e in _runs(sp):
        if e - s >= 10:
            rough.extend(np.abs(np.diff(db[s:e], 2)).tolist())
    if len(rough) >= 20:
        out["env_roughness_db"] = float(np.mean(rough))
    # syllable-rate modulation of the 100 Hz envelope
    env = rms - rms.mean()
    spec = np.abs(np.fft.rfft(env * np.hanning(env.size))) ** 2
    fm = np.fft.rfftfreq(env.size, d=HOP / SR)
    tot = spec[(fm >= 0.5) & (fm <= 50)].sum()
    if tot > 1e-18:
        out["mod_4_16"] = float(spec[(fm >= 4) & (fm <= 16)].sum() / tot)

    # ---- pauses: how much, how long, and what the silence sounds like
    out["pause_share"] = float(1 - sp.mean())
    r_ = _runs(sp)
    gaps = [(r_[i + 1][0] - r_[i][1]) * 10.0 for i in range(len(r_) - 1)]
    out["max_gap_ms"] = float(max(gaps)) if gaps else 0.0
    q_ = ~sp
    if q_.sum() >= 15:
        out["pause_depth_db"] = float(np.median(db[q_]) - p95)
        qm = mag[q_][:, band]
        out["pause_flatness"] = float(np.median(np.exp(np.mean(np.log(qm), axis=1)) / np.mean(qm, axis=1)))
        out["pause_wobble_db"] = float(np.std(db[q_]))
    # breath-like events: >= 100 ms of noisy (flat), low-level sound in the 600 ms before a phrase onset, per 10 s of speech
    flat = np.exp(np.mean(np.log(mag[:, band]), axis=1)) / np.mean(mag[:, band], axis=1)
    ev = 0
    for s, e in r_:
        a, b = max(0, s - 60), max(0, s - 3)
        if b - a < 10:
            continue
        cand = (db[a:b] > p10 + 4) & (db[a:b] < thr) & (flat[a:b] > 0.35)
        ev += int(cand.sum() >= 10)
    out["breath_rate"] = float(10 * ev / max(sp.sum() * 0.01, 1e-6))


def df_band(f: np.ndarray) -> float:
    return float(f[1] - f[0])


def finite_or_nan(v) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return NAN
    return v if math.isfinite(v) else NAN
