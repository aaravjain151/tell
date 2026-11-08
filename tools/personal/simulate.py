#!/usr/bin/env python3
"""OFFLINE SIMULATION of the personal alert-sensitivity learner against the fixed stabiliser. NOT a user study.

    python3 tools/personal/simulate.py CLIPS.json [--streams 100] [--calls 300] [--boot 2000] [--seed 7]

CLIPS.json comes from tools/personal/collect.py (numbers only). Each call is replayed through the REAL live.StableTracker
(ticks every 3 s with small noise), so `max_alert` is what the shipped stabiliser would show. Then a simulated user gives
noisy feedback and the learner adapts. Metrics are PREQUENTIAL (each call is decided before its own feedback is learned).

LOUD CAVEAT. The call stream is SIMULATED. The only real inputs are ~39 distinct (clip, condition) pairs from ONE human speaker
and three TTS engines; on those real clips the fixed stabiliser already makes no mistakes (every scam clip has p_scam >= 0.84,
every other clip has p_scam 0). So the borderline categories (a reminder that mentions payment, a collector with urgency, a soft
scam below the scam threshold) are SYNTHESISED here from assumed score ranges, and the personas and their feedback habits are
assumptions. The result shows the MECHANISM can adapt in a simulated world; it says nothing about real users.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "api"))
os.environ.setdefault("LLM_PROVIDER", "stub")

from tell import live, personal  # noqa: E402

CATS = ("real_benign", "real_ai_disclosed", "real_scam", "pressure_disclosed", "pressure_human", "soft_scam")
WARRANTED = {"real_benign": False, "real_ai_disclosed": False, "real_scam": True, "pressure_disclosed": False,
             "pressure_human": False, "soft_scam": True}
PERSONAS = {
    "appointment-heavy": (0.35, 0.10, 0.05, 0.35, 0.10, 0.05),
    "scam-exposed": (0.35, 0.05, 0.15, 0.00, 0.10, 0.35),
    "typical": (0.60, 0.10, 0.10, 0.05, 0.10, 0.05),
}
P_FEEDBACK_ALERTED, P_FEEDBACK_QUIET = 0.60, 0.25


def tick_dicts(base: dict, rng: np.random.Generator, noise: float = 0.04) -> list[tuple[dict, float, float]]:
    """Ticks (d, t0, t1) for one simulated call from a template dict with p_scam, p_ai, disclosed, families, dur, band_limited."""
    n = max(3, int(base["dur"] // 3))
    out = []
    for i in range(1, n + 1):
        t1 = 3.0 * i
        ps = float(np.clip(base["p_scam"] + rng.normal(0, noise), 0, 1))
        pa = float(np.clip(base["p_ai"] + rng.normal(0, noise), 0, 1))
        tier = "scam" if ps >= 0.55 else ("ai_disclosed" if base["disclosed"] else ("unsure" if (pa >= 0.45 or ps >= 0.35) else "human"))
        out.append(({"tier": tier, "p_ai": pa, "p_scam": ps, "confidence": 0.8, "disclosed_ai": base["disclosed"] and i >= 2,
                     "tells": [{"name": f, "family": "intent", "score": 0.8, "applicable": True} for f in base["families"]],
                     "transcript": " ".join(["w"] * int(3 * t1)),
                     "egress": {"context": {"band_limited": base["band_limited"], "duration_s": t1,
                                            "shadow": {"snr_db": {"value": base.get("snr", 20.0)}}}}}, 0.0, t1))
    return out


def features_of(base: dict, rng: np.random.Generator) -> personal.CallFeatures:
    st, ct = live.StableTracker(), personal.CallTracker()
    for d, t0, t1 in tick_dicts(base, rng):
        s = st.observe(d, t0, t1)
        ct.update(d, s["alert"], s["tier"])
    return ct.f


def templates(rows: list[dict], rng: np.random.Generator) -> dict[str, list[dict]]:
    real = {c: [] for c in CATS}
    for r in rows:
        fam = [t["name"] for t in r["tells"] if t["family"] == "intent" and t["applicable"] and t["score"] >= 0.5
               and t["name"] in ("urgency", "payment_rails", "impersonation", "credential_ask", "secrecy")]
        b = {"p_scam": r["p_scam"], "p_ai": r["p_ai"], "disclosed": bool(r["disclosed_ai"]), "families": fam,
             "dur": float(r["ctx"].get("duration_s") or 15.0), "band_limited": bool(r["ctx"].get("band_limited"))}
        cat = "real_scam" if r["is_scam"] else "real_ai_disclosed" if r["disclosed_ai"] else "real_benign"
        real[cat].append(b)
    syn = {
        "pressure_disclosed": lambda: {"p_scam": rng.uniform(0.55, 0.75), "p_ai": 0.8, "disclosed": True,
                                       "families": ["urgency"], "dur": rng.uniform(14, 28), "band_limited": True},
        "pressure_human": lambda: {"p_scam": rng.uniform(0.50, 0.70), "p_ai": 0.2, "disclosed": False,
                                   "families": ["urgency"], "dur": rng.uniform(14, 28), "band_limited": True},
        "soft_scam": lambda: {"p_scam": rng.uniform(0.40, 0.54), "p_ai": 0.3, "disclosed": False,
                              "families": ["urgency", "impersonation"], "dur": rng.uniform(14, 28), "band_limited": True},
    }
    for c, fn in syn.items():
        real[c] = [fn() for _ in range(12)]
    return real


def pool(rows: list[dict], seed: int, k: int = 6) -> dict[str, list[personal.CallFeatures]]:
    rng = np.random.default_rng(seed)
    tmpl = templates(rows, rng)
    return {c: [features_of(b, rng) for b in tmpl[c] for _ in range(k)] for c in CATS}


def run_stream(pl: dict, persona: str, policy: str, noise: float, calls: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    mix = np.array(PERSONAS[persona], float)
    mix /= mix.sum()
    learner = None if policy == "fixed" else personal.Personal(seed=seed, learner=policy)
    fa = ms = n_neg = n_pos = alerts = 0
    fa2 = ms2 = nneg2 = npos2 = alerts2 = n2 = 0
    for i in range(calls):
        cat = CATS[int(rng.choice(len(CATS), p=mix))]
        f = pl[cat][int(rng.integers(len(pl[cat])))]
        y = WARRANTED[cat]
        level = f.max_alert if learner is None else learner.alert_level(f)
        alerted = level >= 1
        late = i >= calls // 3
        n_pos += y
        n_neg += not y
        alerts += alerted
        fa += alerted and not y
        ms += (not alerted) and y
        if late:
            n2 += 1
            npos2 += y
            nneg2 += not y
            alerts2 += alerted
            fa2 += alerted and not y
            ms2 += (not alerted) and y
        if learner is not None and rng.random() < (P_FEEDBACK_ALERTED if alerted else P_FEEDBACK_QUIET):
            said = y if rng.random() >= noise else (not y)
            learner.learn(f, "scam" if said else "not_scam")
    r = lambda a, b: a / b if b else float("nan")
    return {"fa": r(fa, n_neg), "miss": r(ms, n_pos), "per100": 100 * alerts / calls,
            "fa_late": r(fa2, nneg2), "miss_late": r(ms2, npos2), "per100_late": 100 * alerts2 / max(1, n2),
            "cost_late": 100 * (fa2 + personal.MISS_WEIGHT * ms2) / max(1, n2)}


def boot(vals: np.ndarray, n: int, rng: np.random.Generator) -> tuple[float, float, float]:
    v = vals[np.isfinite(vals)]
    if v.size == 0:
        return float("nan"), float("nan"), float("nan")
    m = [rng.choice(v, v.size).mean() for _ in range(n)]
    return float(v.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("clips")
    ap.add_argument("--streams", type=int, default=100)
    ap.add_argument("--calls", type=int, default=300)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--noise", default="0,0.1,0.2")
    ap.add_argument("--policies", default="fixed,logistic,thompson")
    a = ap.parse_args()
    rows = json.loads(Path(a.clips).read_text())
    pl = pool(rows, a.seed)
    rng = np.random.default_rng(a.seed + 1)
    print("**SIMULATED stream; one human speaker, ~39 real clip templates; borderline categories are synthesised. "
          "Not evidence about real users.**")
    print(f"streams={a.streams} x calls={a.calls} per cell; metrics are the LAST two thirds of each stream (after warm-up); "
          f"mean over streams [95% bootstrap CI over streams]\n")
    print("| persona | feedback noise | policy | false-alert rate | missed-scam rate | alerts / 100 calls | cost / 100 calls (miss x3) |")
    print("|---|---|---|---|---|---|---|")
    for persona in PERSONAS:
        for noise in [float(x) for x in a.noise.split(",")]:
            for pol in a.policies.split(","):
                res = [run_stream(pl, persona, pol, noise, a.calls, a.seed * 1000 + s) for s in range(a.streams)]
                cells = []
                for k, scale in (("fa_late", 100), ("miss_late", 100), ("per100_late", 1), ("cost_late", 1)):
                    m, lo, hi = boot(np.array([r[k] for r in res]) * scale, a.boot, rng)
                    cells.append(f"{m:.1f} [{lo:.1f}, {hi:.1f}]" + ("%" if scale == 100 else ""))
                print(f"| {persona} | {noise:g} | {pol} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
