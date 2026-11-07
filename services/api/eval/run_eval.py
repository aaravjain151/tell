#!/usr/bin/env python3
"""Golden eval. Transcript cases from eval/golden.jsonl (+ synthetic audio pairs).

    python3 eval/run_eval.py            # summary
    python3 eval/run_eval.py --verbose  # every miss with the tells that fired

Target: transcript 4-tier accuracy >= 0.85; synthetic audio human-vs-TTS >= 0.90.
Transcript-only cases have no acoustic evidence, so "ai_undisclosed" relies on script tells alone;
that's the hard part of this eval and the reason the number isn't 1.0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("LLM_PROVIDER", "stub")

from doublespeak import pipeline  # noqa: E402
from tests.synth import make_call, to_wav_bytes  # noqa: E402

TARGET_TRANSCRIPT = 0.85
TARGET_AUDIO = 0.90


def run_transcripts(verbose: bool) -> float:
    cases = [json.loads(l) for l in (HERE / "golden.jsonl").read_text().splitlines() if l.strip()]
    hits, conf = 0, Counter()
    for c in cases:
        v = pipeline.analyze(None, c["transcript"])
        got = v.tier
        # transcript-only: an "unsure" on a human/ai case counts half (we'd rather say unsure than wrong)
        ok = got == c["expected"]
        hits += 1 if ok else (0.5 if got == "unsure" and c["expected"] != "scam" else 0)
        conf[(c["expected"], got)] += 1
        if verbose and not ok:
            fired = [f"{t.name}={t.score:.2f}" for t in v.tells if t.applicable and t.score >= 0.5]
            print(f"MISS {c['id']}: expected {c['expected']}, got {got} (p_ai {v.p_ai:.2f}, p_scam {v.p_scam:.2f}, conf {v.confidence:.2f})\n     {fired}")
    acc = hits / len(cases)
    print(f"transcript eval: {acc:.2f} over {len(cases)} cases (target {TARGET_TRANSCRIPT})")
    for (exp, got), n in sorted(conf.items()):
        if exp != got:
            print(f"   {exp} → {got}: {n}")
    return acc


def run_audio(verbose: bool) -> float:
    n, hits = 0, 0
    for seed in range(12):
        for kind in ("human", "tts"):
            for pb in (False, True):
                v = pipeline.analyze(to_wav_bytes(make_call(kind, seed=seed, phone_band=pb)), None)
                want_ai = kind == "tts"
                ok = (v.p_ai >= 0.6) == want_ai
                n += 1
                hits += ok
                if verbose and not ok:
                    print(f"MISS audio seed={seed} {kind} phone={pb}: p_ai {v.p_ai:.2f}")
    acc = hits / n
    print(f"synthetic audio eval: {acc:.2f} over {n} clips (target {TARGET_AUDIO})")
    return acc


# Engines whose output the HF anti-spoof checkpoint was TRAINED on: scores there are in-domain, not a fair held-out test.
IN_DOMAIN = {"elevenlabs": "garystafford/wav2vec2-deepfake-voice-detector was trained on ElevenLabs output"}


def _engine(rel: Path, base: str) -> str:
    """Engine = folder under the wild dir (data/calls/<engine>/x.wav), else ai__<engine>__<script> in the filename."""
    if len(rel.parts) > 1 and rel.parts[0] != "human":
        return rel.parts[0]
    parts = base.split("__")
    return parts[1] if parts[0] == "ai" and len(parts) >= 3 else "other"


def _label(rel: Path, base: str) -> str:
    return "human" if "human" in rel.parts[:-1] or base.startswith("human") else "ai"


def _condition(stem: str) -> tuple[str, str]:
    """('clean'|'opus-8k', base stem)."""
    return ("opus-8k", stem[: -len(".opus8k")]) if stem.endswith(".opus8k") else ("clean", stem)


def _transcript(wav: Path, base: str) -> str | None:
    """Same text for human and AI readings of one script, so the comparison isolates the voice."""
    root = HERE.parents[2] / "tools" / "redteam" / "scripts"
    sib = wav.with_suffix(".txt")
    if sib.exists():
        return sib.read_text().strip()
    names = sorted((p.stem for p in root.glob("*.txt")), key=len, reverse=True)
    hay = "__".join([base, *wav.parent.parts[-2:]])          # script name may sit in the filename or a folder
    for n in names:
        if n in hay:
            return (root / f"{n}.txt").read_text().strip()
    return None


def _f(x: float | None, nd: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def run_wild(folder: str, verbose: bool) -> None:
    """Per-condition AUC / EER / FPR@90%TPR for p_ai on real recordings, plus each generator held out in turn.

    Layout: <folder>/<engine>/<script>.wav (AI) · <folder>/human/**.wav (human) · <stem>.opus8k.wav from
    tools/redteam/degrade.sh. Flat names `ai__<engine>__<script>.wav` / `human__<speaker>__<script>.wav` also work.
    """
    from eval.metrics import auc, eer, fpr_at_tpr, loeo
    from doublespeak.thresholds import P_AI_THRESHOLD, THRESHOLDS_VERSION
    root = Path(folder)
    rows: dict[str, list[dict]] = {}
    for wav in sorted(root.rglob("*.wav")):
        rel = wav.relative_to(root)
        cond, base = _condition(wav.stem)
        v = pipeline.analyze(wav.read_bytes(), _transcript(wav, base))
        fired = [f"{t.name}={t.score:.2f}" for t in v.tells if t.applicable and t.score >= 0.5]
        rows.setdefault(cond, []).append({"name": str(rel), "label": _label(rel, base), "engine": _engine(rel, base),
                                          "p_ai": v.p_ai, "tier": v.tier, "fired": fired})
    if not rows:
        print(f"no .wav clips under {folder} (make redteam ARGS='--engine all' / record humans into {folder}/human / tools/redteam/degrade.sh)")
        return
    print(f"wild eval ({folder}) · thresholds {THRESHOLDS_VERSION} · shipping p_ai threshold {P_AI_THRESHOLD}")
    for cond in sorted(rows):
        ai = [r for r in rows[cond] if r["label"] == "ai"]
        hu = [r for r in rows[cond] if r["label"] == "human"]
        a, h = [r["p_ai"] for r in ai], [r["p_ai"] for r in hu]
        fpr, thr = fpr_at_tpr(a, h)
        print(f"\n[{cond}] AI n={len(ai)}  human n={len(hu)}   AUC {_f(auc(a, h))}  EER {_f(eer(a, h))}  "
              f"FPR@90%TPR {_f(fpr)}" + (f" (p_ai >= {thr:.2f})" if thr is not None else "  (need both classes)"))
        by_engine: dict[str, list[float]] = {}
        for r in ai:
            by_engine.setdefault(r["engine"], []).append(r["p_ai"])
        held = loeo(by_engine, h) if len(by_engine) > 1 else {}
        for eng in sorted(by_engine):
            sc = by_engine[eng]
            note = f"  [in-domain: {IN_DOMAIN[eng]}]" if eng in IN_DOMAIN else ""
            ho = held.get(eng)
            ho_s = (f"held-out: thr {ho['threshold']:.2f} -> TPR {ho['tpr']:.2f}, FPR {ho['fpr']:.2f}" if ho else "held-out: need >= 2 engines")
            print(f"   {eng:12} n={len(sc):2}  caught {sum(x >= P_AI_THRESHOLD for x in sc)}/{len(sc)} at {P_AI_THRESHOLD}  "
                  f"AUC {_f(auc(sc, h))}  {ho_s}{note}")
        for r in ai:
            if r["p_ai"] < P_AI_THRESHOLD:
                print(f"   MISS  {r['name']}: p_ai {r['p_ai']:.3f}, tier {r['tier']}; fired: {r['fired'] or 'none'}")
        for r in hu:
            if r["p_ai"] >= P_AI_THRESHOLD:
                print(f"   FALSE ALARM  {r['name']}: p_ai {r['p_ai']:.3f}, tier {r['tier']}; fired: {r['fired'] or 'none'}")
        if verbose:
            for r in rows[cond]:
                print(f"   {r['label']:5} {r['engine']:12} {r['name']}: p_ai {r['p_ai']:.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--wild", metavar="DIR", help="evaluate real/Gradium recordings in DIR (e.g. data/calls) instead of the golden set")
    a = ap.parse_args()
    if a.wild:
        run_wild(a.wild, a.verbose)
        sys.exit(0)
    t = run_transcripts(a.verbose)
    au = run_audio(a.verbose)
    ok = t >= TARGET_TRANSCRIPT and au >= TARGET_AUDIO
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
