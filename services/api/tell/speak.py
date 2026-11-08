"""Spoken verdict through Gradium TTS. Sends ONLY Tell's own fixed verdict wording; never caller audio or text.

Two ways the verdict is spoken, both constrained to the SAME fixed wording:

- PRE-RENDERED (preferred for the demo): `tools/render_verdict_audio.py` renders each fixed line to a local WAV
  ahead of time (BUILD time), writing a manifest. `prerendered_wav(tier)` serves the cached bytes with NO network
  and NO egress, so it plays with Wi-Fi off and the call-time egress counters stay 0.
- LIVE (fallback): `verdict_wav(headline)` calls the Gradium CLI (`uvx gradium tts`) right now and records egress as
  "verdict_tts". Needs GRADIUM_API_KEY and `uv` on PATH. Optional GRADIUM_VOICE_ID picks the voice.

Privacy rule (D-004, D-006): ONLY the fixed sentences below may ever reach Gradium, and only at build time for the
pre-rendered files. Caller audio and caller words never go to any TTS. `evidence` is accepted for client
compatibility and deliberately ignored — it quotes the caller.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import privacy

ROOT = Path(__file__).resolve().parents[3]   # repo root (services/api/tell/speak.py -> repo root)

# The fixed spoken lines, one per verdict tier: a headline verdict + a short spoken advice line. These are the ONLY
# sentences Tell will ever voice. They quote no caller content. Keep them short; the renderer reads this dict directly.
SPOKEN_LINES = {
    "scam": "Heads up. Scam pattern. Hang up and call back on a number you already have.",
    "human": "Sounds human. No scam pattern heard.",
    "ai_undisclosed": "Likely synthetic, and the caller did not say so. Treat it as untrusted and call back on a known number.",
    "ai_disclosed": "The caller said it is automated. Never share codes or payment with an automated caller.",
    "unsure": "Unsure. Not enough signal to judge. If money or codes come up, hang up and call back on a known number.",
}

# Where the pre-rendered files and their manifest live. apps/web/verdict_audio/ so the web page can also play them
# statically and offline. Gitignored — audio is never committed. Override with TELL_VERDICT_AUDIO_DIR (used by tests).
MANIFEST_NAME = "manifest.json"


class SpeakUnavailable(RuntimeError):
    pass


def audio_dir() -> Path:
    override = os.environ.get("TELL_VERDICT_AUDIO_DIR")
    return Path(override) if override else ROOT / "apps" / "web" / "verdict_audio"


def manifest_path() -> Path:
    return audio_dir() / MANIFEST_NAME


def tiers() -> set[str]:
    return set(SPOKEN_LINES)


def known_headlines() -> set[str]:
    from . import scorer
    return {h for h, _advice in scorer.COPY.values()}


def tier_for_headline(headline: str) -> str | None:
    """Reverse-map a scorer COPY headline (what the web/API sends) to its tier, or None if it is not one of ours."""
    from . import scorer
    for tier, (h, _advice) in scorer.COPY.items():
        if h == headline:
            return tier
    return None


def spoken_text(tier: str) -> str:
    """The one fixed sentence Tell may speak for `tier`. The fixed-wording guard for the pre-rendered path."""
    if tier not in SPOKEN_LINES:
        raise ValueError(f"no fixed spoken line for tier {tier!r}; allowed: {sorted(SPOKEN_LINES)}")
    return SPOKEN_LINES[tier]


def verdict_text(headline: str, evidence: str = "") -> str:
    """Only Tell's own fixed verdict wording may be spoken (live path). `evidence` is accepted for client
    compatibility and deliberately ignored: evidence strings quote the caller's words, which must never reach a
    third-party TTS."""
    if headline not in known_headlines():
        raise ValueError("only Tell's own verdict wording can be spoken")
    return f"Heads up. {headline}."


# ------------------------------------------------------------------------------------ pre-rendered (no network, no egress)
def load_manifest() -> dict | None:
    """The manifest written by the renderer, or None if nothing has been rendered. Never raises for a missing file."""
    p = manifest_path()
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def prerendered_wav(tier: str) -> bytes:
    """Serve the cached WAV for `tier` from disk. No network, no Gradium, no egress. Raises SpeakUnavailable if the
    file or manifest is missing or the bytes do not match the manifest sha256 (so a stale/edited file is refused)."""
    if tier not in SPOKEN_LINES:
        raise ValueError(f"no fixed spoken line for tier {tier!r}")
    manifest = load_manifest()
    if not manifest:
        raise SpeakUnavailable("no pre-rendered verdict audio (run `make verdict-audio`)")
    entry = next((e for e in manifest.get("lines", []) if e.get("tier") == tier), None)
    if not entry:
        raise SpeakUnavailable(f"no pre-rendered audio for tier {tier!r}")
    # Guard: the manifest text must still be our fixed line. A manifest describing anything else is refused.
    if entry.get("text") != SPOKEN_LINES[tier]:
        raise SpeakUnavailable(f"pre-rendered manifest text for {tier!r} is not the current fixed wording")
    wav_path = audio_dir() / entry["file"]
    try:
        data = wav_path.read_bytes()
    except OSError as e:
        raise SpeakUnavailable(f"pre-rendered file missing: {wav_path.name}") from e
    if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
        raise SpeakUnavailable(f"pre-rendered file {wav_path.name} does not match its manifest sha256")
    return data


# ------------------------------------------------------------------------------------ live (calls Gradium, records egress)
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
