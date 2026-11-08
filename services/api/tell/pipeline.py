"""analyze(audio_bytes, transcript) → Verdict. Pure function over inputs; no I/O except optional LLM."""
from __future__ import annotations

import logging
import os
import time

from . import env as _env
from . import audio as audio_mod, net_monitor
from . import llm, privacy, scorer
from . import audio as audio_mod
from . import llm, privacy, reasons, scorer, secure_store
from . import stt
from .signals import acoustic, intent, neural, script, shadow
from .types import Tell, Verdict


_debug_warned = False


def _warn_debug_save_once() -> None:
    global _debug_warned
    if not _debug_warned:
        _debug_warned = True
        logging.getLogger("tell.pipeline").warning(
            "TELL_DEBUG_SAVE=1: RAW CALLER AUDIO IS BEING WRITTEN TO data/debug. Never use this in a demo or with real calls.")


VOICE_WINDOW_CAP = 60


def voice_windows(tells: list[Tell]) -> list[dict]:
    """DISPLAY ONLY: merge per-window voice scores from the neural voters by window start time (seconds).
    Returns [{"t":.., "pella":.., "hf":.., "learned":..}] ordered by t (a key is absent when that voter did not score that start), at most 60 points."""
    keys = {"neural_pella": "pella", "neural_hf": "hf", "learned_tells": "learned"}
    merged: dict[float, dict] = {}
    for t in tells:
        k = keys.get(t.name)
        if not (k and t.applicable and t.detail):
            continue
        for w in t.detail.get("windows") or []:
            try:
                start, p = round(float(w["t"]), 2), round(float(w["p"]), 3)
            except (KeyError, TypeError, ValueError):
                continue
            merged.setdefault(start, {"t": start})[k] = p
    pts = [merged[s] for s in sorted(merged)]
    if len(pts) > VOICE_WINDOW_CAP:
        step = (len(pts) - 1) / (VOICE_WINDOW_CAP - 1)
        pts = [pts[round(i * step)] for i in range(VOICE_WINDOW_CAP)]
    return pts


def analyze(audio_bytes: bytes | None, transcript: str | None, *, ephemeral: bool = False) -> Verdict:
    """Analyse, while asking the OS (not our own counters) whether this process opened any outside connection.

    `ephemeral=True` is for live streaming ticks: TELL_DEBUG_SAVE is ignored (no audio ever reaches disk)
    and the opt-in history file is not written (a tick every 3 s would flood it)."""
    with net_monitor.watch() as nm:
        v = _analyze(audio_bytes, transcript, ephemeral)
    v.egress = {**v.egress, **nm.report()}
    return v


def _analyze(audio_bytes: bytes | None, transcript: str | None, ephemeral: bool = False) -> Verdict:
    t0 = time.perf_counter()
    ctx: dict = {}
    acoustic_tells: list[Tell] = []
    x = None
    if audio_bytes:
        x, orig_sr, dur_ms = audio_mod.decode(audio_bytes)
        ctx["original_sample_rate"] = orig_sr
        acoustic_tells, actx = acoustic.analyze(x, dur_ms)
        ctx.update(actx)
        acoustic_tells += neural.analyze(x, dur_ms / 1000)
        if not (transcript or "").strip():
            local, src = stt.transcribe_with_source(x)   # VoiceStudio (loopback) → local whisper → None
            if local:
                transcript = local
                ctx["transcript_source"] = src
        if _env.get("TELL_DEBUG_SAVE") == "1" and not ephemeral:  # never in a demo; documented in skills.md
            _warn_debug_save_once()
            os.makedirs("data/debug", exist_ok=True)
            with open(f"data/debug/{privacy.audio_fingerprint(audio_bytes)}.bin", "wb") as f:
                f.write(audio_bytes)

    transcript = (transcript or "").strip()
    script_tells = script.analyze(transcript)
    intent_tells, disclosed = intent.detect(transcript)
    extra, cost = llm.interpret(transcript)
    notes = list(cost.pop("notes", []) or [])   # display only, see Verdict.model_notes
    for t in extra:
        (script_tells if t.family == "script" else intent_tells).append(t)
        # An LLM `ai_disclosure` tell is shown (applicable=False) but never decides: disclosure comes only from the
        # deterministic detector (intent.DISCLOSURE). A hallucinating 3B model must not be able to flip the tier.
    denial = script.ai_denial(transcript) if transcript else False

    vw = voice_windows(acoustic_tells)
    if vw:
        ctx["voice_windows"] = vw   # display only: nothing reads it back into a tier or score
    v = scorer.fuse(acoustic_tells, script_tells, intent_tells, disclosed, denial, ctx)
    if x is not None:
        # SHADOW layers: logged only, added AFTER fusion and outside the signed payload; nothing reads them back.
        ctx["shadow"] = shadow.compute_all(x, vw)
    v.transcript = transcript
    v.reasons = reasons.build(v.tells, v.disclosed_ai, v.p_ai)   # fixed wording from deterministic tells
    v.model_notes = notes                                # display only: never read by scorer, reasons or speak
    v.cost = {**cost, "latency_ms": int(1000 * (time.perf_counter() - t0))}
    v.egress = {**privacy.report(), "context": ctx}
    payload = {"tier": v.tier, "p_ai": round(v.p_ai, 3), "p_scam": round(v.p_scam, 3),
               "tells": [(t.name, round(t.score, 3)) for t in v.tells], "thresholds_version": v.thresholds_version}
    v.signature = privacy.sign(payload, privacy.audio_fingerprint(audio_bytes))
    if not ephemeral:
        secure_store.record_verdict(v)   # opt-in (TELL_HISTORY=1), allowlisted fields only, never raises
    return v
