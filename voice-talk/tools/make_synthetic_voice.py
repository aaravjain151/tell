"""Create a synthetic (macOS `say`, Samantha) demo voice with a recorded consent. No real person involved.
    python tools/make_synthetic_voice.py [name]"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from voice_talk.voices import VoiceStore  # noqa: E402

TEXT = ("The quick brown fox jumps over the lazy dog near the quiet river. "
        "Yesterday we walked to the market and bought fresh bread, apples and a little cheese.")


def main(name="demo-say"):
    with tempfile.TemporaryDirectory() as d:
        aiff, wav = Path(d, "r.aiff"), Path(d, "r.wav")
        subprocess.run(["say", "-v", "Samantha", "-o", str(aiff), TEXT], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-ar", "24000", "-ac", "1", str(wav)], check=True)
        store = VoiceStore(Path(__file__).resolve().parent.parent / "voices")
        print(store.create(name, wav.read_bytes(), TEXT, "macOS say voice Samantha (synthetic, no person)", True))


if __name__ == "__main__":
    main(*sys.argv[1:2])
