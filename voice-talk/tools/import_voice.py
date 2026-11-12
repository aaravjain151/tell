"""Import a reference voice from a longer recording: picks the cleanest 5-15 s stretch, stores it under
voices/<name>/ and writes consent.json ONLY from the attestation given on the command line.

    python tools/import_voice.py --src clip.wav --transcript clip.txt --name sanath \
        --speaker "Full Name" --attest "What the speaker actually agreed to, in their words, and when"

--speaker and --attest are mandatory and have NO default: the tool refuses to run without them, and nothing is
written unless they are non-empty. The source recording is only ever read. voices/ is gitignored; never commit it.
The segment's words are cut from your transcript by proportion of voiced time (no forced aligner), snapped to
punctuation; check the printed text and use "Preview" in the app before relying on the clone.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from voice_talk.voices import ConsentError, VoiceError, VoiceStore, validate_name  # noqa: E402

OUT_SR = 24000
FRAME_S = 0.02
MIN_PAUSE_S = 0.30
PAD_S = 0.15


def _resample(x: np.ndarray, sr: int, out_sr: int) -> np.ndarray:
    if sr == out_sr:
        return x
    from scipy.signal import resample_poly
    g = gcd(sr, out_sr)
    return resample_poly(x, out_sr // g, sr // g).astype(np.float32)


def _frames(x: np.ndarray, sr: int):
    n = int(sr * FRAME_S)
    k = len(x) // n
    rms = np.sqrt((x[: k * n].reshape(k, n).astype(np.float64) ** 2).mean(axis=1))
    return rms, n


def _map_text(tokens: list[str], voiced_cum: np.ndarray, a_f: int, b_f: int) -> str:
    """Words for frames [a_f, b_f), assuming words are spread in proportion to voiced time, snapped to punctuation."""
    total = voiced_cum[-1] or 1.0
    n = len(tokens)

    def idx(frame: int, prefer_end: bool) -> int:
        i = int(round(voiced_cum[min(frame, len(voiced_cum) - 1)] / total * n))
        best, best_d = i, 99
        for j in range(max(0, i - 3), min(n, i + 3) + 1):
            if j == 0 or j == n or re.search(r"[.!?,;:]$", tokens[j - 1]):
                d = abs(j - i)
                if d < best_d:
                    best, best_d = j, d
        return max(0, min(n, best))

    i0, i1 = idx(a_f, False), idx(b_f, True)
    return " ".join(tokens[i0:i1])


def pick_segment(audio: np.ndarray, sr: int, transcript: str, lo: float = 5.0, hi: float = 15.0) -> dict:
    """Return {start_s, end_s, text, score, snr_db, whole} for the cleanest lo..hi second stretch."""
    x = audio if audio.ndim == 1 else audio.mean(axis=1)
    x = x.astype(np.float32)
    rms, n = _frames(x, sr)
    if len(rms) < 10:
        raise ValueError("recording is too short")
    floor = float(np.percentile(rms, 10))
    thr = max(floor * 3.0, 0.1 * float(np.percentile(rms, 95)), 0.004)
    voiced = rms > thr
    if voiced.mean() < 0.1:
        raise ValueError("no clear speech found in the recording")
    first, last = int(np.argmax(voiced)), len(voiced) - 1 - int(np.argmax(voiced[::-1]))
    pad = int(PAD_S / FRAME_S)
    tokens = transcript.split()
    if not tokens:
        raise ValueError("the transcript is empty")
    # boundaries: speech start, centre of every long pause, speech end
    bounds = [max(0, first - pad)]
    run = 0
    for i in range(first, last + 1):
        if voiced[i]:
            if run * FRAME_S >= MIN_PAUSE_S:
                bounds.append(i - run // 2)
            run = 0
        else:
            run += 1
    bounds.append(min(len(voiced), last + 1 + pad))
    cum = np.cumsum(voiced.astype(np.float64))
    cands = []
    for ai in range(len(bounds)):
        for bi in range(ai + 1, len(bounds)):
            a, b = bounds[ai], bounds[bi]
            dur = (b - a) * FRAME_S
            if dur < lo:
                continue
            if dur > hi:
                break
            seg = rms[a:b]
            ratio = float((seg > thr).mean())
            sp = seg[seg > thr]
            snr = 20 * np.log10(max(float(np.percentile(sp, 90)), 1e-6) / max(float(np.percentile(seg, 10)), 1e-6)) if len(sp) else 0.0
            peak = float(np.abs(x[a * n:b * n]).max())
            score = min(snr, 40) / 40 + ratio + min(dur, 12.0) / 12.0 * 0.5 - (1.0 if peak > 0.99 else 0.0)
            cands.append((score, a, b, snr, ratio))
    if not cands:
        raise ValueError(f"no stretch of {lo:.0f}-{hi:.0f} s between pauses; trim the recording by hand")
    score, a, b, snr, _ = max(cands)
    whole = (a == bounds[0] and b == bounds[-1])
    text = transcript.strip() if whole else _map_text(tokens, cum, a, b)
    return {"start_s": round(a * FRAME_S, 2), "end_s": round(b * FRAME_S, 2), "text": text,
            "score": round(float(score), 3), "snr_db": round(float(snr), 1), "whole": whole}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="recording (.wav); only read")
    ap.add_argument("--transcript", required=True, help="text file with the exact words spoken in the recording")
    ap.add_argument("--name", required=True)
    ap.add_argument("--speaker", required=True, help="the speaker's full name (required, no default)")
    ap.add_argument("--attest", required=True, help="what the speaker agreed to, as stated by them (required, no default)")
    ap.add_argument("--voices-dir", default=str(Path(__file__).resolve().parent.parent / "voices"))
    ap.add_argument("--min-s", type=float, default=5.0)
    ap.add_argument("--max-s", type=float, default=15.0)
    a = ap.parse_args(argv)

    if not a.speaker.strip():
        ap.error("--speaker must not be empty")
    if not a.attest.strip():
        ap.error("--attest must not be empty; the tool never invents an attestation")
    try:
        validate_name(a.name)
        src, tpath = Path(a.src), Path(a.transcript)
        if not src.is_file() or not tpath.is_file():
            raise VoiceError("--src and --transcript must be existing files")
        transcript = re.sub(r"\s+", " ", tpath.read_text(encoding="utf-8")).strip()
        audio, sr = sf.read(str(src), dtype="float32")
        seg = pick_segment(audio, sr, transcript, a.min_s, a.max_s)
        mono = audio if audio.ndim == 1 else audio.mean(axis=1)
        clip = _resample(mono[int(seg["start_s"] * sr): int(seg["end_s"] * sr)], sr, OUT_SR)
        buf = io.BytesIO()
        sf.write(buf, clip, OUT_SR, format="WAV", subtype="PCM_16")
        res = VoiceStore(Path(a.voices_dir)).create(a.name, buf.getvalue(), seg["text"], a.speaker, True,
                                                    attestation=a.attest)
    except (ConsentError, VoiceError, ValueError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(f"imported voice {a.name!r} -> {Path(a.voices_dir) / a.name}")
    print(f"  segment {seg['start_s']}s-{seg['end_s']}s of {src.name} (snr ~{seg['snr_db']} dB, whole file: {seg['whole']})")
    print(f"  words: {seg['text']}")
    print(f"  stored at {OUT_SR} Hz mono; consent recorded for {a.speaker.strip()!r} from --attest")
    if not seg["whole"]:
        print("  note: the words were cut from your transcript by proportion, not forced alignment; check them.")
    for w in res["warnings"]:
        print("  warning:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
