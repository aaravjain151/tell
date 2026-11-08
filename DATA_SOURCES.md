# Data sources & licences

Every external dataset used to **train** Tell's models is listed here,
with its licence and how we use it. This is a hard requirement of the project:
nothing trains on data whose licence we have not recorded.

Two unbreakable rules, enforced in code and honoured here:

1. **No real call audio or transcripts are ever stored.** Live calls are
   processed in memory and dropped. Training uses only the public / consented
   datasets below.
2. **No network access at runtime.** Downloads happen once, online, via the
   `training/` scripts. Training and inference are then fully offline.

---

## Part A — voice model (real vs AI-generated speech)

### LibriSpeech ASR (real speech)
- **Source:** `openslr/librispeech_asr` on Hugging Face (config `clean`).
- **Origin:** LibriSpeech, derived from public-domain LibriVox audiobooks.
- **Licence:** CC BY 4.0 (dataset); underlying audio is public domain.
- **Use:** a subset of real human voices (40 speakers × 15 clips, 4–12 s) as the
  REAL class. Converted to 16 kHz mono WAV locally; originals not redistributed.
- **Attribution:** Panayotov et al., "LibriSpeech: an ASR corpus based on public
  domain audiobooks," ICASSP 2015.

### Team recordings (real speech, consented)
- **Source:** `data/team_real/<name>/` — recordings by project team members.
- **Licence / consent:** contributed by the speakers themselves, with explicit
  consent to use for training a *detector*. No third-party or non-consenting
  voices. Not committed to the repo (kept local, git-ignored).

### Qwen3-TTS (AI-generated speech)
- **Source:** `QwenLM/Qwen3-TTS` (official repo) — model
  `Qwen3-TTS-12Hz-1.7B-Base` (or the 0.6B variant on <8 GB GPUs).
- **Licence:** per the Qwen3-TTS model card / repository licence (Apache-2.0
  family at time of writing — verify on the model page before redistributing).
- **Use:** generate the FAKE class by cloning the voices already collected above
  (LibriSpeech + consented team voices) from varied text. **Scope limit:** the
  synthetic clips are negative-class *training examples for the detector only*.
  They are written to disk as training data, never used to impersonate a person
  to a listener. We do not clone any voice that is not public-domain or
  explicitly consented.

---

## Part B — scam-text model (scam vs not-scam transcripts)

### Single-agent scam conversations
- **Source:** `BothBosu/single-agent-scam-conversations` (Hugging Face).
- **Use:** labelled scam vs non-scam conversation text.

### Multi-agent scam conversations
- **Source:** `BothBosu/multi-agent-scam-conversation` (Hugging Face).
- **Use:** labelled scam vs non-scam conversation text.

### Robocall gate dataset
- **Source:** `sugiv/call-gate-robocalls` (Hugging Face).
- **Use:** labelled robocall / legitimate call text.

> Licences for the three text datasets are whatever is stated on each Hugging
> Face dataset page. Record the exact licence string shown there before any
> redistribution; `pull_text_data.py` prints each dataset's reported licence at
> download time so it can be captured here.

### Our own scam scripts (authored in-house)
- **Source:** `data/own_scripts/*.txt` and `data/scam_scripts.txt` — grandparent
  / IRS / bank-OTP style scripts written by the team for coverage.
- **Licence:** authored by us; released for use within this project.

---

## What is committed vs. kept local

- **Committed:** the training *code*, the mined `keywords.json`, model metrics,
  and small model artifacts (e.g. the ~6 KB pellav2 head delta, the joblib
  text model if small enough).
- **Not committed (git-ignored):** downloaded corpora, generated audio, cached
  features, full 2.2 GB checkpoints, and any team recordings. These are
  regenerated locally by the `training/` scripts.
