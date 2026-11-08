# training/ — build Tell's two models

Downloads run **once, online**. Training and use are **fully offline** after.
Every dataset and licence is recorded in [`DATA_SOURCES.md`](../DATA_SOURCES.md).
Two hard rules, enforced in code: **no real call audio/transcripts are stored**,
and **no network at runtime** (only a local Ollama on localhost is allowed).

```
training/
  pellav2-finetune/     PART A - voice model (real vs AI voice)
    pull_real_audio.py    LibriSpeech (40 spk x 15 clips) + consented team voices
    make_fakes.py         Qwen3-TTS clones of those voices -> fake class
    run_training.py       -> finetune/extract_features.py --opus, then train_head.py
  scam-text/            PART B - scam-text model (scam vs not scam)
    pull_text_data.py     3 HF datasets + our scripts -> one parquet
    mine_keywords.py      log-odds phrases -> models/keywords.json
    train_text.py         TF-IDF(1-3) + logreg, hold out whole scam types
  paths.py              shared paths
doublespeak/engine.py   PART C - wires both trained models into the app
```

## Part A — voice model

```bash
pip install datasets soundfile                      # online, once
python training/pellav2-finetune/pull_real_audio.py   # LibriSpeech + team_real
# install Qwen3-TTS from the official repo per its README, then:
python training/pellav2-finetune/make_fakes.py        # clone -> fake class
python training/pellav2-finetune/run_training.py      # features(--opus) + train
# -> models/pellav2_qwen.pt  (+ before/after table printed)
```

Put consented team recordings in `data/team_real/<name>/` before step 1.
`make_fakes.py` clones only public-domain (LibriSpeech) or consented voices and
writes clips strictly as detector training data (see the scope note in that
file and in `DATA_SOURCES.md`).

## Part B — scam-text model

```bash
pip install datasets                                # online, once
python training/scam-text/pull_text_data.py         # -> scam_text.parquet
python training/scam-text/mine_keywords.py          # -> models/keywords.json
python training/scam-text/train_text.py             # -> models/scam_text_model.joblib
```

`train_text.py` holds out **whole scam types** for the test fold, so precision /
recall / false-positive rate reflect unseen scam styles, not leaked near-dupes.

## Part C — wiring

`doublespeak/engine.py` builds a pipeline that uses the fine-tuned pellav2 head
for the voice verdict and the trained scam-text model (with `keywords.json`
reasons) for the conversation verdict. **Ollama is only queried for scam scores
between 0.3 and 0.7** (the uncertain band); outside it the trained model is
trusted. `app.py` calls `build_engine_pipeline()` and falls back to the base
pipeline if any trained artifact is missing, so the app always runs.

## What's committed

Code, `keywords.json`, metrics and small model artifacts are committed.
Downloaded corpora, generated audio, cached features, the 2.2 GB checkpoint and
team recordings are **git-ignored** and regenerated locally.
