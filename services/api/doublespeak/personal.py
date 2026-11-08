"""Personal alert sensitivity: a small ON-DEVICE online learner that decides WHEN THE APP NOTIFIES, nothing else.

HONEST NAME. This is online learning (a Thompson-sampling contextual bandit over a few sensitivity arms, with an online logistic
calibration kept as the alternative the simulation compared), NOT deep reinforcement learning. A few dozen numbers, no neural net, no GPU.

WHAT IT MAY CHANGE: one extra field in the live event, `personal_alert` (none|amber|red), computed from the stabiliser's own
`stable.alert` plus a bounded per-user shift of the amber and red NOTIFICATION thresholds:
    amber shift in [AMBER_RANGE] = [-0.10, +0.15]   (+ = alert less, - = alert sooner; score units, base 0.55)
    red   shift in [RED_RANGE]   = [-0.10,  0.00]   (red can only get EASIER to reach, never harder)
WHAT IT NEVER TOUCHES: scorer.py, thresholds.py, tier, p_ai, p_scam, confidence, signature, the stored verdict, `stable` (tier,
state, alert, reasons) and the UI verdict. `stable.alert` stays authoritative for red. The two protected cases are enforced in
`decide()` (and tested): a stabiliser RED is never lowered (every red carries corroboration or p_scam >= 0.8), and on a call where
the caller disclosed nothing and payment/credential intent fired, no alert is ever lowered.

PRIVACY. Opt-in twice (env DOUBLESPEAK_PERSONAL=1 AND the user's toggle), local only, AES-256-GCM at rest through secure_store
(key in the OS keychain), holds only small numbers (weights, decayed counts), never audio, transcript, evidence or call content,
never uploaded or shared (no network code here), wiped by `wipe()` / DELETE /personal.

THE LEARNER. Feedback labels ('scam' | 'not_scam' | 'ai' | 'human') become a binary "was an alert warranted on this call"
(`warranted()`); 'ai' on an already-disclosed call carries no information. Two learners update on each label:
  * logistic (the alternative): q = sigmoid(w_s*logit(score)+w_o.x+b)
    started at q = score (w_s=1, rest 0) and pulled back to that start by L2; the amber threshold on `score` is where q crosses the
    base 0.55, so with no feedback the shift is exactly 0.
  * thompson (DEFAULT, lower miss-weighted cost in 9 of 9 simulated cells, intervals separated in 3, see docs/PERSONAL-LEARNING.md): per call-profile Beta posteriors over a small set of shift ARMS, sampled once per update with a seeded RNG;
    posterior is decayed toward its prior. It sees the full label for every arm (counterfactual replay), so this is a Bayesian
    arm-weighting bandit with full information, not a partial-feedback bandit.
PRIOR (part b): per call profile (e.g. "automated and said so, no payment words") a decayed count of confirmed-scam vs not; its
shrunken rate adds a small extra shift. Every update multiplies old counts by DECAY, so old feedback fades.

Deterministic given the seed, serialisable (`to_json`/`from_json`), bounded by construction (`clip` at every output).
"""
from __future__ import annotations

import json
import math
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

import numpy as np

from . import secure_store, thresholds

VERSION = "personal-v1"
STATE_FILE = "personal_state.enc"

AMBER_BASE = thresholds.P_SCAM_THRESHOLD          # 0.55: the score at which the amber notification fires with no shift
RED_BASE = 0.80                                   # stabiliser.StabiliserConfig.red_p_scam_threshold
AMBER_RANGE = (-0.10, 0.15)
RED_RANGE = (-0.10, 0.0)
PRIOR_SHIFT_RANGE = (-0.03, 0.05)
ARMS = (-0.10, -0.05, 0.0, 0.05, 0.10, 0.15)
CONTEXTS = ("disclosed_benign", "disclosed_pressure", "undisclosed_ai", "pressure_human", "other")
DECAY = 0.97                                      # per feedback event; half-life about 23 events
MIN_FEEDBACK = 5                                  # below this nothing is shown as "learned"
MISS_WEIGHT = 3.0                                 # a missed scam counts three times a false alert
LEARNERS = ("logistic", "thompson")
DEFAULT_LEARNER = "thompson"
PAYMENT_CRED = frozenset({"payment_rails", "credential_ask"})
LEVEL = {"none": 0, "amber": 1, "red": 2}
NAME = {0: "none", 1: "amber", 2: "red"}
LABELS = ("scam", "not_scam", "ai", "human")
LEARN_RATE, L2 = 0.15, 0.05
PROMOTABLE_TIERS = ("scam", "ai_undisclosed", "unsure")

