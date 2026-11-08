# Fine-tune pellav2 on Qwen3-TTS fakes

Trains only pellav2's layer weights and output layer, with the big
w2v-bert-2.0 backbone frozen. Features are cached once, so training
takes minutes, even on CPU.

## 1. Setup (online, once)
    pip install torch torchaudio transformers soundfile numpy scipy pyloudnorm huggingface_hub

Download `pellav2_infer.py` and `pellav2_detector.pt` (2.32 GB) from the
model page into this folder. Re-download the weights if yours are older
than about 1 November 2026 (they were re-uploaded after a corruption
report). Install ffmpeg if you use `--opus` or non-WAV files.

> In this repo a local `pellav2_infer.py` shim is already provided: it exposes
> the same `Detector` and `load_clip` API by reusing Tell's ported
> pellav2 code (`doublespeak/deepfake.py`), so the scripts run offline now and
> the official `pellav2_infer.py` can replace it drop-in.

## 2. Build the dataset
    data/real/<speaker>/*.wav   real speech
    data/fake/<speaker>/*.wav   Qwen3-TTS clones of the same speaker

- Use the same speakers on both sides, so the model learns real vs fake,
  not who is talking. Good recipe: take 20-40 LibriSpeech speakers plus
  your team (with consent), and clone each one with Qwen3-TTS.
- Aim for 300-500 fakes and a similar number of real clips, 4+ seconds each.
- Vary the text: everyday chat, plus your scam scripts.

`make_dataset.py` assembles these folders from the clips already in the repo
(`data/calls/human/*` as real, `data/calls/qwen3tts/*` as fake) and can generate
new Qwen clips if a local `qwen3_tts` package is present:

    python finetune/make_dataset.py --out finetune/data [--include-gradium]
                                    [--librispeech DIR] [--qwen-count N]

## 3. Run
    python extract_features.py --weights pellav2_detector.pt --data data --out features --opus
    python train_head.py --weights pellav2_detector.pt --features features --out pellav2_qwen.pt

Check the before/after table: you want "fakes caught" up and "real
flagged" low on the held-out speakers.

## 4. Use it
    python pellav2_infer.py pellav2_qwen.pt clip.wav

In the app, load `pellav2_qwen.pt` instead of the original weights. The project
also has a config switch: copy the fine-tuned file to
`models/pellav2_detector_finetuned.pt` and run with `TELL_FINETUNED=1` (the old `DOUBLESPEAK_FINETUNED=1` still works)
(or `dataclasses.replace(config.DEEPFAKE, use_finetuned_head=True)`).
Everything runs offline after step 1.

## engine.py note

The task spec refers to `engine.py`; this project has no such file. The
equivalent module is `doublespeak/deepfake.py` (detector, preprocessing, weight
loading, `DeepfakeDetector`). The config switch lives there and in
`doublespeak/config.py`.
