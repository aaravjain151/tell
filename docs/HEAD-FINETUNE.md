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

## Real phone-recorded humans: false-alarm test and retrain (2026-11-07, later the same day)
Status: **evaluated, still NOT wired** (bar not met, see "Bar" below). No `W_*` weight, threshold or scorer change.

### New data
12 iPhone Voice Memos (.m4a, 11 to 20 s each, 171 s total) of the owner's friends, recorded in quiet rooms. They are **phone voice memos, not phone calls**.
Consent: relayed by the owner in `consent.txt` ("we all consent" to being recorded and to use for testing and training the detector), not signed per speaker.
Speaker identities and count are not known. Files are named by recording place: 8 "Northeastern University" (group `neu`), 4 "Huntington Ave" (group `hunt`).
Converted with ffmpeg to 16 kHz mono WAV in the gitignored `data/finetune/humans_new/`; the audio is never committed. Manifest entry with a SHA-256 per file:
`docs/head-finetune/manifest.json`, key `humans_new_2026_11_07`.
Speech check (local faster-whisper base.en, `local_files_only`, numpy input): all 12 are clear English speech following the owner's script:
4 reads of the casual "train was cancelled, still free for dinner?" message, 4 free-speech "my morning / what I ate" clips, 4 reads of the
"security department, read me the code" scam script. Transcripts stay local.

### How many speakers? (an ESTIMATE)
`python3 -I finetune/head_humans.py speakers`: per clip, the mean over its clean 4 s windows of the time-mean hidden state of one frozen layer; cosine
similarity after subtracting the LibriSpeech mean; average-linkage agglomerative clustering; k chosen by silhouette. The layer is picked on LibriSpeech
(80 known speakers): w2v-BERT 2.0 layer 4 (speaker-verification EER 0.065) and wav2vec2 (HF voter backbone) layer 5 (EER 0.081). No ECAPA model is cached.
Full similarity matrices: `docs/head-finetune/humans_speakers.json`.

* wav2vec2 L5, best silhouette k = 4 (0.48): {hunt_2, hunt_3, neu_7}, {hunt_4, hunt_5, neu_8}, {neu_4, neu_5, neu_6}, {neu_1, neu_2, neu_3}.
* w2v-BERT L4, best silhouette k = 5 (0.393; k = 4 also 0.393): the same groups except neu_5 on its own.
* **Best guess: 4 speakers, 3 clips each.** Every guessed cluster holds exactly one clip of each script (train / morning / scam), so the grouping is not
  a same-text artefact (same text would pull different speakers together). The strongest pairs are 0.87 to 0.95 cosine across different scripts.
* The guess says **location is not speaker**: two of the four guessed speakers recorded at both places (neu_7 with hunt_2/3, neu_8 with hunt_4/5).
  So "same location = same speaker group" is NOT conservative here: it can put one speaker in both train and test. I therefore also ran the cluster
  grouping and a **single-group** split (all 12 clips held out together, scored only by models that saw none of them), which is the truly conservative one.
* The LibriSpeech-calibrated cosine threshold (0.25 / 0.36) puts all 12 clips in one cluster: phone memos are much more alike than audiobook speakers,
  so that threshold does not transfer and is not used.

### 1) Do real phone-recorded humans get flagged as AI? (current voters and the existing head)
Current production pipeline (`run_eval.py --wild`, Pellav2 + HF on, thresholds 2026-11-07.3, file-level degradation by `tools/redteam/degrade.py`),
one score per clip (production windows). n = 12 clips in every row.

| condition | fused p_ai >= 0.60 (shipping) | max p_ai | Pellav2 >= 0.5 | HF >= 0.5 | tiers |
|---|---|---|---|---|---|
| clean | 0/12 | 0.29 | 0/12 (max 0.00) | 0/12 (max 0.00) | human 8, scam 4 |
| opus8k | 0/12 | 0.23 | 0/12 (max 0.00) | 0/12 (max 0.08) | human 9, scam 3 |
| g711_mulaw8k | 0/12 | 0.20 | 0/12 (max 0.00) | 0/12 (max 0.01) | human 9, scam 3 |
| chain_replay_call | 0/12 | 0.20 | 0/12 (max 0.00) | 0/12 (max 0.09) | human 10, scam 2 |
| g711_alaw8k | 0/12 | 0.21 | 0/12 (max 0.00) | 0/12 (max 0.01) | human 9, scam 3 |
| speaker_rerecord_sim | 0/12 | 0.23 | 0/12 (max 0.00) | 0/12 (max 0.17) | human 10, scam 2 |
| **opus_lowbitrate_with_loss** | 0/12 | **0.54** | **7/12 (max 1.00)** | 0/12 (max 0.10) | human 10, scam 2 |
| **chain_pstn_voip** | 0/12 | **0.56** | **7/12 (max 1.00)** | 0/12 (max 0.09) | human 8, scam 3, unsure 1 |

