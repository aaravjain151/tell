#!/usr/bin/env python3
"""Regenerate the four inline demo verdicts in index.html (#samples-data) from the real engine.

    ./.venv/bin/python apps/web/build_samples.py [--check]

Deterministic on purpose: LLM_PROVIDER=stub, no HF/ONNX model, no Whisper (transcripts are supplied), so the
file-only demo shows the same verdict on every machine. Audio is tests/synth.py fixtures (mechanics, not real voices).
Refuses to write if any sample's tier changed from the expected one. --check only reports.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "services" / "api"
sys.path.insert(0, str(API))
os.environ["LLM_PROVIDER"] = "stub"
for k in ("HF_SPOOF_MODEL", "ANTI_SPOOF_MODEL"):
    os.environ.pop(k, None)

from doublespeak import pipeline  # noqa: E402
from tests.synth import make_call, to_wav_bytes  # noqa: E402

HTML = Path(__file__).with_name("index.html")
KIND = {"human": "human", "ai_undisclosed": "tts", "ai_disclosed": "tts", "scam": "tts"}   # synth voice per sample
PAT = re.compile(r'(<script id="samples-data" type="application/json">)(.*?)(</script>)', re.S)


def main() -> int:
    html = HTML.read_text()
    old = json.loads(PAT.search(html).group(2))
    new, bad = {}, []
    for key, s in old.items():
        v = pipeline.analyze(to_wav_bytes(make_call(KIND[key], seed=0, phone_band=True)), s["transcript"]).to_dict()
        v["transcript"] = s["transcript"]
        new[key] = v
        flag = "" if v["tier"] == key else "   <-- TIER CHANGED"
        print(f"{key:15} -> {v['tier']:15} p_ai {v['p_ai']:.2f} p_scam {v['p_scam']:.2f} egress {v['egress']['caller_audio_bytes_sent']}{flag}")
        if v["tier"] != key:
            bad.append(key)
    if bad:
        print("not writing: tiers changed for", bad, file=sys.stderr)
        return 1
    if "--check" not in sys.argv:
        HTML.write_text(PAT.sub(lambda m: m.group(1) + json.dumps(new, separators=(",", ":")) + m.group(3), html, count=1))
        print("wrote", HTML.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
