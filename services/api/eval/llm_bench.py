#!/usr/bin/env python3
"""Compare local Ollama models as the scam-talk judge on the golden transcripts (full pipeline, stub for the rest).

    ./.venv/bin/python services/api/eval/llm_bench.py --models llama3.2:3b qwen2.5:3b qwen3:4b [--limit N]

Reports per model: 4-tier accuracy (same half-credit rule as run_eval), llm_scam_framing recall on scam cases and
false-positive rate on the rest at 0.5, parse failures (no llm tells returned), and median / p95 latency of the LLM call.
Needs `ollama serve` and the models pulled. Everything is on localhost; the models only see transcript text.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ["LLM_PROVIDER"] = "ollama"

from doublespeak import pipeline  # noqa: E402


def bench(model: str, cases: list[dict]) -> dict:
    os.environ["OLLAMA_MODEL"] = model
    hits, lat, fails = 0.0, [], 0
    scam_hit = scam_n = fp = non_n = 0
    for c in cases:
        v = pipeline.analyze(None, c["transcript"])
        framing = next((t for t in v.tells if t.name == "llm_scam_framing"), None)
        if framing is None:
            fails += 1
        lat.append(v.cost.get("latency_ms", 0))
        ok = v.tier == c["expected"]
        hits += 1 if ok else (0.5 if v.tier == "unsure" and c["expected"] != "scam" else 0)
        flagged = framing is not None and framing.score >= 0.5
        if c["expected"] == "scam":
            scam_n += 1
            scam_hit += flagged
        else:
            non_n += 1
            fp += flagged
    lat.sort()
    return {"model": model, "acc": hits / len(cases), "scam_recall": scam_hit / max(scam_n, 1), "framing_fp": fp / max(non_n, 1),
            "parse_fail": fails, "p50_ms": int(statistics.median(lat)), "p95_ms": lat[min(len(lat) - 1, int(0.95 * len(lat)))]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["llama3.2:3b", "qwen2.5:3b"])
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    cases = [json.loads(l) for l in (HERE / "golden.jsonl").read_text().splitlines() if l.strip()]
    cases = cases[: a.limit] if a.limit else cases
    print(f"{len(cases)} golden cases, local Ollama only")
    print(f"{'model':16} {'tier acc':>8} {'scam recall':>11} {'framing FP':>10} {'parse fail':>10} {'p50 ms':>7} {'p95 ms':>7}")
    for m in a.models:
        r = bench(m, cases)
        print(f"{r['model']:16} {r['acc']:8.2f} {r['scam_recall']:11.2f} {r['framing_fp']:10.2f} {r['parse_fail']:10d} {r['p50_ms']:7d} {r['p95_ms']:7d}", flush=True)
