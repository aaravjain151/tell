#!/usr/bin/env python3
"""Run the LOCAL pipeline over labelled clips and dump per-clip NUMERIC features to a JSON file (no audio, no transcript text).

    python3 tools/personal/collect.py DATA_CALLS_DIR OUT.json [--extra FILE.wav ...]

Layout read (read-only): DATA_CALLS_DIR/<engine>/<name>[.opus8k].wav (+ optional <name>[.opus8k].txt transcript) and
DATA_CALLS_DIR/human/<speaker>/.... Output rows hold only numbers and tell names (never audio or transcript), but keep the
file under a scratch directory anyway: it is derived from a person's recordings and is not committed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "api"))
os.environ.setdefault("LLM_PROVIDER", "stub")
os.environ.setdefault("DOUBLESPEAK_STT", "whisper")

SCAM_PREFIXES = ("scam_", "long_tech_scam")


def row_for(path: Path, engine: str, speaker: str, cond: str, name: str) -> dict:
    from doublespeak import pipeline
    txt = path.with_suffix(".txt")
    transcript = txt.read_text(encoding="utf-8", errors="replace") if txt.exists() else None
    v = pipeline.analyze(path.read_bytes(), transcript)
    ctx = (v.egress or {}).get("context") or {}
    return {
        "engine": engine, "speaker": speaker, "name": name, "cond": cond,
        "is_ai": engine != "human", "is_scam": name.startswith(SCAM_PREFIXES),
        "tier": v.tier, "p_ai": v.p_ai, "p_scam": v.p_scam, "confidence": v.confidence, "disclosed_ai": v.disclosed_ai,
        "tells": [{"name": t.name, "family": t.family, "score": t.score, "weight": t.weight, "applicable": t.applicable}
                  for t in v.tells],
        "ctx": {k: ctx.get(k) for k in ("band_limited", "duration_s", "high_band_ratio", "speech_ratio")},
        "shadow": {k: d.get("value") for k, d in (ctx.get("shadow") or {}).items() if isinstance(d, dict)},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("calls_dir")
    ap.add_argument("out")
    ap.add_argument("--extra", nargs="*", default=[], help="extra AI wavs (e.g. the owner's two Qwen files)")
    a = ap.parse_args()
    root = Path(a.calls_dir)
    rows = []
    for wav in sorted(root.rglob("*.wav")):
        rel = wav.relative_to(root)
        engine = rel.parts[0]
        speaker = rel.parts[1] if engine == "human" and len(rel.parts) > 2 else engine
        stem = wav.stem
        cond = "opus8k" if stem.endswith(".opus8k") else "clean"
        name = stem[: -len(".opus8k")] if cond == "opus8k" else stem
        rows.append(row_for(wav, engine, speaker, cond, name))
        print(len(rows), rel, rows[-1]["tier"], round(rows[-1]["p_ai"], 2), round(rows[-1]["p_scam"], 2), flush=True)
    for e in a.extra:
        p = Path(e)
        name = p.stem.replace("data_calls_qwen3tts_", "")
        rows.append(row_for(p, "owner_qwen", "owner_qwen", "clean", name))
    Path(a.out).write_text(json.dumps(rows))
    print("wrote", a.out, len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
