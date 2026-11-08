"""learned_tells voter: a logistic regression over interpretable voice tells (signals/tell_features.py) and, when Pellav2 is
running, a PCA of its frozen w2v-BERT 2.0 layer embedding. Fitted offline on every labelled clip we have, judged held-out by
generator, speaker group and script (training/learned_tells/, docs/LEARNED-TELLS.md).

Safety and determinism:
  * the coefficients, scaler and PCA are a small JSON file next to this module, pinned by SHA-256 and parsed with `json`
    (no pickle, no code); a mismatch, a malformed file or a shape error makes the voter applicable=False, never fatal;
  * numpy only at inference; the embedding comes from the Pellav2 forward pass that already runs (no second model);
  * it scores exactly Pellav2's windows (4 s, 2 s hop, silence skipped, same cap); call score = sigmoid(mean window logit);
  * its logit is re-centred on humans (0 = the 99th percentile of held-in real voices), so a voice it has never seen the
    generator of still reads as "unlike the people we trained on" instead of "unlike the fakes we trained on";
  * optional call-level "pauses" block (signals/pauses.py): call logit = head_coef * mean(window logit) + pause terms +
    intercept, fitted and re-centred on humans by training/learned_tells/pauses.py. Absent block = the plain mean, unchanged;
  * TELL_LEARNED_TELLS=0 turns it off (no Tell is added at all, so the verdict is bit-identical to the engine without the
    module); =1 forces it on; unset follows DEFAULT_ON, which is set from the held-out results (see the doc).
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from pathlib import Path

import numpy as np

from .. import env as _env
from .. import thresholds as T
from ..types import Tell
from . import pauses as PZ
from . import tell_features as TF

log = logging.getLogger("tell.learned")
SR = 16_000
WEIGHTS = Path(__file__).with_name("learned_tells.json")
SHA256 = "11f1d2de16489a141cd940ff576c005a0b9d36b055814081e7ed7273cd29171a"
DEFAULT_ON = True                   # held-out bar met in clean and phone codecs, no added false alarm (docs/LEARNED-TELLS.md)
MAX_BYTES = 2_000_000
_cache: dict | None = None
_error = ""


def enabled() -> bool:
    v = _env.get("TELL_LEARNED_TELLS", "").strip().lower()
    if v in ("0", "false", "off", "no"):
        return False
    if v in ("1", "true", "on", "yes"):
        return True
    return DEFAULT_ON


def _na(why: str) -> Tell:
    return Tell("learned_tells", "acoustic", 0.5, T.ACOUSTIC_WEIGHTS.get("learned_tells", 0.0), why, applicable=False)


def _arr(v, shape=None) -> np.ndarray:
    a = np.asarray(v, dtype=np.float64)
    if shape is not None and a.shape != shape:
        raise ValueError(f"bad shape {a.shape} != {shape}")
    if not np.all(np.isfinite(a)):
        raise ValueError("non-finite parameter")
    return a


def parse(raw: bytes) -> dict:
    """Validate and convert the weights JSON. Raises ValueError on anything unexpected."""
    doc = json.loads(raw.decode("utf-8"))
    if not isinstance(doc, dict) or doc.get("format") != "tell-learned-tells/1":
        raise ValueError("unknown weights format")
    models = {}
    for key in ("full", "interp"):
        m = doc.get("models", {}).get(key)
        if m is None:
            continue
        feats = [str(f) for f in m["features"]]
        unknown = [f for f in feats if f not in TF.FEATURE_NAMES]
        if unknown:
            raise ValueError(f"unknown features {unknown}")
        nf = len(feats)
        out = {"features": feats, "idx": [TF.FEATURE_NAMES.index(f) for f in feats],
               "med": _arr(m["median"], (nf,)), "mu": _arr(m["mean"], (nf,)), "sd": _arr(m["scale"], (nf,)),
               "clip": float(m.get("clip", 5.0)), "intercept": float(m["intercept"])}
        nc = nf
        if m.get("emb"):
            e = m["emb"]
            L, k, D = int(e["layer"]), int(e["k"]), int(e["dim"])
            if not (0 <= L <= 64 and 1 <= k <= 128 and 1 <= D <= 4096):
                raise ValueError("embedding block out of bounds")
            out["emb"] = {"layer": L, "mean": _arr(e["mean"], (D,)), "pc": _arr(e["components"], (k, D)),
                          "z_mu": _arr(e["z_mean"], (k,)), "z_sd": _arr(e["z_scale"], (k,))}
            nc += k
        if m.get("neural"):
            nb = m["neural"]
            if list(nb["inputs"]) != ["pella_logit"]:
                raise ValueError("only the Pellav2 window logit is supported as a neural input")
            out["neural"] = {"mean": _arr(nb["mean"], (1,)), "scale": _arr(nb["scale"], (1,))}
            if np.any(out["neural"]["scale"] <= 0):
                raise ValueError("non-positive scale")
            nc += 1
        out["coef"] = _arr(m["coef"], (nc,))
        if np.any(out["sd"] <= 0) or ("emb" in out and np.any(out["emb"]["z_sd"] <= 0)):
            raise ValueError("non-positive scale")
        models[key] = out
    if "interp" not in models or "full" not in models or "emb" not in models["full"]:
        raise ValueError("weights must include the interp and the full (embedding) model")
    out = {"models": models, "meaning": doc.get("meaning", {}), "version": str(doc.get("version", ""))}
    if doc.get("pauses") is not None:
        out["pauses"] = parse_pauses(doc["pauses"])
    return out


def parse_pauses(b: dict) -> dict:
    """Validate the call-level pause stacker. Raises ValueError on anything unexpected."""
    feats = [str(f) for f in b["features"]]
    unknown = [f for f in feats if f not in PZ.PAUSE_FEATURES]
    if unknown or not feats or len(set(feats)) != len(feats):
        raise ValueError(f"bad pause features {feats}")
    nf = len(feats)
    out = {"features": feats, "med": _arr(b["median"], (nf,)), "mu": _arr(b["mean"], (nf,)), "sd": _arr(b["scale"], (nf,)),
           "coef": _arr(b["coef"], (nf,)), "clip": float(b.get("clip", 5.0)),
           "head_coef": float(b["head_coef"]), "intercept": float(b["intercept"])}
    if np.any(out["sd"] <= 0) or not (0 < out["head_coef"] <= 10) or not math.isfinite(out["intercept"]):
        raise ValueError("bad pause stacker scale/head_coef/intercept")
    return out


def call_logit(head_mean: float, pz: dict | None, x16k: np.ndarray) -> tuple[float, dict | None]:
    """Stack the call-level pause terms onto the head's mean window logit. No block = the mean unchanged (bit-identical)."""
    if pz is None:
        return head_mean, None
    f = PZ.call_pause_features(x16k)
    v = np.array([f[n] for n in pz["features"]], dtype=np.float64)
    v = np.where(np.isfinite(v), v, pz["med"])
    z = np.clip((v - pz["mu"]) / pz["sd"], -pz["clip"], pz["clip"])
    terms = z * pz["coef"]
    return float(pz["head_coef"] * head_mean + terms.sum() + pz["intercept"]), {"features": f, "terms": terms}


