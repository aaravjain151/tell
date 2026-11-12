"""One-time model download. The ONLY place the project touches the network (Hugging Face).

    python setup_models.py                 # 0.6B-Base TTS + whisper base.en
    python setup_models.py --tts 1.7B      # also/instead the 1.7B-Base TTS
    python setup_models.py --whisper small # multilingual STT for non-English sources

Files land in ./models/<name>; the app itself runs with HF_HUB_OFFLINE=1.
"""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TTS = {"0.6B": "Qwen/Qwen3-TTS-12Hz-0.6B-Base", "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-Base"}
WHISPER = {"tiny.en": "Systran/faster-whisper-tiny.en", "base.en": "Systran/faster-whisper-base.en", "small": "Systran/faster-whisper-small"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tts", nargs="*", default=["0.6B"], choices=list(TTS))
    ap.add_argument("--whisper", nargs="*", default=["tiny.en"], choices=list(WHISPER))
    a = ap.parse_args()
    from huggingface_hub import snapshot_download

    for key in a.tts:
        dest = ROOT / "models" / TTS[key].split("/")[1]
        print(f"[setup] {TTS[key]} -> {dest}")
        snapshot_download(TTS[key], local_dir=dest)
    for key in a.whisper:
        dest = ROOT / "models" / f"whisper-{key}"
        print(f"[setup] {WHISPER[key]} -> {dest}")
        snapshot_download(WHISPER[key], local_dir=dest)
    print("[setup] done. Now run: python run.py")


if __name__ == "__main__":
    main()
