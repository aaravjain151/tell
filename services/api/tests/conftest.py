import os

# Settings are TELL_* (D-013); the legacy DOUBLESPEAK_* names are honoured as a fallback by tell/env.py. A shell that
# still exports an old name would leak through that fallback into tests that clear the TELL_ name, so move any legacy
# variable to its new name once, before any test runs (an explicit TELL_ value wins). test_env.py covers the fallback.
for _k in [k for k in os.environ if k.startswith("DOUBLESPEAK_")]:
    os.environ.setdefault("TELL_" + _k[len("DOUBLESPEAK_"):], os.environ.pop(_k))

# Tests must never probe a real local engine: default to in-process whisper (absent on a clean checkout).
# Tests that exercise VoiceStudio set TELL_STT themselves and inject a fake opener.
os.environ.setdefault("TELL_STT", "whisper")
