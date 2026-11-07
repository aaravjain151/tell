"""analyze(audio_bytes, transcript) → Verdict. Pure function over inputs; no I/O except optional LLM."""
from __future__ import annotations

import os
import time

from . import audio as audio_mod, net_monitor
from . import llm, privacy, scorer
from . import audio as audio_mod
from . import llm, privacy, reasons, scorer, secure_store
from . import stt
from .signals import acoustic, intent, neural, script
from .types import Tell, Verdict


def analyze(audio_bytes: bytes | None, transcript: str | None) -> Verdict:
    """Analyse, while asking the OS (not our own counters) whether this process opened any outside connection."""
    with net_monitor.watch() as nm:
        v = _analyze(audio_bytes, transcript)
    v.egress = {**v.egress, **nm.report()}
    return v


def _analyze(audio_bytes: bytes | None, transcript: str | None) -> Verdict:
    t0 = time.perf_counter()
    ctx: dict = {}
    acoustic_tells: list[Tell] = []
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
        if os.environ.get("DOUBLESPEAK_DEBUG_SAVE") == "1":  # never in a demo; documented in skills.md
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

    v = scorer.fuse(acoustic_tells, script_tells, intent_tells, disclosed, denial, ctx)
    v.transcript = transcript
    v.reasons = reasons.build(v.tells, v.disclosed_ai)   # fixed wording from deterministic tells
    v.model_notes = notes                                # display only: never read by scorer, reasons or speak
    v.cost = {**cost, "latency_ms": int(1000 * (time.perf_counter() - t0))}
    v.egress = {**privacy.report(), "context": ctx}
    payload = {"tier": v.tier, "p_ai": round(v.p_ai, 3), "p_scam": round(v.p_scam, 3),
               "tells": [(t.name, round(t.score, 3)) for t in v.tells], "thresholds_version": v.thresholds_version}
    v.signature = privacy.sign(payload, privacy.audio_fingerprint(audio_bytes))
    secure_store.record_verdict(v)   # opt-in (DOUBLESPEAK_HISTORY=1), allowlisted fields only, never raises
    return v
