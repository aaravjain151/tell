#!/usr/bin/env python3
"""Render Tell's fixed spoken verdict lines to local WAV files with Gradium TTS, once, ahead of time.

    python3 tools/render_verdict_audio.py              # render every fixed line (needs GRADIUM_API_KEY + uv)
    python3 tools/render_verdict_audio.py --check       # validate the fixed set + any existing manifest; no Gradium
    python3 tools/render_verdict_audio.py --voice-id V   # pick a Gradium voice (else GRADIUM_VOICE_ID)

Why this exists: so Tell can SPEAK its verdict out loud in a Gradium voice that plays locally with Wi-Fi OFF — the
only bytes that ever reach Gradium are these fixed sentences, and they leave at BUILD time, never during a call.

Privacy: the ONLY text sent to Gradium is `tell.speak.SPOKEN_LINES` — Tell's own fixed verdict wording. It refuses to
render anything else. Caller audio and caller words never reach any TTS. Egress is recorded as `verdict_tts_prerender`.

Output: <out>/<tier>.wav (16 kHz mono, small) + <out>/manifest.json {voice_id, date, lines:[{tier,text,file,sha256}]}.
Default <out> is apps/web/verdict_audio/ (gitignored — audio is never committed). Re-run with `make verdict-audio`.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from tell import privacy, speak  # noqa: E402


def assert_fixed(tier: str, text: str) -> None:
    """Refuse to render anything that is not Tell's own fixed spoken line for this tier."""
    if tier not in speak.SPOKEN_LINES:
        raise ValueError(f"refusing: {tier!r} is not a verdict tier; only {sorted(speak.SPOKEN_LINES)} may be spoken")
    if text != speak.SPOKEN_LINES[tier]:
        raise ValueError(f"refusing: text for {tier!r} is not Tell's fixed wording — only fixed verdict lines may be rendered")


def to_16k_mono_wav(wav_bytes: bytes) -> bytes:
    """Decode whatever Gradium returned and re-encode as 16 kHz mono PCM16 (small, uniform). Uses Tell's own decoder."""
    import numpy as np

    from tell import audio
    x, _sr, _ms = audio.decode(wav_bytes)
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    return buf.getvalue()


def gradium_cli(text: str, voice_id: str) -> bytes:
    """Call `uvx gradium tts` and return the raw WAV bytes. Raises speak.SpeakUnavailable on any failure."""
    if not os.environ.get("GRADIUM_API_KEY"):
        raise speak.SpeakUnavailable("GRADIUM_API_KEY not set")
    uvx = shutil.which("uvx")
    if not uvx:
        raise speak.SpeakUnavailable("`uvx` not found — install uv (brew install uv) to use the Gradium CLI")
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "line.wav"
        cmd = [uvx, "gradium", "tts", text, "-o", str(out)]
        if voice_id:
            cmd += ["--voice-id", voice_id]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if p.returncode != 0 or not out.exists():
            raise speak.SpeakUnavailable(f"gradium tts failed: {(p.stderr or p.stdout)[:300]}")
        return out.read_bytes()


def render(out_dir: Path, voice_id: str, runner=gradium_cli) -> dict:
    """Render every fixed line. Returns the manifest dict. `runner(text, voice_id) -> wav_bytes` is injectable (tests)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lines, chars = [], 0
    for tier, text in speak.SPOKEN_LINES.items():
        assert_fixed(tier, text)                       # belt-and-braces: never send anything but the fixed wording
        raw = runner(text, voice_id)
        privacy.record_egress("verdict_tts_prerender", len(text.encode()))   # BUILD-time egress, logged as its own kind
        chars += len(text)
        wav = to_16k_mono_wav(raw)
        fname = f"{tier}.wav"
        (out_dir / fname).write_bytes(wav)
        lines.append({"tier": tier, "text": text, "file": fname,
                      "sha256": hashlib.sha256(wav).hexdigest(), "bytes": len(wav)})
    manifest = {
        "voice_id": voice_id or "default",
        "engine": "gradium",
        "sample_rate": 16000,
        "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "gradium_calls": len(lines),
        "characters_sent": chars,
        "lines": lines,
    }
    (out_dir / speak.MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def check(out_dir: Path) -> int:
    """Validate the fixed set and, if present, that the manifest matches the files on disk. No Gradium call."""
    for tier, text in speak.SPOKEN_LINES.items():
        assert_fixed(tier, text)
    print(f"fixed spoken lines OK: {len(speak.SPOKEN_LINES)} tiers ({', '.join(speak.SPOKEN_LINES)})")
    manifest_file = out_dir / speak.MANIFEST_NAME
    if not manifest_file.exists():
        print(f"no manifest at {manifest_file} — nothing rendered yet (run `make verdict-audio`)")
        return 0
    manifest = json.loads(manifest_file.read_text())
    bad = 0
    for entry in manifest.get("lines", []):
        tier = entry.get("tier")
        if entry.get("text") != speak.SPOKEN_LINES.get(tier):
            print(f"  MISMATCH {tier}: manifest text is not the current fixed wording"); bad += 1; continue
        wav = out_dir / entry["file"]
        if not wav.exists():
            print(f"  MISSING  {tier}: {wav.name}"); bad += 1; continue
        if hashlib.sha256(wav.read_bytes()).hexdigest() != entry.get("sha256"):
            print(f"  SHA FAIL {tier}: {wav.name} does not match manifest"); bad += 1; continue
        print(f"  ok       {tier}: {wav.name} ({entry.get('bytes', 0)} B)")
    print(f"voice_id={manifest.get('voice_id')} date={manifest.get('date')}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(speak.audio_dir()), help="output dir for WAVs + manifest.json")
    ap.add_argument("--voice-id", default="", help="Gradium voice id (else GRADIUM_VOICE_ID from the environment)")
    ap.add_argument("--env-file", help="load GRADIUM_API_KEY/GRADIUM_VOICE_ID from this .env into the process env for "
                    "this one render step (never printed). Equivalent to `set -a && . <file>`.")
    ap.add_argument("--check", action="store_true", help="validate the fixed set + manifest; no Gradium call")
    a = ap.parse_args(argv)
    if a.env_file:
        from dotenv import load_dotenv
        load_dotenv(a.env_file)                       # loads into os.environ only; values are never printed
    voice_id = a.voice_id or os.environ.get("GRADIUM_VOICE_ID", "")
    out_dir = Path(a.out)
    if a.check:
        return check(out_dir)
    try:
        before = privacy.report()["external_requests"]
        manifest = render(out_dir, voice_id)
    except speak.SpeakUnavailable as e:
        print(f"NOT RENDERED: {e}", file=sys.stderr)
        print("Everything else is built; run `make verdict-audio` once GRADIUM_API_KEY and uv are available.",
              file=sys.stderr)
        return 3
    calls = privacy.report()["external_requests"] - before
    print(f"Rendered {manifest['gradium_calls']} fixed verdict lines to {out_dir}")
    print(f"Gradium calls (credits used): {manifest['gradium_calls']}  ·  characters sent: {manifest['characters_sent']}"
          f"  ·  egress records this run: {calls}")
    print(f"voice_id={manifest['voice_id']}  ·  files are 16 kHz mono  ·  manifest: {out_dir / speak.MANIFEST_NAME}")
    print("Only Tell's own fixed wording was sent to Gradium, at build time. Caller audio/words never leave the device.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
