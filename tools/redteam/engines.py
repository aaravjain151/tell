"""TTS engines for generating attacker calls. Red-team tooling only: it is never imported by the analysis path.

Each engine turns *our script text* into a WAV file. Caller audio is never sent anywhere.

  gradium     `uvx gradium tts` CLI            needs GRADIUM_API_KEY (+ uv)            cloud, credits
  elevenlabs  `elevenlabs` SDK (text_to_speech.convert) ELEVENLABS_API_KEY in .env.local (from the ElevenLabs CLI)   cloud, credits
  voicestudio POST localhost:3900/v1/audio/speech   VoiceStudio app running locally   local, free, AGPL-3.0 (used over HTTP only; no code vendored)
  qwen3tts    `qwen-tts` package, Qwen3-TTS Base  pip install -U qwen-tts; clones from a ref wav + its exact words   local, free, Apache-2.0; slow on Mac (mps), minutes per clip

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


ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    """Load .env.local (written by the ElevenLabs CLI), then .env, into os.environ; real environment variables win. Never prints values."""
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env.local")
    load_dotenv(ROOT / ".env")


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


def elevenlabs(text: str, out: Path, voice_id: str = "", client=None, **_) -> None:
    """ElevenLabs SDK (`pip install elevenlabs`). The key is read from ELEVENLABS_API_KEY by the SDK, never passed here."""
    from elevenlabs import ElevenLabs
    load_env()   # the SDK reads ELEVENLABS_API_KEY from the environment; it lives in .env.local
    voice = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")   # stock "George"; override with a consenting teammate's clone
    model = os.environ.get("ELEVENLABS_MODEL", "eleven_v4")
    audio = (client or ElevenLabs()).text_to_speech.convert(text=text, voice_id=voice, model_id=model, output_format="pcm_16000")
    out.write_bytes(wrap_pcm16(b"".join(audio), 16_000))


def voicestudio(text: str, out: Path, voice_id: str = "", opener=None, **_) -> None:
    base = os.environ.get("VOICESTUDIO_URL", "http://127.0.0.1:3900")
    body = {"input": text, "model": os.environ.get("VOICESTUDIO_MODEL", "omnivoice"), "response_format": "wav"}
    if voice_id:
        body["voice"] = voice_id          # a VoiceStudio profile id (e.g. a consenting teammate's clone)
    out.write_bytes(_post(base + "/v1/audio/speech", body, {}, opener, timeout=600))   # first call may download the model


_qwen = None   # loaded once: the model is ~2-4 GB


def _load_qwen():
    import torch
    from qwen_tts import Qwen3TTSModel
    name = os.environ.get("QWEN3TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-Base")   # 1.7B-Base is better but ~3x slower
    mps = torch.backends.mps.is_available()
    return Qwen3TTSModel.from_pretrained(name, device_map="mps" if mps else "cpu", dtype=torch.bfloat16 if mps else torch.float32)


def qwen3tts(text: str, out: Path, voice_id: str = "", voice_text: str = "", loader=None, **_) -> None:
    """Clone the voice in `voice_id` (a ref .wav of a consenting teammate) saying `voice_text` (its exact words)."""
    global _qwen
    import numpy as np
    if not voice_id or not Path(voice_id).is_file():
        raise RuntimeError("qwen3tts needs --voice <ref.wav> (a consenting teammate, 3-15 s) and --voice-text '<exact words in it>'")
    if not voice_text.strip():
        raise RuntimeError("qwen3tts needs --voice-text: the exact words spoken in the reference clip")
    if _qwen is None:
        _qwen = (loader or _load_qwen)()
    wavs, sr = _qwen.generate_voice_clone(text=text, language=os.environ.get("QWEN3TTS_LANG", "English"), ref_audio=voice_id, ref_text=voice_text)
    x = np.clip(np.asarray(wavs[0], dtype=np.float32), -1.0, 1.0)
    out.write_bytes(wrap_pcm16((x * 32767).astype("<i2").tobytes(), int(sr)))


# order matters for `--engine all` under --max: the slow local one first, so it is never starved
ENGINES = {"qwen3tts": qwen3tts, "voicestudio": voicestudio, "gradium": gradium, "elevenlabs": elevenlabs}
VOICE_ENV = {"gradium": "GRADIUM_VOICE_ID", "elevenlabs": "ELEVENLABS_VOICE_ID", "voicestudio": "VOICESTUDIO_VOICE", "qwen3tts": "QWEN3TTS_REF"}
PAID = {"gradium", "elevenlabs"}


def unavailable_reason(engine: str, opener=None) -> str | None:
    """None if the engine looks usable, else a one-line reason."""
    if engine == "gradium":
        if not os.environ.get("GRADIUM_API_KEY"):
            return "GRADIUM_API_KEY not set"
        if not shutil.which("uvx"):
            return "`uvx` not found (brew install uv)"
    elif engine == "elevenlabs":
        import importlib.util
        if not os.environ.get("ELEVENLABS_API_KEY"):
            return "ELEVENLABS_API_KEY not set (run `npx -y @elevenlabs/cli@latest onboard init`; the key lands in .env.local)"
        if importlib.util.find_spec("elevenlabs") is None:
            return "elevenlabs SDK not installed (pip install -r tools/redteam/requirements.txt)"
    elif engine == "qwen3tts":
        import importlib.util
        if importlib.util.find_spec("qwen_tts") is None:
            return "qwen-tts not installed (pip install -U qwen-tts)"
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