def load() -> dict | None:
    """Pinned, size-capped, hash-checked JSON. Cached per process; errors cached too (never retried in a hot loop)."""
    global _cache, _error
    if _cache is not None or _error:
        return _cache
    try:
        raw = WEIGHTS.read_bytes()
        if len(raw) > MAX_BYTES:
            raise ValueError("weights file too large")
        if hashlib.sha256(raw).hexdigest() != SHA256:
            raise ValueError("weights do not match the pinned SHA-256")
        _cache = parse(raw)
    except Exception as e:  # noqa: BLE001
        _error = f"learned tells unavailable ({type(e).__name__}: {str(e)[:80]})"
        log.warning(_error)
    return _cache


def layers_needed() -> tuple[int, ...]:
    """Backbone layers the full model reads (asked of Pellav2's forward pass); empty when off or unavailable."""
    if not enabled():
        return ()
    w = load()
    return (w["models"]["full"]["emb"]["layer"],) if w else ()


def window_logits(m: dict, F: np.ndarray, E: np.ndarray | None, P: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(logit per window, standardised design [n, nc]) for model m. F = [n, len(FEATURE_NAMES)] raw features,
    E = [n, D] backbone layer means, P = [n] Pellav2 window probabilities (only for models that use them)."""
    x = F[:, m["idx"]]
    x = np.where(np.isfinite(x), x, m["med"])
    z = np.clip((x - m["mu"]) / m["sd"], -m["clip"], m["clip"])
    if "emb" in m:
        e = m["emb"]
        pz = (E - e["mean"]) @ e["pc"].T
        z = np.hstack([z, np.clip((pz - e["z_mu"]) / e["z_sd"], -m["clip"], m["clip"])])
    if "neural" in m:
        p = np.clip(np.asarray(P, dtype=np.float64), 1e-4, 1 - 1e-4)
        lg = np.log(p / (1 - p))[:, None]
        z = np.hstack([z, np.clip((lg - m["neural"]["mean"]) / m["neural"]["scale"], -m["clip"], m["clip"])])
    return z @ m["coef"] + m["intercept"], z


def learned_vote(x16k: np.ndarray, pella_extras: dict | None = None) -> Tell | None:
    """None when the voter is off (so nothing changes); otherwise a Tell (applicable=False on any problem).

    The vote comes from the "full" model (PCA of a Pellav2 backbone layer + logistic regression, its logit re-centred so 0 is
    the edge of the real voices it was trained on). The "interp" model (interpretable tells) never votes; it only names the
    tells in the evidence line."""
    if not enabled():
        return None
    w = load()
    if w is None:
        return _na(_error or "learned tells not loaded")
    full = w["models"]["full"]
    L = full["emb"]["layer"]
    if not pella_extras or L not in pella_extras.get("emb", {}):
        return _na("learned tells need the Pellav2 embedding (Pellav2 off or failed)")
    ts = [round(float(t), 2) for t in pella_extras.get("t", [])]
    emb = np.asarray(pella_extras["emb"][L], dtype=np.float64)
    if not ts or emb.shape[0] != len(ts):
        return _na("learned tells: embedding and windows do not line up")
    x = np.asarray(x16k, dtype=np.float32)
    try:
        feats = [TF.window_features(x[int(round(t * SR)):int(round(t * SR)) + 4 * SR]) for t in ts]   # once per window
        F = np.array([[f[n] for n in TF.FEATURE_NAMES] for f in feats], dtype=np.float64)
        P = np.asarray(pella_extras.get("p", []), dtype=np.float64) if "neural" in full else None
        lg, _ = window_logits(full, F, emb, P)
        _, zi = window_logits(w["models"]["interp"], F, None)
    except Exception as e:  # noqa: BLE001
        log.warning("learned tells failed: %s", e)
        return _na(f"learned tells failed ({type(e).__name__})")
    try:
        logit, pinfo = call_logit(float(np.mean(lg)), w.get("pauses"), x)
    except Exception as e:  # noqa: BLE001
        log.warning("learned tells pause stacker failed: %s", e)
        return _na(f"learned tells failed ({type(e).__name__})")
    score = float(1 / (1 + math.exp(-logit)))
    n = len(ts)
    evidence = f"learned tells: P(synthetic) = {score:.2f} over {n} window{'s' if n != 1 else ''}"
    if pinfo is not None:
        push = float(pinfo["terms"].sum())
        evidence += f"; {PZ.describe(pinfo['features'])}" + (f" ({'toward AI' if push > 0 else 'toward human'})" if abs(push) >= 0.15 else "")
    up, down = _top_tells(w["models"]["interp"], zi, w["meaning"])
    if up:
        evidence += "; toward AI: " + ", ".join(up)
    if down:
        evidence += "; toward human: " + ", ".join(down)
    return Tell("learned_tells", "acoustic", score, T.ACOUSTIC_WEIGHTS.get("learned_tells", 0.0), evidence,
                detail=_detail(ts, lg, pinfo))


def _detail(ts: list[float], lg: np.ndarray, pinfo: dict | None) -> dict:
    d = {"windows": [{"t": t, "p": round(float(1 / (1 + math.exp(-v))), 4)} for t, v in zip(ts, lg)]}
    if pinfo is not None:
        d["pauses"] = {k: (round(v, 3) if math.isfinite(v) else None) for k, v in pinfo["features"].items()}
    return d


def _top_tells(m: dict, z: np.ndarray, meaning: dict) -> tuple[list[str], list[str]]:
    """Plain-English words for the interpretable tells that pushed this call furthest toward AI / toward human (max 2 each)."""
    nf = len(m["features"])
    contrib = z[:, :nf].mean(axis=0) * m["coef"][:nf]
    up, down = [], []
    for j in np.argsort(-np.abs(contrib)):
        if abs(contrib[j]) < 0.15:
            break
        name = m["features"][j]
        side = "ai" if contrib[j] > 0 else "human"
        bucket = up if side == "ai" else down
        if len(bucket) < 2:
            bucket.append(str(meaning.get(name, {}).get(side, name)))
    return up, down