FEATURE_NAMES = ("p_ai", "p_scam", "peak_scam", "peak_ai_undisclosed", "max_alert", "n_families", "payment_cred",
                 "disclosed", "band_limited", "snr_db", "bandwidth_hz", "noise_floor_std_db", "gate_transitions_per_min",
                 "duration_bucket")

EXPLAIN_TOPIC = {
    "disclosed_benign": "automated appointment calls that say they are automated",
    "disclosed_pressure": "automated calls that say they are automated but mention payment or codes",
    "undisclosed_ai": "calls where the voice sounds synthetic and the caller did not say so",
    "pressure_human": "calls from a person who mentions urgency or money",
    "other": "other calls",
}
EXPLAIN_LESS = "Doublespeak has learned to alert you slightly less for {}."
EXPLAIN_SOONER = "Doublespeak has learned to alert you slightly sooner for {}."
EXPLAIN_RED = "Doublespeak has learned to raise a red alert slightly sooner when a call you reported as a scam looks like this one."
EXPLAIN_LEARNING = "Doublespeak is still learning from your feedback and has not changed anything yet."
EXPLAIN_ALWAYS = ("This only changes when you are notified. It never changes what a call is judged to be, "
                  "and a strong scam alert is always shown.")
EXPLAIN_OFF = "Personal learning is off. Nothing is being learned or stored."
SHOW_AT = 0.03


def clip(x: float, lo: float, hi: float) -> float:
    return float(min(hi, max(lo, x)))


def _logit(p: float) -> float:
    p = clip(p, 0.02, 0.98)
    return math.log(p / (1 - p))


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-clip(z, -30.0, 30.0)))


# ---------------------------------------------------------------------------------------------------------- features
def duration_bucket(seconds: float | None) -> int:
    s = float(seconds or 0.0)
    return 0 if s < 30 else 1 if s < 120 else 2


@dataclass
class CallFeatures:
    """The per-call vector. Numbers and booleans only; built from an allowlist, never from text."""
    p_ai: float = 0.0
    p_scam: float = 0.0
    peak_scam: float = 0.0               # highest p_scam on any tick
    peak_ai_undisclosed: float = 0.0     # highest p_ai on any tick while the caller had disclosed nothing
    max_alert: int = 0                   # highest stable.alert level on the call (0 none, 1 amber, 2 red)
    n_families: int = 0                  # intent families that fired (stabiliser evidence), 0..5
    payment_cred: bool = False
    disclosed: bool = False
    band_limited: float = 0.0
    snr_db: float = 0.0                  # shadow cues, latest values; 0.0 when unavailable
    bandwidth_hz: float = 0.0
    noise_floor_std_db: float = 0.0
    gate_transitions_per_min: float = 0.0
    duration_s: float = 0.0
    promotable: bool = False             # shown tier was scam / ai_undisclosed / unsure after warm-up on some tick

    @property
    def protected(self) -> bool:
        """The caller disclosed nothing and payment/credential intent fired: alerts are never lowered."""
        return self.payment_cred and not self.disclosed

    @property
    def score(self) -> float:
        return max(self.peak_scam, self.peak_ai_undisclosed)

    def vector(self) -> list[float]:
        return [self.p_ai, self.p_scam, self.peak_scam, self.peak_ai_undisclosed, float(self.max_alert), float(self.n_families),
                float(self.payment_cred), float(self.disclosed), self.band_limited, self.snr_db, self.bandwidth_hz,
                self.noise_floor_std_db, self.gate_transitions_per_min, float(duration_bucket(self.duration_s))]

    def context(self) -> str:
        if self.disclosed:
            return "disclosed_pressure" if self.payment_cred else "disclosed_benign"
        if self.p_ai >= thresholds.P_AI_THRESHOLD or self.peak_ai_undisclosed >= thresholds.P_AI_THRESHOLD:
            return "undisclosed_ai"
        if self.n_families >= 1 or self.peak_scam >= 0.30:
            return "pressure_human"
        return "other"

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, d: dict) -> "CallFeatures":
        return cls(**{k: type(getattr(cls(), k))(d[k]) for k in cls.__dataclass_fields__ if k in d})