"scam" = the human reading the scam script (intent rules; correct behaviour, not an AI false alarm). 0/12 has a 95% upper bound of 26%.
**Finding:** Pellav2 alone calls 7 of 12 real humans synthetic (scores up to 1.00) after 6 kbps Opus with burst loss (our own crude concealment), and
fused p_ai climbs to 0.54 to 0.56, 0.04 under the AI threshold. The same shows on the old reals (Pellav2 FPR@0.5 = 0.55 on the 485 LibriSpeech + Sanath
+ new windows in chain_pstn_voip, `tables_humans.md`). A real low-bitrate lossy call path is the most likely place for a human false alarm today.

Window level (45 windows: 4 s, hop 4 s, max 4 per clip), share of windows >= 0.5 (`docs/head-finetune/humans_falsealarm.json`):

| condition | Pellav2 now | HF now | existing head (`head_pella_mlp.pt`, never saw these speakers) |
|---|---|---|---|
| clean | 0.00 | 0.00 | 0.02 |
| opus8k | 0.00 | 0.00 | **0.18** |
| g711_mulaw8k | 0.00 | 0.00 | 0.13 |
| chain_replay_call | 0.00 | 0.00 | 0.02 |
| g711_alaw8k | 0.00 | 0.00 | 0.16 |
| chain_pstn_voip | **0.51** | 0.02 | 0.07 |

The existing head's clip means stay below 0.5 for all 12 clips in every condition (max clip mean 0.13 clean, 0.41 opus8k, 0.40 g711, 0.27 replay),
but 13 to 18% of its codec windows cross 0.5 where Pellav2 has none: the head trained without phone-memo humans over-flags them.
The JSON also has rates at a "5% FPR on the old reals" threshold; for Pellav2 that threshold is about 0.001, so those columns are not informative.

### 2) Retrain with the new humans in the real class (same protocol)
`python3 -I finetune/head_train_eval.py evaluate --backbone pella --extra-humans {location|cluster|single}`: LibriSpeech + Sanath reals, all fakes, plus the 45
new-human windows; identical degrade chains; leave-one-generator-out x leave-speakers-out, each new group its own extra fold (old speakers keep their
earlier folds). Cells: AUC / TPR@FPR5% / TPR@0.5 / FPR@0.5, out-of-fold. Reals = 485 windows (440 old + 45 new); "new humans as reals" = only the
45 new windows vs the held-out generator. Cluster grouping shown; location and single are within a few points (all in `tables_humans.md`).

| held-out | condition | n real / fake | Pellav2 now | head before (no new humans) | head after (cluster) |
|---|---|---|---|---|---|
| Qwen | opus8k | 485 / 442 | 0.98 / 0.91 / 0.50 / 0.00 | 0.96 / 0.85 / 0.38 / 0.00 | 0.95 / 0.84 / 0.41 / 0.00 |
| Qwen | chain_replay_call | 485 / 442 | 0.58 / 0.06 / 0.01 / 0.01 | 0.65 / 0.16 / 0.06 / 0.01 | 0.63 / 0.17 / 0.05 / 0.00 |
| Gradium | opus8k | 485 / 72 | 1.00 / 1.00 / 0.74 / 0.00 | 1.00 / 1.00 / 1.00 / 0.04 | 1.00 / 1.00 / 1.00 / 0.02 |
| Gradium | chain_replay_call | 485 / 72 | 0.41 / 0.03 / 0.00 / 0.01 | 0.82 / 0.38 / 0.25 / 0.03 | 0.77 / 0.25 / 0.08 / 0.02 |
| `say` | opus8k | 485 / 94 | 1.00 / 1.00 / 1.00 / 0.00 | 1.00 / 1.00 / 1.00 / 0.02 | 1.00 / 1.00 / 1.00 / 0.03 |
| `say` | chain_replay_call | 485 / 94 | 0.73 / 0.19 / 0.03 / 0.01 | 0.92 / 0.66 / 0.54 / 0.02 | 0.89 / 0.57 / 0.46 / 0.01 |
| seen | g711_mulaw8k | 485 / 608 | 0.99 / 0.96 / 0.47 / 0.00 | 0.99 / 0.98 / 0.95 / 0.00 | 0.99 / 0.98 / 0.97 / 0.01 |
| seen | chain_replay_call | 485 / 608 | 0.58 / 0.08 / 0.01 / 0.01 | 0.81 / 0.37 / 0.25 / 0.01 | 0.82 / 0.47 / 0.27 / 0.01 |
| Qwen, new humans as reals | chain_replay_call | 45 / 442 | 0.52 / 0.11 / 0.01 / 0.00 | n/a | 0.67 [0.55, 0.76] / 0.28 / 0.05 / 0.00 |
| Gradium, new humans as reals | chain_replay_call | 45 / 72 | 0.31 / 0.03 / 0.00 / 0.00 | n/a | 0.80 [0.66, 0.91] / 0.32 / 0.08 / 0.02 |
| `say`, new humans as reals | chain_replay_call | 45 / 94 | 0.70 / 0.28 / 0.03 / 0.00 | n/a | 0.95 [0.91, 0.99] / 0.88 / 0.46 / 0.00 |

