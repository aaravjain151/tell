"""Tell: a 100% on-device scam-call detector for older people.

The package is intentionally split into small, single-purpose modules:

* :mod:`doublespeak.offline_guard` - forces offline ML operation.
* :mod:`doublespeak.config`        - constants and paths.
* :mod:`doublespeak.audio`         - in-memory microphone capture.
* :mod:`doublespeak.transcribe`    - faster-whisper speech-to-text.
* :mod:`doublespeak.deepfake`      - pellav2 preprocessing + model loader.
* :mod:`doublespeak.secure_store`  - AES-256-GCM encrypted alert history.
* :mod:`doublespeak.net_monitor`   - psutil outbound-connection monitor.
* :mod:`doublespeak.detector`      - the full detection pipeline (entry point).

The scam-talk analysis (Ollama + regex safety net) lives inside
:mod:`doublespeak.detector`.

Importing the package applies the offline guard immediately.
"""

from __future__ import annotations

from . import offline_guard  # noqa: F401  (import for side effect)

__all__ = ["offline_guard"]
__version__ = "0.1.0"
