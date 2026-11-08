"""Step 1: cache pellav2's per-layer features for every training clip.

Folder layout (speaker = the person whose voice it is, real or cloned):

    data/real/<speaker>/*.wav
    data/fake/<speaker>/*.wav      (Qwen3-TTS clones of that speaker)

Usage:

    python extract_features.py --weights pellav2_detector.pt --data data --out features
    python extract_features.py ... --opus      # also add WhatsApp-like Opus copies (needs ffmpeg)

Needs pellav2_infer.py (from the model page) in this folder.
"""

import argparse
import csv
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pellav2_infer import Detector, load_clip  # noqa: E402  (pellav2's exact preprocessing)

AUDIO_EXT = {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".opus"}


def find_clips(data_dir: Path):
    clips = []
    for label_name, label in (("real", 0), ("fake", 1)):
        root = data_dir / label_name
        if not root.exists():
            sys.exit(f"Missing folder: {root}")
        for f in sorted(root.rglob("*")):
            if f.suffix.lower() in AUDIO_EXT:
                rel = f.relative_to(root)
                speaker = rel.parts[0] if len(rel.parts) > 1 else f.stem
                clips.append((f, label, speaker))
    return clips


def to_wav(src: Path, dst: Path, opus: bool):
    """Decode any format to 16 kHz WAV with ffmpeg, optionally via a 16 kbps Opus round trip."""
    if opus:
        mid = dst.with_suffix(".opus")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                        "-ac", "1", "-c:a", "libopus", "-b:a", "16k", str(mid)], check=True)
        src = mid
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                    "-ac", "1", "-ar", "16000", str(dst)], check=True)


@torch.no_grad()
def layer_means(model, wav):
    """Masked time-average of every hidden layer -> [layers, hidden]."""
    feats, mask = model.features(wav)
    hs = model.backbone(input_features=feats, attention_mask=mask,
                        output_hidden_states=True).hidden_states
    m = mask[:, :, None].float()
    return torch.stack([(h * m).sum(1) / m.sum(1).clamp(min=1) for h in hs], 1)[0]


def logit_from_means(model, per_layer):
    w = torch.softmax(model.layer_weights, dim=0)
    return model.head((per_layer * w[:, None]).sum(0)).item()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="pellav2_detector.pt")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="features")
    ap.add_argument("--opus", action="store_true", help="add Opus-compressed copies")
    args = ap.parse_args()

    need_ffmpeg = args.opus
    clips = find_clips(Path(args.data))
    if any(f.suffix.lower() not in {".wav", ".flac"} for f, _, _ in clips):
        need_ffmpeg = True
    if need_ffmpeg and not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found: install it, or convert clips to .wav and drop --opus")

    n_real = sum(1 for _, l, _ in clips if l == 0)
    print(f"Found {len(clips)} clips ({n_real} real, {len(clips) - n_real} fake), "
          f"{len({s for _, _, s in clips})} speakers")

    device = ("cuda" if torch.cuda.is_available()
              else "mps" if torch.backends.mps.is_available() else "cpu")
    model = Detector().to(device)
    model.load_state_dict(torch.load(args.weights, map_location=device, weights_only=True))
    model.eval()
    print(f"Model loaded on {device}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    feats, rows = [], []
    variants = [False, True] if args.opus else [False]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for i, (path, label, speaker) in enumerate(clips):
            for aug in variants:
                try:
                    src = path
                    if aug or path.suffix.lower() not in {".wav", ".flac"}:
                        src = tmp / f"clip_{i}_{int(aug)}.wav"
                        to_wav(path, src, opus=aug)
                    wav = torch.from_numpy(load_clip(str(src)))[None].to(device)
                    per_layer = layer_means(model, wav)
                    base_logit = logit_from_means(model, per_layer)
                    if i == 0 and not aug:  # sanity check: cached path == original model
                        full = model(wav).item()
                        assert abs(full - base_logit) < 1e-2, (full, base_logit)
                except Exception as e:
                    print(f"  skipped {path} ({'opus' if aug else 'clean'}): {e}")
                    continue
                feats.append(per_layer.float().cpu().numpy().astype(np.float16))
                rows.append({"path": str(path), "label": label, "speaker": speaker,
                             "aug": "opus" if aug else "clean",
                             "base_p_fake": f"{1 / (1 + np.exp(-base_logit)):.4f}"})
            if (i + 1) % 25 == 0:
                print(f"  {i + 1}/{len(clips)} clips done")

    np.save(out / "feats.npy", np.stack(feats))
    with open(out / "meta.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    base = np.array([float(r["base_p_fake"]) for r in rows])
    labels = np.array([r["label"] for r in rows])
    print(f"\nSaved {len(rows)} feature sets to {out}/")
    print(f"Original pellav2 on this data: fakes caught {np.mean(base[labels == 1] >= 0.5):.1%}, "
          f"real voices flagged {np.mean(base[labels == 0] >= 0.5):.1%}")


if __name__ == "__main__":
    main()
