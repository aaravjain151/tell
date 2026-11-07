import os

# Tests must never probe a real local engine: default to in-process whisper (absent on a clean checkout).
# Tests that exercise VoiceStudio set DOUBLESPEAK_STT themselves and inject a fake opener.
os.environ.setdefault("DOUBLESPEAK_STT", "whisper")
