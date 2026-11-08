"""Read-only readiness: inspect resident models, local caches and loopback status APIs.

No inference, warm-up, downloads or heavyweight model-library imports belong here.
Unset configuration is off, even where the analysis pipeline has implicit defaults.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from . import env as _env
from . import localhost, net_monitor, offline_guard, stt, thresholds
from .signals import neural


def _state(status: str, detail: str) -> dict:
    return {"status": status, "detail": detail}


def _cached(name: str, filenames: tuple[str, ...]) -> bool:
    path = Path(name)
    if path.is_dir():
        return any((path / filename).is_file() for filename in filenames)
    try:
        from huggingface_hub import try_to_load_from_cache
        return any(isinstance(try_to_load_from_cache(name, filename), str) for filename in filenames)
    except ImportError:
        return False


def _model(name: str, loaded: bool, filenames: tuple[str, ...]) -> dict:
    if loaded:
        return _state("ready", "loaded in memory")
    cached = _cached(name, filenames)
    return _state("degraded", "cached but not loaded yet" if cached else "not cached, run make models")


def _stt() -> dict:
    mode = _env.get("TELL_STT", "").lower()
    name = _env.get("TELL_WHISPER_MODEL", "")
    if mode == "voicestudio" or (not mode and not name):
        return _state("off", "Whisper not configured")
    if mode not in ("", "auto", "whisper"):
        return _state("degraded", "unknown TELL_STT")
    name = name or "base.en"
    # Mirror faster-whisper aliases without importing its heavyweight inference library.
    if "/" not in name and not Path(name).is_dir():
        if name in ("turbo", "large-v3-turbo"):
            name = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
        elif name == "distil-large-v3.5":
            name = "distil-whisper/distil-large-v3.5-ct2"
        elif name.startswith("distil-"):
            name = "Systran/faster-distil-whisper-" + name.removeprefix("distil-")
        else:
            name = "Systran/faster-whisper-" + ("large-v3" if name == "large" else name)
    return _model(name, stt._model is not None, ("model.bin",))


def _hf() -> dict:
    name = os.environ.get("HF_SPOOF_MODEL", "")
    if not name:
        return _state("off", "HF_SPOOF_MODEL not configured")
    return _model(name, neural._hf is not None,
                  ("model.safetensors", "pytorch_model.bin", "model.safetensors.index.json", "pytorch_model.bin.index.json"))


def _pella() -> dict:
    if not os.environ.get("PELLA_MODEL"):
        return _state("off", "PELLA_MODEL not configured")
    from .signals import pella
    if pella._model is not None:
        return _state("ready", f"loaded in memory on {pella._device}")
    if pella._error:
        return _state("degraded", pella._error[:120])
    path = pella.weights_path()
    return _state("degraded", "cached but not loaded yet" if path is not None and path.exists() else "not cached, run make models")


def _ollama() -> dict:
    provider = os.environ.get("LLM_PROVIDER", "").lower()
    if provider in ("", "stub"):
        return _state("off", "LLM not configured" if not provider else "stub provider")
    if provider != "ollama":
        return _state("degraded", "provider cannot be verified locally")
    base = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    name = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
    name = name if ":" in name.rsplit("/", 1)[-1] else name + ":latest"

    def contains(payload: dict) -> bool:
        return any(model.get("name") == name or model.get("model") == name for model in payload["models"])

    # /api/ps lists resident models; /api/tags lists cached ones. Neither loads a model.
    if contains(localhost.get_json(base + "/api/ps", timeout=0.75)):
        return _state("ready", "loaded in Ollama memory")
    cached = contains(localhost.get_json(base + "/api/tags", timeout=0.75))
    return _state("degraded", "cached but not loaded yet" if cached else "not cached, run make models")


def _voicestudio() -> dict:
    if _env.get("TELL_STT", "").lower() not in ("auto", "voicestudio"):
        return _state("off", "VoiceStudio STT not configured")
    base = os.environ.get("VOICESTUDIO_URL", "http://127.0.0.1:3900").rstrip("/")
    result = localhost.get_json(base + "/v1/models", timeout=1.5)
    for model in result["data"]:
        if model.get("id") == "whisper-1":
            if model.get("loaded") is True:
                return _state("ready", "VoiceStudio reports whisper-1 loaded")
            return _state("degraded", "VoiceStudio reachable; whisper-1 load state unconfirmed")
    return _state("degraded", "VoiceStudio does not advertise whisper-1")


def _check(check: Callable[[], dict]) -> dict:
    try:
        return check()
    except Exception as exc:  # noqa: BLE001 - readiness must survive broken optional engines/caches
        return _state("degraded", f"check failed ({type(exc).__name__})")


def report() -> dict:
    """Return a fresh snapshot without changing model state or analysis counters."""
    components = {name: _check(check) for name, check in (
        ("stt", _stt), ("anti_spoof_hf", _hf), ("pellav2", _pella), ("llm", _ollama), ("voicestudio_stt", _voicestudio),
    )}
    degraded = [name for name, component in components.items() if component["status"] == "degraded"]
    stt_ready = any(components[name]["status"] == "ready" for name in ("stt", "voicestudio_stt"))
    try:
        network = net_monitor.snapshot_report()
    except Exception:  # noqa: BLE001
        network = {"os_check": "unavailable", "os_outbound_count": 0, "os_outbound_seen": []}
    try:
        offline = bool(offline_guard.is_enforced())
    except Exception:  # noqa: BLE001
        offline = False
    try:
        version = str(thresholds.THRESHOLDS_VERSION)
    except Exception:  # noqa: BLE001
        version = "unknown"
    try:
        from . import privacy
        posture = privacy.posture()          # the switches that can move call content off the machine or onto disk
    except Exception:  # noqa: BLE001
        posture = {}
    return {"ready": stt_ready and not degraded, "degraded": degraded, "components": components,
            "offline_models": offline, "os_network": network, "privacy_posture": posture, "thresholds_version": version}
