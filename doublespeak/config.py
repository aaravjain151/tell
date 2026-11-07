"""Central configuration for DoubleSpeak.

All tunable constants and filesystem paths live here so the rest of the code
stays declarative. Importing this module also enforces offline mode via
:mod:`doublespeak.offline_guard`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Importing offline_guard first sets HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE etc.
from . import offline_guard  # noqa: F401  (import for side effect)

# --------------------------------------------------------------------------- #
# Filesystem layout
# --------------------------------------------------------------------------- #

#: Project root (the folder that contains the ``doublespeak`` package).
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

#: Where encrypted data and offline model weights live. Overridable via env so
#: the whole app can be pointed at a removable drive if desired.
DATA_DIR: Path = Path(os.environ.get("DOUBLESPEAK_DATA_DIR", PROJECT_ROOT / "data"))

#: Local directory holding the pellav2 weights + config (downloaded once, then
#: used fully offline). Expected files: ``pellav2_detector.pt``, ``config.json``.
MODELS_DIR: Path = Path(os.environ.get("DOUBLESPEAK_MODELS_DIR", PROJECT_ROOT / "models"))

#: Encrypted, append-only alert history file (AES-256-GCM, see crypto_store).
HISTORY_FILE: Path = DATA_DIR / "alert_history.enc"


def ensure_dirs() -> None:
    """Create the data directory if missing. Models dir is created on demand."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Audio
# --------------------------------------------------------------------------- #

#: Sample rate every component works in. Both whisper and pellav2 expect 16 kHz.
SAMPLE_RATE: int = 16_000

#: Length of each analysis window, in seconds. Long enough for the LLM to have
#: meaningful text, short enough to warn the user quickly.
WINDOW_SECONDS: float = 6.0

#: How much consecutive windows overlap, in seconds. Keeps sentences intact.
WINDOW_OVERLAP_SECONDS: float = 1.0


# --------------------------------------------------------------------------- #
# faster-whisper
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WhisperConfig:
    """Settings for the faster-whisper transcriber (CPU, int8, VAD)."""

    model_size: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    vad_filter: bool = True
    beam_size: int = 1  # greedy: fastest, fine for short windows
    #: Local CTranslate2 model directory. If None, faster-whisper resolves the
    #: name from its own offline cache (populated during one-time setup).
    local_model_dir: Path | None = field(
        default_factory=lambda: _optional_dir(MODELS_DIR / "faster-whisper-base")
    )


# --------------------------------------------------------------------------- #
# pellav2 deepfake detector
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DeepfakeConfig:
    """Settings for the pellav2 audio deepfake detector."""

    hub_repo: str = "Sadanie/pellav2-audio-deepfake-detector"
    backbone: str = "facebook/w2v-bert-2.0"
    #: Local path to ``pellav2_detector.pt``. Required for offline use.
    weights_path: Path = MODELS_DIR / "pellav2_detector.pt"
    #: Probability threshold above which a clip is flagged as AI-cloned.
    fake_threshold: float = 0.5
    target_lufs: float = -23.0
    crop_seconds: int = 4


# --------------------------------------------------------------------------- #
# Ollama scam analyzer
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class OllamaConfig:
    """Settings for the local Ollama scam-talk analyzer.

    The host is pinned to localhost: this is the ONLY network connection the
    product is allowed to make.
    """

    host: str = "http://localhost:11434"
    model: str = "llama3.2:3b"
    #: Seconds to wait for a response before giving up on a window.
    timeout: float = 30.0
    #: Deterministic output: temperature 0 keeps warnings consistent.
    temperature: float = 0.0


# --------------------------------------------------------------------------- #
# Risk scoring
# --------------------------------------------------------------------------- #

#: Scam-text score (0-100) at/above which we show a warning.
SCAM_WARN_THRESHOLD: int = 50

#: Keychain service + key names used by secure_store / keyring.
KEYRING_SERVICE: str = "doublespeak"
KEYRING_USERNAME: str = "alert-history-key"


# --------------------------------------------------------------------------- #
# Detection pipeline (detector.py)
# --------------------------------------------------------------------------- #

#: Rolling voice-analysis window and hop, in seconds (pellav2 scores 4 s crops).
VOICE_WINDOW_SECONDS: float = 4.0
VOICE_HOP_SECONDS: float = 2.0

#: RMS energy below which a window counts as silent and is skipped.
SILENCE_RMS: float = 0.01

#: Risk fusion weights and the "both high" escalation rule.
VOICE_WEIGHT: float = 0.4
SCAM_WEIGHT: float = 0.6
ESCALATE_VOICE_ABOVE: float = 0.7
ESCALATE_SCAM_ABOVE: float = 0.5
ESCALATED_RISK_FLOOR: float = 0.9

#: Fused-risk thresholds for the three plain-language levels.
RISK_HIGH: float = 0.65
RISK_MEDIUM: float = 0.35

#: Regex scam rules: (compiled pattern source, weight 0-1, plain reason).
#: Weights are summed over matched rules and clamped to 1.0. Tuned so a single
#: clear scam signal (gift cards, codes) crosses the 0.5 "both high" gate.
SCAM_RULES: list[tuple[str, float, str]] = [
    (r"gift ?cards?|steam card|google play card|itunes card", 0.6,
     "Asked you to buy gift cards"),
    (r"gift card number|scratch (?:off|the back)|read me the code", 0.5,
     "Asked for the gift card number"),
    (r"bitcoin|crypto(?:currency)?|wire transfer|western union|money ?gram", 0.55,
     "Asked for crypto or a wire transfer"),
    (r"\barrest(?:ed)?\b|warrant|jail|\bpolice\b|lawsuit|legal action", 0.5,
     "Threatened you with arrest or the police"),
    (r"accident|hospital|kidnap|ransom|\bbail\b|in trouble", 0.5,
     "Claimed an emergency to scare you"),
    (r"\botp\b|one[- ]?time (?:code|pin|password)|verification code|\bpin\b|\bpassword\b",
     0.6, "Asked for a code, PIN or password"),
    (r"social security|\bssn\b|bank account number|routing number|card number",
     0.55, "Asked for sensitive personal or bank numbers"),
    (r"don'?t tell|keep (?:this|it) (?:secret|between us)|do not tell anyone", 0.4,
     "Told you to keep it secret"),
    (r"act now|right now|immediately|urgent(?:ly)?|within the hour|before it'?s too late",
     0.35, "Pressured you to act immediately"),
]


@dataclass(frozen=True)
class Contact:
    """A trusted contact shown on the 'call their real number' button."""

    name: str
    phone: str


#: Demo contacts list. In a real build this would be the user's saved contacts
#: (entered locally, never uploaded). Display-only for the demo.
CONTACTS: list[Contact] = [
    Contact("your bank", "1-800-555-0100"),
    Contact("your son David", "1-415-555-0137"),
    Contact("the police (non-emergency)", "1-311"),
]


def _optional_dir(path: Path) -> Path | None:
    """Return ``path`` if it exists on disk, else ``None``."""
    return path if path.exists() else None


# Instantiate the default configs once for convenient import.
WHISPER = WhisperConfig()
DEEPFAKE = DeepfakeConfig()
OLLAMA = OllamaConfig()