New-human false alarms of the RETRAINED head (share of the 45 windows >= 0.5; each window scored by a model that never saw its group):

| grouping | model: Qwen held out / all gens seen | clean | opus8k | g711_mulaw8k | chain_replay_call | g711_alaw8k | chain_pstn_voip |
|---|---|---|---|---|---|---|---|
| location | | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.02 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| cluster (best guess) | | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| **single (conservative)** | | 0.00 / 0.00 | 0.00 / 0.02 | 0.00 / **0.09** | 0.00 / 0.04 | 0.00 / **0.09** | 0.00 / 0.00 |
| Pellav2 now | | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.51 |

Reading: when other phone-memo speakers are in training, the head stops flagging these humans (0 to 2%); when none are (single group), it flags up to 9%
of codec windows, like the old head. So the head's false alarms look like a domain-coverage problem that a few speakers fix for this kind of audio, but
we cannot show it generalises to a new recording setup. Adding the humans cost some held-out Gradium replay catch (TPR@FPR5% 0.38 -> 0.25) and nothing
elsewhere beyond noise. In chain_pstn_voip the head is much safer than Pellav2 (FPR@0.5 0.06 to 0.09 vs 0.55 on the 485 reals).

Owner Qwen files (never trained on; mean P(synthetic) over the 3 production windows; head = the fold-model that never saw Sanath):

| file | condition | Pellav2 now | head before: no Qwen / Qwen seen | head after (cluster): no Qwen / Qwen seen |
|---|---|---|---|---|
| rough_morning | clean | 0.67 | 0.59 / 0.78 | 0.14 / 0.81 |
| rough_morning | opus8k | 0.67 | 0.93 / 0.97 | 0.49 / 0.98 |
| rough_morning | chain_replay_call | 0.00 | 0.12 / 0.17 | 0.17 / 0.08 |
| long_tech_scam | clean | 0.02 | 0.62 / 0.69 | 0.36 / 0.73 |
| long_tech_scam | opus8k | 0.00 | 0.57 / 0.96 | 0.62 / 0.97 |
| long_tech_scam | chain_replay_call | 0.00 | 0.32 / 0.31 | 0.14 / 0.21 |

n = 2 files. With Qwen seen the owner clips stay caught in clean/opus8k; with Qwen held out the new humans pull them toward "human" (clean 0.59 -> 0.14).
Neither head catches them through the simulated replay chain.

### 3) Learned fusion (PR #82)
Not done: PR #82 (`feat/personal-learning`, `tools/personal/fusion.py`) is still open and not on main, so there was nothing on main to refit.

### Bar
Bar for proposing the head as an optional voter: on held-out speaker groups, false alarms at the shipping operating point no higher than the current
fusion, AND a better catch rate on held-out generators in the replay chain.
* Replay catch: **met.** Held-out Qwen / Gradium / `say` TPR@0.5 0.05 / 0.08 / 0.46 vs Pellav2 0.01 / 0.00 / 0.03; AUC 0.63 / 0.77 / 0.89 vs 0.58 / 0.41 / 0.73.
* False alarms: **not met / not shown.** The current fusion flags 0/12 new humans in all 8 conditions. The retrained head flags 0% of new-human windows
  only when other phone-memo speakers were in training; in the conservative single-group split it flags up to 9% of codec windows (Pellav2: 0%), and on
  the held-out LibriSpeech/Sanath reals its FPR@0.5 is 0.01 to 0.03 in opus8k/g711 where Pellav2's is 0.00. With 12 clips (4 estimated speakers), a
  "no higher than 0/12" claim has a 95% upper bound of 26% and cannot be established.
So **`neural_head` was not wired.** The retrained head is local only (`data/finetune/head_hum_cluster_pella_mlp.pt`, 1.07 MB, not committed).

### What would change the call
More human speakers on more devices (the single-group result says coverage matters), real phone CALLS rather than memos, a fused-p_ai simulation of the
head at a proposed weight on all held-out reals, and a look at the Pellav2 low-bitrate-loss false alarms (a shipping-voter issue, independent of the head).

### Caveats
* The speaker count (4) is an estimate from embedding clustering; identities are unknown. By that estimate the location groups share speakers.
* Recordings are phone voice memos in quiet rooms: not phone calls, no real network codec, no real replay. All channels are simulated.
* 45 windows from 12 clips; windows of one clip are not independent. Each guessed speaker read the same three scripts: content is balanced but narrow.
* opus_lowbitrate_with_loss uses our own burst-loss concealment, not libopus PLC, so the Pellav2 false alarms there may partly be that artefact.
