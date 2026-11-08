#!/usr/bin/env python3
"""Paired feature table for real (Sanath) vs Qwen3-TTS (same speaker's clone, same scripts). Offline study tool, not product code.

    python3 tools/qwen_cues_prep.py WORK          # once: audio per condition + word times
    python3 tools/qwen_cues.py WORK               # writes WORK/features.csv

Uses praat-parselmouth and librosa (study-only; not imported by services/api). One speaker, one TTS engine: see docs/QWEN-CUES.md.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import parselmouth
from parselmouth.praat import call

SR = 16_000
COND = ["clean", "opus8k", "g711_mulaw8k", "chain_replay_call"]


def _db_frames(x, frame=320, hop=160):
    n = 1 + (len(x) - frame) // hop
    idx = np.arange(frame)[None] + hop * np.arange(n)[:, None]
    return 20 * np.log10(np.sqrt(np.mean(x[idx].astype(np.float64) ** 2, axis=1)) + 1e-9)


def speech_mask(db):
    thr = max(np.percentile(db, 10) + 8.0, np.percentile(db, 95) - 35.0)
    m = db >= thr
    # fill gaps < 120 ms (12 hops); drop blips < 80 ms
    def runs(b):
        d = np.diff(np.concatenate(([0], b.astype(int), [0])))
        return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))
    for s, e in runs(~m):
        if e - s < 12 and s > 0 and e < len(m):
            m[s:e] = True
    for s, e in runs(m):
        if e - s < 8:
            m[s:e] = False
    return m, thr


def runs(b):
    d = np.diff(np.concatenate(([0], b.astype(int), [0])))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def st(f):
    return 12 * np.log2(f / 100.0)


def cv(a):
    a = np.asarray(a, float)
    return float(np.std(a) / np.mean(a)) if len(a) >= 2 and np.mean(a) > 0 else np.nan


def feats(x: np.ndarray, words: list, script: str) -> dict:
    o: dict = {}
    x = x.astype(np.float64)
    dur = len(x) / SR
    db = _db_frames(x)
    m, thr = speech_mask(db)
    sp = runs(m)
    # ----- pauses (>=120 ms gaps between speech runs, excluding leading/trailing)
    gaps = [(sp[i][1], sp[i + 1][0]) for i in range(len(sp) - 1)]
    pd_ms = np.array([(b - a) * 10 for a, b in gaps], float)
    speech_s = m.sum() * 0.01
    nw = max(len(script.split()), 1)
    o["dur_s"] = dur
    o["speech_frac"] = float(m.mean())
    o["articulation_wps"] = nw / max(speech_s, 1e-3)
    o["overall_wps"] = nw / (sp[-1][1] * 0.01 - sp[0][0] * 0.01) if sp else np.nan
    o["pause_n_per_100w"] = 100 * len(pd_ms) / nw
    o["pause_mean_ms"] = float(pd_ms.mean()) if len(pd_ms) else np.nan
    o["pause_cv"] = cv(pd_ms)
    o["pause_long_n_per_100w"] = 100 * float((pd_ms >= 300).sum()) / nw
    o["pause_frac_time"] = float(pd_ms.sum() / 10 / max(len(m), 1))
    starts = np.array([a for a, _ in gaps], float) * 0.01
    o["pause_spacing_cv"] = cv(np.diff(starts)) if len(starts) >= 3 else np.nan
    # pause depth and breath
    if gaps:
        depth, breath, nb = [], 0, 0
        for a, b in gaps:
            if b - a < 20:
                continue
            seg = db[a:b]
            depth.append(np.median(seg) - np.median(db[m]))
            nb += 1
            if np.max(np.convolve(seg, np.ones(5) / 5, "same")) > np.percentile(db[m], 50) - 38 and (b - a) >= 20:
                breath += 1
        o["pause_depth_db"] = float(np.median(depth)) if depth else np.nan
        o["breathy_pause_frac"] = breath / nb if nb else np.nan
    else:
        o["pause_depth_db"] = o["breathy_pause_frac"] = np.nan
    o["floor_p5_db"] = float(np.percentile(db, 5) - np.percentile(db[m], 95))
    # ----- phrase-level rate variability (syllable nuclei via envelope peaks, 300-3000 Hz)
    import scipy.signal as ss
    b, a_ = ss.butter(4, [300, 3000], "bandpass", fs=SR)
    env = np.abs(ss.hilbert(ss.filtfilt(b, a_, x)))
    env = ss.filtfilt(*ss.butter(2, 10, "low", fs=SR), env)
    envh = env[::160]
    envdb = 20 * np.log10(envh + 1e-9)
    pk, _ = ss.find_peaks(envdb, prominence=3.0, distance=8)
    pk = pk[m[np.minimum(pk, len(m) - 1)]] if len(pk) else pk
    o["nuclei_per_speech_s"] = len(pk) / max(speech_s, 1e-3)
    rates = []
    for s, e in sp:
        if e - s >= 60:
            k = ((pk >= s) & (pk < e)).sum()
            rates.append(k / ((e - s) * 0.01))
    o["phrase_rate_cv"] = cv(rates)
    phr_dur = np.array([(e - s) * 0.01 for s, e in sp])
    o["phrase_dur_cv"] = cv(phr_dur)
    # inter-nucleus interval regularity (rhythm)
    ini = np.diff(pk) * 10.0
    ini = ini[ini < 400]
    o["inter_syll_cv"] = cv(ini)
    # ----- energy dynamics
    if len(sp) >= 3:
        on, off = [], []
        for s, e in sp:
            if e - s >= 15:
                seg = db[max(s - 2, 0):s + 8]
                on.append(np.max(np.diff(seg)) if len(seg) > 2 else np.nan)
                seg = db[e - 8:e + 3]
                off.append(-np.min(np.diff(seg)) if len(seg) > 2 else np.nan)
        o["onset_rise_db_10ms"] = float(np.nanmedian(on))
        o["offset_fall_db_10ms"] = float(np.nanmedian(off))
    o["speech_level_std_db"] = float(np.std(db[m]))
    envd = envdb[m[:len(envdb)]] if len(envdb) <= len(m) else envdb
    mod = envh[: len(envh)] - envh.mean()
    sp_ = np.abs(np.fft.rfft(mod * np.hanning(len(mod)))) ** 2
    f = np.fft.rfftfreq(len(mod), 0.01)
    tot = sp_[(f >= 0.5) & (f <= 50)].sum()
    o["mod_4_16_ratio"] = float(sp_[(f >= 4) & (f <= 16)].sum() / tot)
    pn = sp_[(f >= 0.5) & (f <= 20)]
    pn = pn / pn.sum()
    o["mod_entropy"] = float(-(pn * np.log(pn + 1e-12)).sum())
    # ----- Praat features
    snd = parselmouth.Sound(x.astype(np.float64), SR)
    pitch = snd.to_pitch_ac(time_step=0.01, pitch_floor=70, pitch_ceiling=400, voicing_threshold=0.5)
    f0 = pitch.selected_array["frequency"]
    voiced = f0 > 0
    o["voiced_frac_of_speech"] = float(voiced.sum() / max(m.sum(), 1))
    s0 = np.where(voiced, st(np.where(voiced, f0, 100)), np.nan)
    sv = s0[voiced]
    if len(sv) > 50:
        o["f0_mean_hz"] = float(np.mean(f0[voiced]))
        o["f0_std_st"] = float(np.std(sv))
        o["f0_range_st"] = float(np.percentile(sv, 95) - np.percentile(sv, 5))
        d = np.diff(s0)
        d = d[np.isfinite(d)]
        d = d[np.abs(d) < 3]            # no octave jumps
        o["f0_rate_st_per_s"] = float(np.mean(np.abs(d)) / 0.01)
        # micro perturbation: residual after 7-frame median smoothing, within runs
        res = []
        for s, e in runs(voiced):
            if e - s >= 9:
                seg = s0[s:e]
                sm = ss.medfilt(seg, 7)
                res.append(seg[3:-3] - sm[3:-3])
        o["f0_micro_st"] = float(np.std(np.concatenate(res))) if res else np.nan
        # F0 vs energy coupling
        n = min(len(s0), len(db))
        mk = voiced[:n] & np.isfinite(s0[:n])
        o["f0_energy_corr"] = float(np.corrcoef(s0[:n][mk], db[:n][mk])[0, 1])
        dd = np.diff(s0[:n]); de = np.diff(db[:n])
        mk2 = np.isfinite(dd) & (np.abs(dd) < 3)
        o["f0_energy_dcorr"] = float(np.corrcoef(dd[mk2], de[mk2])[0, 1])
        # phrases: declination, final movement, contour sameness
        fin, decl, conts, fry = [], [], [], []
        for s, e in sp:
            if (e - s) < 60:
                continue
            seg = s0[s:e]
            ok = np.isfinite(seg)
            if ok.sum() < 30:
                continue
            tt = np.arange(len(seg))[ok] * 0.01
            decl.append(np.polyfit(tt, seg[ok], 1)[0])
            last = seg[-20:]; prev = seg[-50:-20]
            if np.isfinite(last).sum() >= 6 and np.isfinite(prev).sum() >= 6:
                fin.append(np.nanmedian(last) - np.nanmedian(prev))
            fry.append(1 - np.isfinite(seg[-20:]).mean())
            c = np.interp(np.linspace(0, len(seg) - 1, 24), np.arange(len(seg))[ok], seg[ok])
            conts.append(c - c.mean())
        o["f0_declination_st_s"] = float(np.mean(decl)) if decl else np.nan
        o["f0_final_move_st_mean"] = float(np.mean(fin)) if fin else np.nan
        o["f0_final_move_st_std"] = float(np.std(fin)) if len(fin) >= 3 else np.nan
        o["phrase_final_unvoiced"] = float(np.mean(fry)) if fry else np.nan
        if len(conts) >= 4:
            C = np.corrcoef(np.array(conts))
            o["contour_sameness"] = float(C[np.triu_indices(len(conts), 1)].mean())
        o["decl_std"] = float(np.std(decl)) if len(decl) >= 3 else np.nan
    pp = call(snd, "To PointProcess (periodic, cc)", 70, 400)
    try:
        o["jitter_local"] = call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
        o["shimmer_local"] = call([snd, pp], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
    except Exception:
        o["jitter_local"] = o["shimmer_local"] = np.nan
    try:
        hnr = snd.to_harmonicity_cc(0.01, 70, 0.1, 1.0)
        h = hnr.values[0]
        h = h[h > -100]
        o["hnr_db"] = float(np.mean(h)); o["hnr_std_db"] = float(np.std(h))
    except Exception:
        pass
    try:
        pc = call(snd, "To PowerCepstrogram", 70, 0.002, 5000, 50)
        o["cpps_db"] = call(pc, "Get CPPS", "no", 0.02, 0.0005, 70, 400, 0.05, "parabolic", 0.001, 0, "Straight", "Robust")
    except Exception:
        o["cpps_db"] = np.nan
    # spectral tilt and band profile on voiced speech frames
    import librosa
    S = np.abs(librosa.stft(x.astype(np.float32), n_fft=512, hop_length=160, center=False)) ** 2
    n = min(S.shape[1], len(m))
    vm = m[:n] & (db[:n] > np.percentile(db[m], 40))
    L = S[:, :n][:, vm].mean(axis=1) + 1e-12
    fr = np.fft.rfftfreq(512, 1 / SR)
    ldb = 10 * np.log10(L)
    sel = (fr >= 100) & (fr <= 3400)
    o["tilt_db_per_oct"] = float(np.polyfit(np.log2(fr[sel]), ldb[sel], 1)[0])
    tot = L[(fr >= 50) & (fr <= 8000)].sum()
    for lo, hi in [(50, 500), (500, 1000), (1000, 2000), (2000, 3000), (3000, 4000), (4000, 6000), (6000, 8000)]:
        o[f"band_{lo}_{hi}_db"] = float(10 * np.log10(L[(fr >= lo) & (fr < hi)].sum() / tot))
    o["alpha_ratio_db"] = float(10 * np.log10(L[(fr >= 1000) & (fr < 3400)].sum() / L[(fr >= 50) & (fr < 1000)].sum()))
    # HF floor texture: frame-to-frame variability of 4-7 kHz band during speech (vocoder smoothness)
    hb = 10 * np.log10(S[(fr >= 4000) & (fr < 7500)].sum(axis=0) + 1e-12)[:n]
    o["hf_band_fluct_db"] = float(np.mean(np.abs(np.diff(hb[m[:n]]))))
    # formants
    try:
        fm = snd.to_formant_burg(0.01, 5, 4500, 0.025, 50)
        ts = pitch.xs()
        F1 = np.array([fm.get_value_at_time(1, t) for t in ts]); F2 = np.array([fm.get_value_at_time(2, t) for t in ts])
        ok = voiced & np.isfinite(F1) & np.isfinite(F2)
        d2 = np.abs(np.diff(F2)); okd = ok[1:] & ok[:-1]
        d1 = np.abs(np.diff(F1))
        o["f2_move_hz_10ms"] = float(np.median(d2[okd]))
        o["f1_move_hz_10ms"] = float(np.median(d1[okd]))
        o["f2_std_hz"] = float(np.std(F2[ok]))
        o["f1_std_hz"] = float(np.std(F1[ok]))
        o["f2_jerk_hz"] = float(np.median(np.abs(np.diff(F2, 2))[ok[2:] & ok[1:-1] & ok[:-2]]))
    except Exception:
        pass
    # ----- word-aligned pause placement (clean ASR timing; same word times used for every condition)
    if words:
        punc = [re.sub(r"[^a-z']", "", w.lower()) for w in script.split()]
        ends_punct = [bool(re.search(r"[.,;:?!]$", w)) for w in script.split()]
        asr_w = [re.sub(r"[^a-z']", "", w[0].lower()) for w in words]
        import difflib
        sm = difflib.SequenceMatcher(a=punc, b=asr_w, autojunk=False)
        mapping = {}
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    mapping[i1 + k] = j1 + k
        o["asr_match_frac"] = len(mapping) / max(len(punc), 1)
        gp = []
        for i in range(len(punc) - 1):
            if i in mapping and (i + 1) in mapping and mapping[i + 1] == mapping[i] + 1:
                j = mapping[i]
                gp.append((ends_punct[i], max(words[j + 1][1] - words[j][2], 0.0)))
        if gp:
            pa = np.array([g for p, g in gp if p]); pb = np.array([g for p, g in gp if not p])
            o["gap_at_punct_ms"] = float(np.median(pa) * 1000) if len(pa) else np.nan
            o["gap_midphrase_ms"] = float(np.median(pb) * 1000) if len(pb) else np.nan
            o["punct_realised_frac"] = float((pa >= 0.15).mean()) if len(pa) else np.nan
            o["midphrase_pause_per_100w"] = float(100 * (pb >= 0.15).sum() / nw)
            o["midphrase_gap_p90_ms"] = float(np.percentile(pb, 90) * 1000) if len(pb) else np.nan
            o["gap_punct_vs_mid_ratio"] = (o["gap_at_punct_ms"] / max(o["gap_midphrase_ms"], 1.0)) if len(pa) and len(pb) else np.nan
        o["asr_extra_words"] = max(len(asr_w) - len(punc), 0) / nw
        # gaps by boundary type: period/?/! vs comma/;/: vs no punctuation
        raw = script.split()
        gper, gcom, gmid = [], [], []
        for i in range(len(punc) - 1):
            if i in mapping and (i + 1) in mapping and mapping[i + 1] == mapping[i] + 1:
                j = mapping[i]
                g = max(words[j + 1][1] - words[j][2], 0.0) * 1000
                (gper if re.search(r"[.?!]$", raw[i]) else gcom if re.search(r"[,;:]$", raw[i]) else gmid).append(g)
        o["gap_period_ms"] = float(np.mean(gper)) if gper else np.nan
        o["gap_comma_ms"] = float(np.mean(gcom)) if gcom else np.nan
        o["gap_period_cv"] = cv(gper) if len(gper) >= 3 else np.nan
        o["gap_midword_mean_ms"] = float(np.mean(gmid)) if gmid else np.nan
        o["gap_ge120_per_100w"] = 100 * float(np.sum(np.array(gper + gcom + gmid) >= 120)) / nw
        o["gap_ge120_midword_per_100w"] = 100 * float(np.sum(np.array(gmid) >= 120)) / nw
        # sentence pace sameness: words per second inside each sentence (first word start to last word end)
        sent, cur = [], []
        for i in range(len(punc)):
            cur.append(i)
            if re.search(r"[.?!]$", raw[i]) or i == len(punc) - 1:
                sent.append(cur); cur = []
        paces = []
        for s_ in sent:
            if s_[0] in mapping and s_[-1] in mapping and len(s_) >= 4:
                t0, t1 = words[mapping[s_[0]]][1], words[mapping[s_[-1]]][2]
                if t1 - t0 > 0.5:
                    paces.append(len(s_) / (t1 - t0))
        o["sentence_pace_cv"] = cv(paces) if len(paces) >= 3 else np.nan
    return o


_W2V: dict = {}


def _cos_drift(E: np.ndarray, pre: str) -> dict:
    """Euclidean distances between adjacent windows / to the clip centroid, relative to the mean embedding norm."""
    nrm = np.linalg.norm(E, axis=1).mean() + 1e-9
    adj = np.linalg.norm(E[1:] - E[:-1], axis=1) / nrm
    cd = np.linalg.norm(E - E.mean(axis=0), axis=1) / nrm
    return {f"{pre}_adj_dist": float(adj.mean()), f"{pre}_centroid_dist": float(cd.mean()), f"{pre}_centroid_dist_std": float(cd.std())}


def drift(x: np.ndarray) -> dict:
    """Timbre consistency: mean-pooled 1 s embeddings of speech-heavy 1 s windows (>= 60% speech frames)."""
    import librosa
    db = _db_frames(x)
    m, _ = speech_mask(db)
    wins = [i for i in range(len(x) // SR) if m[i * 100:(i + 1) * 100].mean() >= 0.6]
    o: dict = {"drift_windows": len(wins)}
    if len(wins) < 4:
        return o
    mf = []
    for i in wins:
        M = librosa.feature.mfcc(y=x[i * SR:(i + 1) * SR].astype(np.float32), sr=SR, n_mfcc=20, n_fft=512, hop_length=160)
        mf.append(M[1:].mean(axis=1))
    mf = np.array(mf)
    o.update(_cos_drift(mf, "mfcc"))
    import torch
    from transformers import Wav2Vec2Model
    if "m" not in _W2V:
        _W2V["m"] = Wav2Vec2Model.from_pretrained("garystafford/wav2vec2-deepfake-voice-detector").eval()
    E = []
    with torch.no_grad():
        for i in wins:
            w = x[i * SR:(i + 1) * SR].astype(np.float32)
            w = (w - w.mean()) / (w.std() + 1e-7)
            hs = _W2V["m"](torch.from_numpy(w)[None], output_hidden_states=True).hidden_states
            E.append(torch.stack([hs[4], hs[8]]).mean(dim=2).reshape(-1).numpy())
    E = np.array(E)
    o.update(_cos_drift(E, "w2v"))
    return o


def main() -> int:
    work = Path(sys.argv[1])
    asr = json.loads((work / "asr.json").read_text())
    calls = Path("/Users/aarav/Downloads/tell/data/calls")
    rows = []
    for f in sorted((work / "audio").glob("*.npy")):
        cls, name, cond = f.stem.split("__")
        key = f"{cls}__{name}"
        script_name = name.replace("owner_", "")
        txt = calls / ("human/sanath" if cls == "human" else "qwen3tts") / f"{script_name}.txt"
        script = txt.read_text().strip() if txt.exists() else " ".join(w[0] for w in asr[key])
        if cond not in COND:
            continue
        xa = np.load(f)
        r = feats(xa, asr[key], script)
        r.update(drift(xa))
        r.update(cls=cls, script=name, cond=cond)
        rows.append(r)
        print(key, cond, flush=True)
    pd.DataFrame(rows).to_csv(work / "features.csv", index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
