"""Load the learned-tells caches into aligned per-window and per-clip arrays (see extract.py)."""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

# the CURRENT engine (thresholds 2026-11-07.3) voice weights; used to rebuild its fused voice p_ai per clip
CUR_W = {"pause_regularity": 1.0, "breath_proxy": 1.2, "pitch_stability": 0.9, "noise_floor": 0.8}
W_PELLA, W_HF = 4.0, 0.7
EPS = 1e-4
PELLA_EPS = 0.01   # window P clipped to [0.01, 0.99] before the logit mean (same as pella.LOGIT_EPS)


def logit(p):
    p = np.clip(np.asarray(p, np.float64), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(z):
    return 1 / (1 + np.exp(-np.asarray(z, np.float64)))


class Cond:
    """One channel condition: windows (aligned between the neural and the feature cache) and per-clip engine components."""

    def __init__(self, cond: str, layers: tuple[int, ...] = ()):
        self.cond = cond
        n = np.load(C.LT / f"neural_{cond}.npz")
        f = np.load(C.LT / f"feats_{cond}.npz")
        assert np.array_equal(n["clip"], f["clip"]) and np.allclose(n["t"], f["t"]), f"window mismatch in {cond}"
        self.clip = n["clip"].astype(int)
        self.t = n["t"]
        self.pella_logit = n["pella_logit"].astype(np.float64)
        self.hf_p = n["hf_p"].astype(np.float64)
        self.X = f["X"].astype(np.float64)
        self.names = [str(s) for s in f["names"]]
        self.emb = {L: n["emb"][:, L, :].astype(np.float32) for L in layers}
        self.hf_prod = n["hf_prod"].astype(np.float64)
        self.cur = f["cur"].astype(np.float64)
        self.cur_names = [str(s) for s in f["cur_names"]]
        self.high_band_ratio = f["high_band_ratio"]
        self.n_clips = len(self.hf_prod)
        off = np.load(C.LT / f"audio_{cond}.npz")["off"]
        self.dur = np.diff(off) / 16000.0
        self.win_of = [np.where(self.clip == i)[0] for i in range(self.n_clips)]

    # ---- the engine's pieces per clip
    def pella_prod(self) -> np.ndarray:
        """What the CURRENT engine computes: mean P over at most 3 evenly spaced windows (PELLA_MAX_WINDOWS=3)."""
        out = np.full(self.n_clips, np.nan)
        for i, w in enumerate(self.win_of):
            if len(w) == 0:
                continue
            idx = np.unique(np.linspace(0, len(w) - 1, 3).round().astype(int)) if len(w) > 3 else np.arange(len(w))
            out[i] = float(np.mean(sigmoid(self.pella_logit[w[idx]])))
        return out

    def pella_all(self, eps: float = PELLA_EPS) -> np.ndarray:
        """The fix: every window, aggregated as sigmoid(mean of window logits)."""
        out = np.full(self.n_clips, np.nan)
        for i, w in enumerate(self.win_of):
            if len(w):
                out[i] = float(sigmoid(np.mean(np.clip(self.pella_logit[w], logit(eps), logit(1 - eps)))))
        return out

    def fused(self, *, breath_w=1.2, pella="prod", extra=None, extra_w=0.0, pella_w=W_PELLA, hf_w=W_HF,
              cur_w=None, dur_s=None) -> np.ndarray:
        """Voice-only fused p_ai (no transcript: script tells not applicable), exactly scorer._wmean over the voice tells."""
        w = dict(CUR_W if cur_w is None else cur_w)
        w["breath_proxy"] = breath_w
        pp = self.pella_prod() if pella == "prod" else self.pella_all()
        out = np.full(self.n_clips, np.nan)
        for i in range(self.n_clips):
            num = den = 0.0
            for j, nm in enumerate(self.cur_names):
                s = self.cur[i, j]
                if np.isfinite(s) and w[nm] > 0:
                    num += s * w[nm]; den += w[nm]
            neural_ok = self.dur[i] >= 3.0                     # neural.analyze skips clips under 3 s
            for s, ww in ((pp[i], pella_w), (self.hf_prod[i], hf_w)):
                if neural_ok and np.isfinite(s) and ww > 0:
                    num += s * ww; den += ww
            if extra is not None and neural_ok and np.isfinite(extra[i]) and extra_w > 0:
                num += extra[i] * extra_w; den += extra_w
            out[i] = num / den if den > 0 else 0.5
        return out


@lru_cache(maxsize=None)
def load(cond: str, layers: tuple[int, ...] = ()) -> Cond:
    return Cond(cond, layers)


def sources():
    rows = C.read_sources()
    return rows
