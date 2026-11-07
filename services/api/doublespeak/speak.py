"""Spoken verdict through Gradium TTS. Sends ONLY our verdict text; records egress as "verdict_tts".

Uses the Gradium CLI documented in the gradium-py README (`uvx gradium tts "text" -o out.wav`),
so there is no bespoke HTTP code to get wrong. Requires GRADIUM_API_KEY in the environment and
`uv` on PATH (https://docs.astral.sh/uv/). Optional GRADIUM_VOICE_ID picks the voice.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from . import privacy


class SpeakUnavailable(RuntimeError):
    pass


def known_headlines() -> set[str]:
    from . import scorer
    return {h for h, _advice in scorer.COPY.values()}


def verdict_text(headline: str, evidence: str = "") -> str:
    """Only Doublespeak's own fixed verdict wording may be spoken. `evidence` is accepted for client compatibility
    and deliberately ignored: evidence strings quote the caller's words, which must never reach a third-party TTS."""
    if headline not in known_headlines():
        raise ValueError("only Doublespeak's own verdict wording can be spoken")
    return f"Heads up. {headline}."


def verdict_wav(headline: str, evidence: str = "") -> bytes:
    key = os.environ.get("GRADIUM_API_KEY")
    if not key:
        raise SpeakUnavailable("GRADIUM_API_KEY not set")
    uvx = shutil.which("uvx")
    if not uvx:
        raise SpeakUnavailable("`uvx` not found — install uv to use the Gradium CLI")
    text = verdict_text(headline, evidence)
    cmd = [uvx, "gradium", "tts", text]
    voice = os.environ.get("GRADIUM_VOICE_ID")
    if voice:
        cmd += ["--voice-id", voice]
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "verdict.wav")
        cmd += ["-o", out]
        privacy.record_egress("verdict_tts", len(text.encode()))
        p = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "GRADIUM_API_KEY": key}, timeout=60)
        if p.returncode != 0 or not os.path.exists(out):
            raise SpeakUnavailable(f"gradium tts failed: {(p.stderr or p.stdout)[:300]}")
        with open(out, "rb") as f:
            return f.read()