def _shadow_value(d: dict, key: str) -> float:
    try:
        v = (((d.get("egress") or {}).get("context") or {}).get("shadow") or {}).get(key)
        v = v.get("value") if isinstance(v, dict) else v
        return float(v) if v is not None and math.isfinite(float(v)) else 0.0
    except (TypeError, ValueError):
        return 0.0


class CallTracker:
    """One per live call. Accumulates the feature vector from raw tick dicts + the stabiliser's own alert. Pure."""

    def __init__(self) -> None:
        self.f = CallFeatures()
        self._families: set[str] = set()
        self.ticks = 0

    def update(self, d: dict, stable_alert: str, shown_tier: str) -> CallFeatures:
        f = self.f
        self.ticks += 1
        p_ai, p_scam = float(d.get("p_ai") or 0.0), float(d.get("p_scam") or 0.0)
        f.p_ai, f.p_scam = p_ai, p_scam
        f.disclosed = f.disclosed or bool(d.get("disclosed_ai"))
        f.peak_scam = max(f.peak_scam, p_scam)
        if not f.disclosed:
            f.peak_ai_undisclosed = max(f.peak_ai_undisclosed, p_ai)
        for t in d.get("tells") or []:
            if (t.get("family") == "intent" and t.get("applicable", True) and float(t.get("score", 0)) >= 0.5
                    and t.get("name") in {"urgency", "payment_rails", "impersonation", "credential_ask", "secrecy"}):
                self._families.add(t["name"])
        f.n_families = len(self._families)
        f.payment_cred = bool(self._families & PAYMENT_CRED)
        f.max_alert = max(f.max_alert, LEVEL.get(stable_alert, 0))
        ctx = (d.get("egress") or {}).get("context") or {}
        f.band_limited = 1.0 if ctx.get("band_limited") else f.band_limited
        f.duration_s = max(f.duration_s, float(ctx.get("duration_s") or 0.0))
        for k in ("snr_db", "bandwidth_hz", "noise_floor_std_db", "gate_transitions_per_min"):
            v = _shadow_value(d, k)
            if v:
                setattr(f, k, v)
        if shown_tier in PROMOTABLE_TIERS:
            f.promotable = True
        return f


# ---------------------------------------------------------------------------------------------------------- decision
def decide(level: int, score: float, p_scam: float, protected: bool, promotable: bool,
           amber_shift: float, red_shift: float) -> int:
    """The ONLY place a personal alert level is computed. `level` is the stabiliser's alert (0/1/2); the result is 0/1/2.

    * level 2 (red) is returned unchanged: never suppressed (every stabiliser red is corroborated or p_scam >= 0.8).
    * amber is dropped only when the shift is positive, the call is not `protected`, and score < AMBER_BASE + shift.
    * a missing alert is raised to amber only when the shift is negative, the shown tier is promotable and
      score >= AMBER_BASE + shift.
    * amber becomes red only when the red shift is negative and p_scam >= RED_BASE + red_shift.
    Shifts are re-clipped here, so even a corrupted state cannot exceed the documented range."""
    a = clip(amber_shift, *AMBER_RANGE)
    r = clip(red_shift, *RED_RANGE)
    if level >= 2:
        return 2
    out = level
    if out == 1 and a > 0 and not protected and score < AMBER_BASE + a:
        out = 0
    elif out == 0 and a < 0 and promotable and score >= AMBER_BASE + a:
        out = 1
    if out == 1 and r < 0 and p_scam >= RED_BASE + r:
        out = 2
    if protected:
        out = max(out, level)
    return out


def call_level(f: CallFeatures, amber_shift: float, red_shift: float) -> int:
    return decide(f.max_alert, f.score, f.peak_scam, f.protected, f.promotable, amber_shift, red_shift)


def warranted(label: str, f: CallFeatures) -> bool | None:
    """Map a feedback label to 'an alert was warranted on this call'; None = carries no information."""
    if label == "scam":
        return True
    if label in ("not_scam", "human"):
        return False
    if label == "ai":
        return None if f.disclosed else True
    return None


