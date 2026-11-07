"""TTS engines for generating attacker calls. Red-team tooling only: it is never imported by the analysis path.

Each engine turns *our script text* into a WAV file. Caller audio is never sent anywhere.

  gradium     `uvx gradium tts` CLI            needs GRADIUM_API_KEY (+ uv)            cloud, credits
  elevenlabs  POST api.elevenlabs.io           needs ELEVENLABS_API_KEY                cloud, credits
  voicestudio POST localhost:3900/v1/audio/speech   VoiceStudio app running locally   local, free, AGPL-3.0 (used over HTTP only; no code vendored)

Clone only voices of people who consented (teammates). Never clone a real person's voice without their say-so.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import urllib.request
import wave
from pathlib import Path

Opener = urllib.request.urlopen   # injectable in tests


def wrap_pcm16(pcm: bytes, sr: int = 16_000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()


def _post(url: str, body: dict, headers: dict, opener=None, timeout: float = 120) -> bytes:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json", **headers})
    with (opener or Opener)(req, timeout=timeout) as r:
        return r.read()


def gradium(text: str, out: Path, voice_id: str = "", **_) -> None:
    cmd = [shutil.which("uvx") or "uvx", "gradium", "tts", text, "-o", str(out)]
    if voice_id:
        cmd += ["--voice-id", voice_id]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[:300])


def elevenlabs(text: str, out: Path, voice_id: str = "", opener=None, **_) -> None:
    voice = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")   # stock "Rachel"; override with your clone
    model = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=pcm_16000"
    pcm = _post(url, {"text": text, "model_id": model}, {"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, opener)
    out.write_bytes(wrap_pcm16(pcm, 16_000))


def voicestudio(text: str, out: Path, voice_id: str = "", opener=None, **_) -> None:
    base = os.environ.get("VOICESTUDIO_URL", "http://127.0.0.1:3900")
    body = {"input": text, "model": os.environ.get("VOICESTUDIO_MODEL", "omnivoice"), "response_format": "wav"}
    if voice_id:
        body["voice"] = voice_id          # a VoiceStudio profile id (e.g. a consenting teammate's clone)
    out.write_bytes(_post(base + "/v1/audio/speech", body, {}, opener, timeout=600))   # first call may download the model


ENGINES = {"gradium": gradium, "elevenlabs": elevenlabs, "voicestudio": voicestudio}
VOICE_ENV = {"gradium": "GRADIUM_VOICE_ID", "elevenlabs": "ELEVENLABS_VOICE_ID", "voicestudio": "VOICESTUDIO_VOICE"}
PAID = {"gradium", "elevenlabs"}


def unavailable_reason(engine: str, opener=None) -> str | None:
    """None if the engine looks usable, else a one-line reason."""
    if engine == "gradium":
        if not os.environ.get("GRADIUM_API_KEY"):
            return "GRADIUM_API_KEY not set"
        if not shutil.which("uvx"):
            return "`uvx` not found (brew install uv)"
    elif engine == "elevenlabs":
        if not os.environ.get("ELEVENLABS_API_KEY"):
            return "ELEVENLABS_API_KEY not set"
    elif engine == "voicestudio":
        base = os.environ.get("VOICESTUDIO_URL", "http://127.0.0.1:3900")
        try:
            with (opener or Opener)(base + "/v1/audio/voices", timeout=3):
                pass
        except Exception as e:  # noqa: BLE001
            return f"VoiceStudio not reachable at {base} (start the app): {str(e)[:60]}"
    else:
        return f"unknown engine {engine}"
    return None
