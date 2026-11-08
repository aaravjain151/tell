# Small head on frozen SSL layers: recipe and held-out evaluation (2026-11-07)

Status: **evaluated, NOT wired.** No `neural_head` voter ships, no `W_*` weight or threshold changed. The pipeline and the
numbers are here so the decision can be revisited with better data. Why not wired: see "Verdict".

## Why
Our voters (Pellav2, HF wav2vec2) scored Qwen3-TTS clones of Sanath at 0.01 to 0.67 over a phone relay, while a human hears them as fake
at once. The literature (research notes in the session scratchpad, `docs/DETECTION-LAYERS.md`) points at a head of 0.1 to 0.3 M parameters
on frozen intermediate layers of an SSL backbone, trained with codec/channel augmentation on many-speaker real speech, and judged
leave-one-generator-out. `finetune/pellav2_qwen_*` (Samarth's earlier run) proved nothing: 10 validation clips, Sanath in train and val.

## Data and provenance (everything under `data/finetune/`, gitignored; nothing but small JSON/CSV is committed)
| Part | What | n (source clips / 4 s windows) | Licence |
|---|---|---|---|
| Real | LibriSpeech dev-clean + test-clean, 80 speakers x 5 utterances, 4.5 to 14 s | 400 / 400 | CC BY 4.0, https://www.openslr.org/12 (Panayotov et al., ICASSP 2015) |
| Real | Sanath, the repo's own recordings (`data/calls/human/sanath`), consented | 10 / 40 | consent relayed by Aarav (voice-talk `consent.json`) |
| Fake: `qwen` | Qwen3-TTS 0.6B-Base zero-shot clones, local, of 80 LibriSpeech speakers (one 5 to 9 s reference each, 5 texts) + 2 synthetic consented voice-talk demo voices (10 texts each) + the repo's 9 existing Sanath clones | 419 / 442 (plus 6 owner-file windows, eval only) | Apache-2.0 model; LibriSpeech CC BY 4.0 allows the cloning with attribution |
| Fake: `gradium` | the repo's existing Gradium clips (`data/calls/gradium`, `gradium_stock`) | 18 / 72 | already in repo |
| Fake: `say` | macOS `say`, 10 voices x 4 texts (free, local, non-neural; a deliberately different generator) | 40 / 94 | n/a |
| Fake: ElevenLabs | **none**: the repo has no ElevenLabs clip and the paid API is off limits, so it is NOT an evaluation generator | 0 | |

Texts: 20 hand-written conversational/scam sentences + LibriSpeech transcript sentences of other speakers. The two owner files
(`~/Downloads/data_calls_qwen3tts_{rough_morning,long_tech_scam}.wav`; the second is byte-identical to `data/calls/qwen3tts/long_tech_scam.wav`,
which was excluded by hash) are never trained on. `docs/head-finetune/manifest.json` has archive URLs and SHA-256; `sources.csv` has one row per source clip (label, generator,
speaker, SHA-256). Total download 0.7 GB, disk about 4 GB.

Reproduce: untar the two archives under `data/finetune/raw/{dev,test}/`, then
```
python3 finetune/head_build_data.py plan
/Users/aarav/Downloads/voice-talk/.venv/bin/python finetune/head_gen_qwen.py     # local Qwen3-TTS, MPS, ~5.2 s per clip, 36 min for 420 clips
python3 finetune/head_build_data.py finalize
python3 finetune/head_extract.py windows          # 4 s windows x 8 channel conditions (tools/redteam/degrade.py, same code for both classes)
python3 finetune/head_extract.py features pella   # frozen w2v-BERT 2.0, MPS
python3 finetune/head_extract.py features hf      # frozen wav2vec2 (garystafford), MPS
python3 finetune/head_train_eval.py evaluate --backbone pella [--kind linear] [--train-all-conds] [--clean-only]
python3 finetune/head_report.py results_pella_mlp
```

## Method
* Unit: a 4 s window (Pellav2's own preprocessing: DC removal, 20 Hz HPF, -23 LUFS). Degradation is `tools/redteam/degrade.py` (PR #72) applied to the window, identical for both classes.
* Training channels: clean, opus8k, g711_mulaw8k, opus_lowbitrate_with_loss, speaker_rerecord_sim. Eval-only: g711_alaw8k, chain_pstn_voip, and `chain_replay_call` (= speaker_rerecord_sim then opus8k: a composition of two trained pieces, never trained as a chain; `--train-all-conds` adds it and changes little).
* Features: per layer, masked time mean and std of every hidden state of the frozen backbone (25 layers x 1024). Head = learned softmax layer weights, standardise, Dropout 0.3, Linear 2048-128, GELU, Dropout, Linear 128-1: **262,426 parameters, 1.07 MB**. A mean-only linear variant (2,074 parameters) is also reported. Class- and generator-balanced loss (sqrt weighting), AdamW, 25 epochs, no early stopping, no tuning on test data.
* Protocol: speakers split into 5 folds; a window is only scored by a model that never saw its **speaker**. For each generator g in {qwen, gradium, say} the model is also trained **without any g fake**, so fakes are scored by a model that saw neither their generator nor their speaker (pooled out-of-fold). A "speakers held out, generators seen" row is the optimistic reference.
* Baseline: the shipped voters' own probability on the same windows (Pellav2 = `pella.py` forward; HF = `garystafford/wav2vec2-deepfake-voice-detector`), threshold-free metrics plus rates at the fixed 0.5 cut.
* Cost: Pellav2 feature pass about 1 to 2.5 min per condition on MPS (small batches, GPU shared); the whole 20-model cross-validation of a head trains in about 2.5 min on CPU; the final head fits in 4 s. Compute used: MPS for backbones and Qwen generation, CPU for heads.

## Results (head on Pellav2 layers vs the current Pellav2 voter, MLP head, all numbers out-of-fold)
Every number has its n in the table (`n real / n fake` windows). Full tables incl. 95% AUC CIs, g711_alaw8k and chain_pstn_voip: `docs/head-finetune/tables.md` and the raw `results_*.json`.

| scenario | condition | n real / fake | current AUC / TPR@FPR5% / FPR@0.5 | head AUC / TPR@FPR5% / FPR@0.5 |
|---|---|---|---|---|
| hold out Qwen | clean | 440 / 442 | 1.00 / 1.00 / 0.00 | 1.00 / 0.99 / 0.00 |
| hold out Qwen | opus8k | 440 / 442 | 0.98 / 0.91 / 0.00 | 0.96 / 0.85 / 0.00 |
| hold out Qwen | g711 | 440 / 442 | 0.99 / 0.95 / 0.00 | 0.97 / 0.88 / 0.00 |
| hold out Qwen | chain_replay_call | 440 / 442 | 0.58 / 0.06 / 0.01 | 0.65 / 0.16 / 0.01 |
| hold out Gradium | clean | 440 / 72 | 1.00 / 1.00 / 0.00 | 1.00 / 1.00 / 0.00 |
| hold out Gradium | opus8k | 440 / 72 | 1.00 / 1.00 / 0.00 | 1.00 / 1.00 / 0.04 |
| hold out Gradium | g711 | 440 / 72 | 1.00 / 1.00 / 0.00 | 1.00 / 1.00 / 0.02 |
| hold out Gradium | chain_replay_call | 440 / 72 | 0.42 / 0.03 / 0.01 | 0.82 / 0.38 / 0.03 |
| hold out `say` | opus8k | 440 / 94 | 1.00 / 1.00 / 0.00 | 1.00 / 1.00 / 0.02 |
| hold out `say` | chain_replay_call | 440 / 94 | 0.73 / 0.19 / 0.01 | 0.92 / 0.66 / 0.02 |
| generators seen | opus8k | 440 / 608 | 0.99 / 0.94 / 0.00 | 0.99 / 0.97 / 0.02 |
| generators seen | chain_replay_call | 440 / 608 | 0.59 / 0.08 / 0.01 | 0.81 / 0.37 / 0.01 |
| Sanath only, hold out Qwen | chain_replay_call | 40 / 34 | 0.65 / 0.29 / 0.00 | 0.80 / 0.26 / 0.03 |

Reproduced with a different speaker-fold seed (`results_s11_*`): same pattern (held-out-Qwen opus8k TPR@FPR5% 0.80 vs 0.91, replay AUC 0.62 vs 0.58; Gradium replay 0.72 vs 0.42; say replay 0.93 vs 0.73).
Other findings: a **clean-only** head collapses under channel change and on Sanath (Sanath-only AUC 0.18 on clean) so augmentation is not optional; the 2 k-parameter linear head loses more on held-out Qwen opus8k (AUC 0.87, TPR@FPR5% 0.68) and is no safer on false alarms; training on `chain_replay_call` too (`all_*`) does not raise its held-out-Qwen AUC (0.64).
The same head idea on the **HF wav2vec2 backbone** (`docs/head-finetune/table_hf.md`) beats the shipped HF voter everywhere (held-out Qwen replay AUC 0.64 vs 0.38; the shipped HF voter raises false alarms at 0.5 on 27 to 40% of the real windows), but stays below Pellav2 on clean and opus8k.

### The two owner files (never trained on; mean P(synthetic) over the production windows, 3 windows each)
Current voters vs the head fold-model that never saw Sanath real or cloned speech (MLP; "seen" = other Qwen clones in training, "no Qwen" = no Qwen fake at all):

| file | condition | Pellav2 now | HF now | head, no Qwen | head, Qwen seen |
|---|---|---|---|---|---|
| rough_morning | clean | 0.67 | 0.05 | 0.59 | 0.78 |
| rough_morning | opus8k | 0.67 | 0.18 | 0.93 | 0.98 |
| rough_morning | chain_replay_call | 0.00 | 0.20 | 0.12 | 0.17 |
| long_tech_scam | clean | 0.02 | 0.10 | 0.62 | 0.69 |
| long_tech_scam | opus8k | 0.00 | 0.60 | 0.57 | 0.96 |
| long_tech_scam | chain_replay_call | 0.00 | 0.01 | 0.32 | 0.31 |

n = 2 files. The head moves both owner clips toward fake in clean and opus8k (the exact failure) but not enough through the simulated replay chain; the linear head gives 0.93/0.87 clean and 0.35/0.70 replay (Qwen seen).

## Verdict
The head helps where the shipped voters are weakest, **relayed/replayed audio** (replay chain AUC +0.07 to +0.40, TPR at 5% FPR +0.10 to +0.47 for all three held-out generators, replicated with another fold seed), and equals Pellav2 on clean and on held-out Gradium/`say`. But on a held-out **Qwen** it is a little worse than Pellav2 on opus8k and g711 (TPR@FPR5% 0.85 vs 0.91, 0.88 vs 0.95), and its false-alarm rate at the 0.5 cut on held-out real speakers is 0.02 to 0.04 in several cells where Pellav2's is 0.00. The task's bar was "beats the current voters on held-out generators and speakers without raising false alarms", so **the `neural_head` voter was not wired**. A working draft of the voter (HEAD_MODEL, SHA-256 pinned, weights_only, windowed like pella.py) exists but is not in the tree; the final head (1.07 MB) was trained locally at `data/finetune/head_pella_mlp.pt`.
What would change the call: real conversational human speech from many speakers on real phone paths (the main gap), several real replay captures, ElevenLabs and other modern generators, a per-condition calibrated threshold, and fusing the head only when `band_limited` is true.

## Caveats (read before quoting any number)
* **Real speech is read audiobook speech (80 speakers) plus ONE conversational speaker (Sanath, 10 files).** No phone-conversation humans from other speakers, so false alarms on real calls are not bounded by this work.
* Pellav2 already scores about 1.00 on the clean/opus8k LibriSpeech clones, so the held-out sets are easier than the owner files; the head's gain shows only in the replay chain and on the owner clips.
* Channels are **synthetic** (codec simulations and a synthetic RIR, not a measured one); the replay chain is the only stand-in for a speaker-to-mic relay, and no real captured call is in the evaluation.
* Generators: Qwen (one model family, 0.6B), Gradium (18 clips, 2 voices), macOS `say` (non-neural). No ElevenLabs, no Qwen 1.7B. The "hold out Gradium/say" rows have 72 and 94 fake windows from few sources (clips of one file are not independent; AUC CIs in the full table resample whole clips).
* Cloned speakers are the same LibriSpeech speakers that appear as real, which stops a speaker shortcut but means fakes are clones of read speech from a clean reference.
* The held-out fold models were trained on 80% of speakers, hyper-parameters fixed up front; the 262 k-parameter head still carries Sanath-specific signal in the "seen" owner column (other fold models saw him); only the sanath-held-out fold is reported.
* Pellav2 baseline numbers come from the shipped forward on 4 s windows; production averages up to 3 windows per call.