# ---------------------------------------------------------------------------------------------------------- learner
def _x_other(f: CallFeatures) -> list[float]:
    """Context inputs of the logistic (beside the score): small, roughly 0..1 scaled."""
    return [float(f.disclosed), float(f.payment_cred), f.n_families / 3.0, f.band_limited,
            0.0 if f.disclosed else f.peak_ai_undisclosed, duration_bucket(f.duration_s) / 2.0]


N_OTHER = 6


class Personal:
    """The pure learner state (no IO). `learner` picks which part drives the amber shift."""

    def __init__(self, seed: int = 0, learner: str = DEFAULT_LEARNER) -> None:
        if learner not in LEARNERS:
            raise ValueError("unknown learner")
        self.seed, self.learner = int(seed), learner
        self.enabled = False
        self.n_feedback = 0
        self.w = [1.0] + [0.0] * N_OTHER          # w[0] on logit(score)
        self.b = 0.0
        self.beta = {c: [[3.0, 2.0] if a == 0.0 else [2.0, 2.0] for a in ARMS] for c in CONTEXTS}
        self.chosen = {c: ARMS.index(0.0) for c in CONTEXTS}
        self.prior = {c: [0.0, 0.0] for c in CONTEXTS}      # decayed [warranted weight, total weight]
        self.red_stat = [0.0, 0.0]                           # decayed [scam, total] over amber-only calls with high p_scam
        self.seen: list[str] = []

    # --- shifts (always bounded) -------------------------------------------------------------------------------
    def _logistic_shift(self, f: CallFeatures) -> float:
        o = sum(wi * xi for wi, xi in zip(self.w[1:], _x_other(f))) + self.b
        ws = max(0.5, self.w[0])
        s_star = _sigmoid((_logit(AMBER_BASE) - o) / ws)
        return s_star - AMBER_BASE

    def prior_shift(self, ctx: str) -> float:
        w, n = self.prior[ctx]
        rate = (w + 1.0) / (n + 2.0)
        return clip(0.3 * (0.5 - rate), *PRIOR_SHIFT_RANGE)

    def amber_shift(self, f: CallFeatures) -> float:
        base = self._logistic_shift(f) if self.learner == "logistic" else ARMS[self.chosen[f.context()]]
        return clip(base + self.prior_shift(f.context()), *AMBER_RANGE)

    def red_shift(self) -> float:
        w, n = self.red_stat
        if n < 3.0:
            return 0.0
        rate = (w + 1.0) / (n + 2.0)
        return clip(RED_RANGE[0] * clip((rate - 0.5) / 0.5, 0.0, 1.0), *RED_RANGE)

    def shifts_for(self, f: CallFeatures) -> tuple[float, float]:
        return self.amber_shift(f), self.red_shift()

    def alert_level(self, f: CallFeatures) -> int:
        return call_level(f, *self.shifts_for(f))

    # --- learning ------------------------------------------------------------------------------------------------
    def learn(self, f: CallFeatures, label: str) -> bool:
        """One feedback label on one call. Returns True when it carried information."""
        if label not in LABELS:
            return False
        self.n_feedback += 1
        y = warranted(label, f)
        ctx = f.context()
        for c in CONTEXTS:                                  # old feedback fades
            self.prior[c][0] *= DECAY
            self.prior[c][1] *= DECAY
        self.red_stat[0] *= DECAY
        self.red_stat[1] *= DECAY
        if y is None:
            return False
        self.prior[ctx][0] += 1.0 if y else 0.0
        self.prior[ctx][1] += 1.0
        if f.max_alert == 1 and f.peak_scam >= 0.7 and label in ("scam", "not_scam"):
            self.red_stat[0] += 1.0 if y else 0.0
            self.red_stat[1] += 1.0
        self._logistic_step(f, 1.0 if y else 0.0)
        self._thompson_step(f, ctx, bool(y))
        return True

    def _logistic_step(self, f: CallFeatures, y: float) -> None:
        x = [_logit(f.score)] + _x_other(f)
        q = _sigmoid(sum(wi * xi for wi, xi in zip(self.w, x)) + self.b)
        sw = MISS_WEIGHT if y == 1.0 else 1.0
        g = sw * (q - y)
        w0 = [1.0] + [0.0] * N_OTHER
        for i in range(len(self.w)):
            self.w[i] -= LEARN_RATE * (g * x[i] + L2 * (self.w[i] - w0[i]))
        self.b -= LEARN_RATE * (g + L2 * self.b)
        self.w[0] = clip(self.w[0], 0.5, 3.0)
        self.w[1:] = [clip(v, -3.0, 3.0) for v in self.w[1:]]
        self.b = clip(self.b, -3.0, 3.0)

    def _thompson_step(self, f: CallFeatures, ctx: str, y: bool) -> None:
        post = self.beta[ctx]
        for i, a in enumerate(ARMS):
            alerted = call_level(f, a, 0.0) >= 1
            pa, pb = (3.0, 2.0) if a == 0.0 else (2.0, 2.0)
            post[i][0] = pa + DECAY * (post[i][0] - pa)
            post[i][1] = pb + DECAY * (post[i][1] - pb)
            if alerted == y:
                post[i][0] += 1.0
            else:
                post[i][1] += MISS_WEIGHT if (y and not alerted) else 1.0
        rng = np.random.default_rng([self.seed, self.n_feedback, CONTEXTS.index(ctx)])
        draws = [rng.beta(a, b) for a, b in post]
        self.chosen[ctx] = int(np.argmax(draws))

    # --- explanation ---------------------------------------------------------------------------------------------
    def explain(self) -> list[str]:
        if self.n_feedback < MIN_FEEDBACK:
            return [EXPLAIN_LEARNING, EXPLAIN_ALWAYS]
        out = []
        for c in CONTEXTS:
            shift = self.context_shift(c)
            if shift >= SHOW_AT:
                out.append(EXPLAIN_LESS.format(EXPLAIN_TOPIC[c]))
            elif shift <= -SHOW_AT:
                out.append(EXPLAIN_SOONER.format(EXPLAIN_TOPIC[c]))
        if self.red_shift() <= -SHOW_AT:
            out.append(EXPLAIN_RED)
        if not out:
            out.append(EXPLAIN_LEARNING)
        out.append(EXPLAIN_ALWAYS)
        return out

    def context_shift(self, ctx: str) -> float:
        """Representative amber shift for a call profile (typical borderline call), for display."""
        f = {"disclosed_benign": CallFeatures(p_ai=0.8, p_scam=0.6, peak_scam=0.6, disclosed=True),
             "disclosed_pressure": CallFeatures(p_ai=0.8, p_scam=0.6, peak_scam=0.6, disclosed=True, payment_cred=True, n_families=1),
             "undisclosed_ai": CallFeatures(p_ai=0.7, peak_ai_undisclosed=0.7),
             "pressure_human": CallFeatures(p_ai=0.2, p_scam=0.6, peak_scam=0.6, n_families=1),
             "other": CallFeatures(p_ai=0.2, p_scam=0.3, peak_scam=0.3)}[ctx]
        return self.amber_shift(f)

    def sensitivity(self) -> dict:
        return {"amber": {c: round(self.context_shift(c), 3) for c in CONTEXTS}, "red": round(self.red_shift(), 3),
                "amber_range": list(AMBER_RANGE), "red_range": list(RED_RANGE), "learner": self.learner}

    # --- serialisation -------------------------------------------------------------------------------------------
    def to_json(self) -> str:
        return json.dumps({"v": VERSION, "seed": self.seed, "learner": self.learner, "enabled": self.enabled,
                           "n": self.n_feedback, "w": self.w, "b": self.b, "beta": self.beta, "chosen": self.chosen,
                           "prior": self.prior, "red": self.red_stat, "seen": self.seen[-200:]}, sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "Personal":
        d = json.loads(s)
        if d.get("v") != VERSION:
            raise ValueError("unknown personal state version")
        p = cls(int(d["seed"]), d["learner"])
        p.enabled, p.n_feedback = bool(d["enabled"]), int(d["n"])
        p.w = [float(x) for x in d["w"]][: N_OTHER + 1]
        p.b = float(d["b"])
        p.beta = {c: [[float(a), float(b)] for a, b in d["beta"][c]] for c in CONTEXTS}
        p.chosen = {c: int(d["chosen"][c]) % len(ARMS) for c in CONTEXTS}
        p.prior = {c: [float(a), float(b)] for c, (a, b) in ((c, d["prior"][c]) for c in CONTEXTS)}
        p.red_stat = [float(x) for x in d["red"]]
        p.seen = [str(x) for x in d.get("seen", [])]
        return p


# ---------------------------------------------------------------------------------------------------------- feedback intake
class FeedbackSource(Protocol):
    def recent(self, n: int) -> list[dict]: ...


class FakeFeedback:
    """Test/dev stand-in for doublespeak.feedback (owned by the feat/block-spam branch). Records are dicts:
    {"id"?: str, "call_id"?: str|None, "label": 'scam'|'not_scam'|'ai'|'human', "tick"?: int, "ts"?: float}, newest LAST."""

    def __init__(self, records: Iterable[dict] = ()) -> None:
        self.records = list(records)

    def recent(self, n: int) -> list[dict]:
        return self.records[-n:]


def feedback_adapter() -> FeedbackSource:
    """Thin adapter over the real store. Until doublespeak/feedback.py (`recent(n)`) lands this returns an empty fake, so the
    personal layer is inert instead of failing. If the real module returns newest-first, it is reversed here to oldest-first."""
    try:
        from . import feedback as _fb          # type: ignore[attr-defined]  # may not exist yet
    except ImportError:
        return FakeFeedback()

    class _Real:
        def recent(self, n: int) -> list[dict]:
            recs = list(_fb.recent(n))
            if len(recs) > 1 and recs[0].get("ts", 0) > recs[-1].get("ts", 0):
                recs.reverse()
            return [dict(r) for r in recs]

    return _Real()


def _record_key(r: dict) -> str:
    return str(r.get("id") or f"{r.get('ts')}|{r.get('call_id')}|{r.get('label')}|{r.get('tick')}")


# ---------------------------------------------------------------------------------------------------------- the layer (IO)
def env_on() -> bool:
    return os.environ.get("DOUBLESPEAK_PERSONAL") == "1"


def state_path() -> Path:
    return secure_store.data_dir() / STATE_FILE


class PersonalLayer:
    """Wires the learner to disk (encrypted), the live tick path and the feedback store. Thread-safe."""

    RECENT_MAX = 50

    def __init__(self, key_provider: Callable[[], bytes] | None = None, feedback: FeedbackSource | None = None,
                 seed: int | None = None) -> None:
        self._kp = key_provider
        self._fb = feedback
        self._seed = seed
        self._lock = threading.RLock()
        self._p: Personal | None = None
        self._unavailable = ""
        self.calls: "OrderedDict[str, CallFeatures]" = OrderedDict()   # in-memory only: recent finished calls, numbers only
        self._order: list[str] = []

    # --- storage -------------------------------------------------------------------------------------------------
    def _key(self) -> bytes:
        return (self._kp or secure_store.keyring_key_provider)()

    def _load(self) -> Personal:
        if self._p is not None:
            return self._p
        seed = self._seed if self._seed is not None else int.from_bytes(os.urandom(4), "big")
        p = Personal(seed)
        path = state_path()
        try:
            if path.exists():
                p = Personal.from_json(secure_store._decrypt(self._key(), path.read_text(encoding="ascii")).decode("utf-8"))
        except secure_store.HistoryUnavailable as e:
            self._unavailable = str(e)
        except Exception:  # noqa: BLE001  corrupt/tampered state: start clean rather than act on it
            p = Personal(seed)
        self._p = p
        return p

    def _save(self) -> None:
        p = self._p
        if p is None:
            return
        try:
            line = secure_store._encrypt(self._key(), p.to_json().encode("utf-8"))
            secure_store._ensure_dir()
            tmp = state_path().with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.fchmod(fd, 0o600)
                os.write(fd, line.encode("ascii"))
            finally:
                os.close(fd)
            os.replace(tmp, state_path())
            self._unavailable = ""
        except secure_store.HistoryUnavailable as e:
            self._unavailable = str(e)
        except OSError:
            self._unavailable = "state could not be written"

    # --- public contract -----------------------------------------------------------------------------------------
    def active(self) -> bool:
        """True only when the env flag is on AND the user switched it on. Reads nothing from disk when the flag is off."""
        if not env_on():
            return False
        with self._lock:
            return self._load().enabled and not self._unavailable

    def set_enabled(self, on: bool) -> dict:
        with self._lock:
            if not env_on():
                return self.status()
            p = self._load()
            if on:
                try:
                    self._key()
                except secure_store.HistoryUnavailable as e:
                    self._unavailable = str(e)
                    return self.status()
            p.enabled = bool(on)
            self._save()
            return self.status()

    def wipe(self) -> dict:
        with self._lock:
            try:
                state_path().unlink()
            except FileNotFoundError:
                pass
            self._p = None
            self.calls.clear()
            self._order.clear()
            self._unavailable = ""
            return {"wiped": True}

    def status(self) -> dict:
        with self._lock:
            if not env_on():
                return {"enabled": False, "available": False, "n_feedback": 0, "sensitivity": None, "explain": [EXPLAIN_OFF]}
            p = self._load()
            if not p.enabled:
                return {"enabled": False, "available": not self._unavailable, "n_feedback": p.n_feedback,
                        "sensitivity": None, "explain": [EXPLAIN_OFF]}
            self.sync()
            return {"enabled": True, "available": not self._unavailable, "n_feedback": p.n_feedback,
                    "sensitivity": p.sensitivity(), "explain": p.explain()}

    # --- live path -----------------------------------------------------------------------------------------------
    def on_tick(self, tracker: CallTracker, d: dict, stable_alert: str, shown_tier: str) -> str | None:
        """-> 'none'|'amber'|'red' when active, else None (callers then add NO field, keeping events bit-identical)."""
        if not self.active():
            return None
        with self._lock:
            f = tracker.update(d, stable_alert, shown_tier)
            a, r = self._load().shifts_for(f)
            p_scam, p_ai = float(d.get("p_scam") or 0.0), float(d.get("p_ai") or 0.0)   # this tick's scores
            score = max(p_scam, 0.0 if f.disclosed else p_ai)
            return NAME[decide(LEVEL.get(stable_alert, 0), score, p_scam, f.protected, shown_tier in PROMOTABLE_TIERS, a, r)]

    def on_call_end(self, tracker: CallTracker | None, call_id: str | None = None) -> None:
        if tracker is None or tracker.ticks == 0 or not self.active():
            return
        with self._lock:
            cid = call_id or f"call-{len(self._order) + 1}"
            self.calls[cid] = tracker.f
            self._order.append(cid)
            while len(self.calls) > self.RECENT_MAX:
                self.calls.popitem(last=False)
            self.sync()

    # --- feedback ------------------------------------------------------------------------------------------------
    def sync(self) -> int:
        """Pull new feedback records and learn from each. A record with a known call_id uses that call; otherwise it is
        attributed to the most recent finished call (assumption: feedback follows the call). Returns labels learned."""
        with self._lock:
            if not env_on():
                return 0
            p = self._load()
            if not p.enabled:
                return 0
            src = self._fb if self._fb is not None else feedback_adapter()
            try:
                recs = src.recent(100)
            except Exception:  # noqa: BLE001  a broken feedback store must not break a call
                return 0
            learned = 0
            for r in recs:
                key = _record_key(r)
                if key in p.seen:
                    continue
                f = self.calls.get(str(r.get("call_id"))) if r.get("call_id") else None
                if f is None and self._order and self.calls:
                    f = self.calls.get(self._order[-1])
                if f is None:
                    continue
                p.seen.append(key)
                learned += int(p.learn(f, str(r.get("label"))))
            if learned:
                p.seen = p.seen[-200:]
                self._save()
            return learned


LAYER = PersonalLayer()


# ---------------------------------------------------------------------------------------------------------- HTTP contract
from fastapi import APIRouter, HTTPException, Request  # noqa: E402
from pydantic import BaseModel  # noqa: E402

router = APIRouter()
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}   # "testclient" is Starlette's TestClient only


class _Toggle(BaseModel):
    enabled: bool


def _loopback_only(request: Request) -> None:
    """Origin/Host are already enforced for every route by limits.GuardMiddleware; this adds the client-address check."""
    host = request.client.host if request.client else ""
    if host not in _LOOPBACK:
        raise HTTPException(403, "loopback only")


@router.get("/personal")
def personal_get(request: Request) -> dict:
    _loopback_only(request)
    return LAYER.status()


@router.post("/personal")
def personal_set(body: _Toggle, request: Request) -> dict:
    _loopback_only(request)
    return LAYER.set_enabled(body.enabled)


@router.delete("/personal")
def personal_wipe(request: Request) -> dict:
    _loopback_only(request)
    return LAYER.wipe()
