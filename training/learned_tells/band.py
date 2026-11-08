#!/usr/bin/env python3
"""band_limited calibration: 4-8 kHz energy relative to 1-4 kHz, on the SAME clips clean vs through phone codecs.

  python -I training/learned_tells/band.py      # prints distributions and the threshold that separates them
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
from extract import load_audio  # noqa: E402

from tell.signals import tell_features as TF  # noqa: E402


def main() -> None:
    rows = C.read_sources()
    res = {}
    for cond in ("clean", "opus8k", "g711_mulaw8k", "chain_replay_call", "speaker_rerecord_sim", "opus_lowbitrate_with_loss"):
        xs = load_audio(cond)
        res[cond] = np.array([TF.band_ratio_db(x) for x in xs])
    clean = res["clean"]
    for cond, v in res.items():
        q = np.nanpercentile(v, [0, 1, 5, 50, 95, 99, 100])
        print(f"{cond:28s} n={np.isfinite(v).sum():4d}  min/p1/p5/med/p95/p99/max dB: " + " ".join(f"{a:6.1f}" for a in q))
    # wideband sources only (some sources are already narrowband in the clean condition: the Sanath raw takes etc.)
    phone = np.concatenate([res[c] for c in ("opus8k", "g711_mulaw8k", "chain_replay_call", "speaker_rerecord_sim", "opus_lowbitrate_with_loss")])
    print("phone max", np.nanmax(phone), " clean p1", np.nanpercentile(clean, 1))
    low_clean = [(rows[i]["id"], round(float(clean[i]), 1)) for i in np.argsort(clean)[:15]]
    print("lowest clean clips:", low_clean)
    np.savez(C.LT / "band.npz", **res)


if __name__ == "__main__":
    main()
