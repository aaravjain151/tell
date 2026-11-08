# Learned tells: what gives an AI voice away, learned from every clip we have (2026-11-08)

Status: **shipped, on by default** (thresholds `2026-11-08.1`). Voter `learned_tells` (`services/api/tell/signals/learned.py`,
weight 8.0), plus three engine fixes (Pellav2 on every window with a logit mean, `breath_proxy` weight 0, `band_limited`
re-defined). `TELL_LEARNED_TELLS=0` turns the voter off. Code for the study: `training/learned_tells/`.

Read the caveats before quoting any number: the human class is read audiobook speech (80 speakers) plus ONE conversational
speaker (Sanath) plus 12 phone memos (4 speakers, estimated); every channel is simulated; the replay chain is still unsolved.

## What changed in the engine, in one table (voice only, held out; catch = AI clips at p_ai >= 0.60)

Every clip is scored by a model that never saw its speaker group; "held-out X" rows by a model that never saw ANY fake of X.
n = 435 human clips (400 LibriSpeech, 23 Sanath, 12 phone memos) in every row; human false alarms at 0.60 are **0 in every
cell below, before and after**.

| scenario (n AI) | condition | current engine: AUC / catch | new engine: AUC / catch | catch at the current engine's false-alarm count (0), before -> after |
|---|---|---|---|---|
| all generators seen (484) | clean | 0.99 / 0.61 | 1.00 / **0.94** | 0.90 -> 1.00 |
| | opus8k | 0.87 / 0.38 | 0.99 / **0.57** | 0.64 -> 0.89 |
| | g711 mu-law | 0.83 / 0.25 | 1.00 / **0.51** | 0.56 -> 0.95 |
| | replay (speaker -> room -> opus) | 0.51 / 0.00 | 0.66 / 0.00 | 0.00 -> 0.00 |
| held-out Qwen (426) | clean | 0.99 / 0.55 | 1.00 / **0.90** | 0.89 -> 0.98 |
| | opus8k | 0.85 / 0.32 | 0.97 / **0.44** | 0.60 -> 0.77 |
| | g711 | 0.81 / 0.18 | 0.99 / **0.42** | 0.52 -> 0.91 |
| | replay | 0.50 / 0.00 | 0.61 / 0.00 | 0.00 -> 0.00 |
| held-out Gradium (18) | clean | 1.00 / 0.94 | 1.00 / **1.00** | 1.00 -> 1.00 |
| | opus8k | 1.00 / 0.56 | 1.00 / **0.72** | 0.78 -> 1.00 |
| | g711 | 0.96 / 0.28 | 1.00 / **0.56** | 0.72 -> 1.00 |
| | replay | 0.70 / 0.00 | 0.66 / 0.00 | 0.00 -> 0.00 |
| held-out macOS say (40) | clean / opus8k / g711 | 1.00 / 1.00 each | 1.00 / 1.00 each | 1.00 -> 1.00 |
| | replay | 0.58 / 0.00 | 0.84 / 0.00 | 0.00 -> 0.00 |

AUC 95% bootstrap intervals (resampling clips) are in the full table, `training/learned_tells/report.py` output, reproduced in
the appendix. Lossy paths, where the current engine already false-alarms (our crude 6 kbps Opus + burst-loss concealment):

| condition | human false alarms at 0.60: current -> fixes only -> new engine (n = 435) | catch, all AI (n = 484) |
|---|---|---|
| chain_pstn_voip | **156 -> 221 -> 73** | 0.79 -> 0.92 -> 0.72 |
| opus_lowbitrate_with_loss | **161 -> 234 -> 68** | 0.79 -> 0.93 -> 0.74 |

The voter halves the false alarms there (all of them LibriSpeech and phone-memo clips, driven by Pellav2 scoring lossy humans
as synthetic); the two fixes alone would have RAISED them, so they only ship together with the voter (see "Decision").

## Data (all local, read-only; caches in a scratch folder, nothing committed but code, the 289 KB weights and tables)

| class | source | clips | used as |
|---|---|---|---|
| human | LibriSpeech dev/test-clean, 80 speakers x 5 (CC BY 4.0, from the head study) | 400 | train/CV, 5 speaker folds |
| human | Sanath, `data/calls/human/sanath` (+3 raw m4a takes with no converted twin) | 23 | train/CV, own group |
| human | 12 phone memos of the owner's friends (consent relayed, `human_recordings/consent.txt`), 4 estimated speakers | 12 | train/CV, one group per estimated speaker; also all 12 held out together |
| AI | Qwen3-TTS 0.6B clones of the 80 LibriSpeech voices + 2 synthetic demo voices | 408 | train/CV (a clone shares its real speaker's fold) |
| AI | Qwen3-TTS clones of Sanath, `data/calls/qwen3tts` (paired by script) | 18 | train/CV with Sanath's group; script split |
| AI | Gradium (`gradium`, `gradium_stock`) | 18 | train/CV, held out as a generator |
| AI | macOS `say`, 10 voices | 40 | train/CV, held out as a generator |
| AI, test only | the two owner files (`rough_morning`, `long_tech_scam`; the repo copies are excluded from training) | 2 | pure test |
| AI, test only | ElevenLabs `eleven_multilingual_v2` lines from the launch film (generator never trained on) | 9 lines, 0.5-2.8 s | pure test (lines and concatenations) |
| AI, test only | Qwen3-TTS **1.7B** takes (a model size never trained on), voice-talk QA calls | 4 + 4 | pure test |

Units: every non-silent 4 s window at a 2 s hop (the production windowing, uncapped): 3,488 windows per condition (1,639 human,
1,849 AI, 143 test). Conditions via `tools/redteam/degrade.py`, applied to the whole clip, identical for both classes.
Training: clean, opus8k, g711_mulaw8k, speaker_rerecord_sim, opus_lowbitrate_with_loss. Evaluation: clean, opus8k, g711_mulaw8k,
chain_replay_call (never trained as a chain), plus chain_pstn_voip for false alarms.

## Method

* **Features per window** (cached, `training/learned_tells/extract.py`): every existing Tell score; Pellav2 on EVERY window
  (probability and the masked time-mean of all 25 w2v-BERT 2.0 layers, from the same forward pass); the HF voter per window and
  per call; 28 interpretable tells in `services/api/tell/signals/tell_features.py` (numpy, the same code ships): pitch spread,
  range, speed, micro-wobble, jitter/shimmer proxies, pitch-loudness coupling, HNR, cepstral peak prominence, harmonic-valley
  depth, harmonic in-tune-ness (instantaneous frequency), group-delay spread (vocoder phase), envelope roughness, 4-16 Hz
  modulation, spectral flux/tilt/flatness, low-mid balance, pause share/length/depth/texture/wobble, breath-like events, and the
  channel descriptors (noise floor, SNR, 5-7.5 kHz level, exact zeros) kept apart as `CHANNEL_FEATURES`.
* **Models** (`evaluate.py`): L2 and L1 logistic regression on interpretable tells alone, on a PCA-32 of the layer-12 embedding
  alone, and on both (+ the Pellav2 logit); a small gradient-boosted model (sklearn, depth 3) as a check. Median imputation,
  standardising, PCA and C (inner 3-fold group CV) are fitted on training folds only. Class weights balance human/AI; inside
  each class sources are weighted by sqrt(n) so LibriSpeech and the Qwen clones do not drown the rest. Call score = mean of
  window logits.
* **Human-centred calibration** (the `_cal` variant that ships): after fitting, the logit is shifted so 0 is the 99th
  percentile of human clip logits scored out-of-fold inside the training data. Without it, a voter that never saw a generator
  gives that generator's fakes moderate probabilities and, fused, LOWERED held-out Qwen catch (0.85 -> 0.55 at 0.60). With it,
  the voter reads "how unlike the real voices we trained on", which held up for every held-out generator.
* **Evaluation**: leave-one-generator-out (Qwen, Gradium, say) x leave-one-speaker-group-out (5 LibriSpeech folds, Sanath, each
  estimated friend speaker); the 12 memos also held out together; Sanath vs his Qwen clones split BY SCRIPT; owner, ElevenLabs,
  Qwen 1.7B and QA files never in any fold. Fused p_ai is rebuilt exactly as `scorer._wmean` does from the engine's own
  components, and the shipped artifact was then run through the real `pipeline.analyze` on the test files (the simulation and
  the pipeline agree to 2 decimals on the owner files).

## Which model (learned score alone, clip AUC; same folds)

| model | seen: clean / opus8k / g711 / replay | held-out Qwen | held-out Gradium | held-out say |
|---|---|---|---|---|
| current engine fused p_ai | 0.99 / 0.87 / 0.83 / 0.51 | 0.99 / 0.85 / 0.81 / 0.50 | 1.00 / 1.00 / 0.96 / 0.70 | 1.00 / 1.00 / 1.00 / 0.57 |
| Pellav2 all windows alone | 0.99 / 0.92 / 0.88 / 0.49 | 0.99 / 0.91 / 0.86 / 0.48 | 1.00 / 1.00 / 0.91 / 0.62 | 1.00 / 1.00 / 1.00 / 0.51 |
| interpretable tells, L2 | 0.83 / 0.82 / 0.83 / 0.67 | 0.70 / 0.70 / 0.70 / 0.60 | 0.71 / 0.73 / 0.74 / 0.62 | 0.97 / 1.00 / 0.97 / 0.73 |
| interpretable tells, L1 | 0.77 / 0.77 / 0.74 / 0.62 | 0.50 / 0.50 / 0.50 / 0.50 | 0.59 / 0.55 / 0.51 / 0.31 | 0.75 / 0.73 / 0.74 / 0.58 |
| interp + Pellav2 logit, L2 | 0.98 / 0.92 / 0.92 / 0.67 | 0.90 / 0.81 / 0.80 / 0.60 | 0.98 / 0.94 / 0.90 / 0.60 | 1.00 / 1.00 / 1.00 / 0.76 |
| gradient boosting (interp + Pellav2 + HF) | 1.00 / 1.00 / 1.00 / 0.73 | 0.89 / 0.76 / 0.76 / 0.59 | 1.00 / 1.00 / 1.00 / 0.68 | 1.00 / 1.00 / 1.00 / 0.92 |
| embedding PCA-32, L2 | 1.00 / 1.00 / 1.00 / 0.69 | 1.00 / 0.99 / 1.00 / 0.63 | 1.00 / 1.00 / 1.00 / 0.55 | 1.00 / 1.00 / 1.00 / 0.90 |
| interp + embedding, L2 | 1.00 / 0.99 / 1.00 / 0.74 | 0.98 / 0.91 / 0.95 / 0.64 | 1.00 / 1.00 / 1.00 / 0.64 | 1.00 / 1.00 / 1.00 / 0.92 |
| interp + embedding + Pellav2, L2 | 1.00 / 0.99 / 1.00 / 0.74 | 0.99 / 0.94 / 0.97 / 0.64 | 1.00 / 1.00 / 1.00 / 0.63 | 1.00 / 1.00 / 1.00 / 0.92 |
| **shipped: embedding, L2, human-centred** | 1.00 / 1.00 / 1.00 / 0.70 | 1.00 / 0.99 / 1.00 / 0.65 | 1.00 / 1.00 / 1.00 / 0.56 | 1.00 / 1.00 / 1.00 / 0.89 |

Reading: a linear read-out of the frozen w2v-BERT layer 12 generalises to held-out generators far better than our hand-written
tells (held-out Qwen 0.99-1.00 vs 0.70), and adding the tells to it makes held-out Qwen slightly WORSE (they carry
generator-specific directions: e.g. pitch moves faster in Gradium and ElevenLabs but slower in Qwen and `say`). The gradient
boosting check over-fits seen generators. So the voter votes from the embedding; the interpretable model only names the tells
in the evidence line. Layer choice (4/8/12/16/20/24 gave 0.92-0.96 on a clean-only pass) was not tuned further. Weight 8 was the
largest of {4, 6, 8, 12, 16} at which no held-out cell caught less than the current engine (12 lost held-out Qwen opus8k);
choosing it on these same folds is a mild optimism, disclosed.

## The tells: what gives an AI voice away (interpretable L2 model, all training clips, standardised weights)

AUC columns are each tell ALONE (clip median, all AI vs all humans), clean / opus8k / g711 / replay; "survives" = same side of
0.5 as the weight, by at least 0.05, in that condition. L1 (C chosen by inner CV) keeps only the top three.

| rank | tell | toward AI | weight (L2 / L1) | AUC alone c / o / g / r | survives phone + replay | plain English |
|---|---|---|---|---|---|---|
| 1 | cpp_db | voice too regular and clean | +0.46 / +0.34 | 0.78 / 0.79 / 0.75 / 0.64 | yes | the voicing is more perfectly periodic than a real throat makes it |
| 2 | pause_wobble_db | pause level jumps | +0.26 / +0.08 | 0.71 / 0.70 / 0.70 / 0.68 | yes | silences are rendered (gated, jumping), not a steady room tone |
| 3 | spectral_flux | slow spectral change | -0.25 / -0.07 | 0.30 / 0.30 / 0.30 / 0.32 | yes | the sound changes more smoothly from one 10 ms to the next |
| 4 | pause_flatness | hiss-like pause noise | +0.25 / 0 | 0.55 / 0.56 / 0.59 / 0.39 | phone only (flips in replay) | what little noise sits in pauses is featureless hiss |
| 5 | lowmid_balance_db | weak low-mids | -0.24 / 0 | 0.41 throughout | yes (but likely mic/recorder) | 500-1000 Hz vs 100-500 Hz balance differs |
| 6 | spectral_tilt_db | dark voice | -0.20 / 0 | 0.38 / 0.39 / 0.38 / 0.39 | yes (likely partly recorder) | less 1-3.4 kHz energy relative to the lows |
| 7 | pause_share | few pauses | -0.17 / 0 | 0.35 / 0.33 / 0.34 / 0.46 | phone only | it barely stops talking |
| 8 | harm_valley_db | clean gaps between harmonics | +0.15 / 0 | 0.65 / 0.66 / 0.63 / 0.58 | yes | no breath noise between the harmonics |
| 9 | pause_depth_db | very deep, silent pauses | -0.12 / 0 | 0.44 / 0.41 / 0.43 / 0.60 | phone only | pauses drop far below speech level |
| 10 | mod_4_16 | strong, even syllable beat | +0.10 / 0 | 0.58 / 0.60 / 0.60 / 0.63 | yes | the syllable rhythm is unusually regular |
| 11 | f0_energy_corr | pitch tied to loudness | +0.10 / 0 | 0.62 / 0.63 / 0.63 / 0.56 | yes | louder always means higher, as a rule |
| 12 | harm_if_dev | harmonics stray from the pitch | +0.09 / 0 | 0.25 / 0.25 / 0.26 / 0.39 | only jointly (alone it says the opposite) | |

The rest (group delay, shimmer, HNR, breath events, pitch range/spread/speed/micro-wobble, envelope roughness, jitter) have
|weight| < 0.09. Cross-generator directions that did NOT replicate: pitch speed (up for Gradium 0.85 and ElevenLabs 0.83, down
for Qwen 0.45 and `say` 0.28), pause share, spectral tilt. This model alone is weak (AUC 0.83 seen, 0.70 held-out Qwen): it is
the explanation layer, not the detector. It agrees with `docs/QWEN-CUES.md` (CPP strongest and phone-robust; silence too clean).

## The three engine fixes

* **Pellav2**: every window up to 16 (was 3), call score = sigmoid(mean window logit) with window P clipped to [0.01, 0.99].
  Alone on the current fusion it lifts Qwen catch a little (clean 0.55 -> 0.60, opus8k 0.32 -> 0.38, g711 0.18 -> 0.24) and,
  with a 1e-4 clip, added one replay false alarm (a 2-window LibriSpeech clip with windows 0.998 / 0.016 became 0.74 instead of
  0.51); clipping window P at 0.01 removes it (max human p_ai in replay 0.62 -> 0.50) at a cost of <= 2 points of catch. The clip
  value was chosen on these folds, disclosed. Latency: a live 10 s tick now scores 4 windows (was 3); a 60 s file 16.
* **breath_proxy 1.2 -> 0**: mean score 0.19 on humans vs 0.27 on AI (clean), ~0.1-0.24 everywhere: a near-constant pull toward
  "human". My own breath detector (`breath_rate`) did not separate either (AUC 0.40-0.63 by generator), so it is shown, not fused.
  Clean catch with the current fusion 0.61 -> 0.82, no new false alarm in clean/opus8k/g711/replay; but on lossy paths it uncovers
  Pellav2's false alarms (156 -> 190), which is why it only ships with the voter.
* **band_limited**: now 5-7.5 kHz energy relative to 1-4 kHz below -37 dB. On the same 949 clips: clean -31 to +7 dB (0/949
  flagged; the old rule flagged 71% of clean clips); opus8k -42 to -69, G.711 -40 to -80, replay chain -43 to -69 (949/949
  flagged each); our lossy concealment adds broadband clicks so about half of those clips read as wideband (a missed flag, not a
  false "no content above 4 kHz" line). 4-8 kHz did not separate (codec transition band). The user-facing line now reads
  "phone-band audio (5-7.5 kHz is X dB below 1-4 kHz, as after a phone codec): detectors are less reliable here". Display only.

## Pure test sets (the real pipeline, voice only; never trained on)

| file | condition | before p_ai (tier) | after p_ai (tier) | learned |
|---|---|---|---|---|
| owner `rough_morning` (Qwen clone of Sanath) | clean | 0.40 (human) | **0.67 (ai_undisclosed)** | 0.76 |
| | opus8k | 0.40 (human) | 0.55 (unsure) | 0.72 |
| | g711 | 0.09 (human) | 0.44 (human) | 0.73 |
| | replay | 0.08 (human) | 0.22 (human) | 0.36 |
| owner `long_tech_scam` | clean | 0.15 (human) | 0.57 (unsure) | 0.81 |
| | opus8k | 0.20 (human) | 0.41 (human) | 0.60 |
| | g711 | 0.14 (human) | 0.36 (human) | 0.55 |
| | replay | 0.05 (human) | 0.26 (human) | 0.47 |
| ElevenLabs, all 9 lines concatenated (17.8 s) | clean / opus8k / g711 | 0.69 / 0.69 / 0.69 (AI) | **0.80 / 0.80 / 0.80 (AI)** | 0.82 |
| | replay | 0.14 (human) | 0.28 (human) | 0.40 |
| ElevenLabs, caller voice (8.0 s) | g711 | 0.65 (unsure) | **0.78 (AI)** | 0.83 |
| ElevenLabs, Meera voice (8.2 s) | clean / opus / g711 / replay | 0.67 / 0.70 / 0.68 / 0.14 | 0.79 / 0.80 / 0.79 / 0.27 | 0.82 / 0.81 / 0.81 / 0.37 |
| ElevenLabs single lines (0.5-2.8 s) | all | 0.50 (unsure) | 0.50 (unsure) | not scored: < 3 s, by design |
| Qwen 1.7B takes (1.1-2.3 s) | all | 0.50 | 0.50 | not scored: < 3 s |
| voice-talk QA calls (Qwen, 4 calls) | clean / opus / g711 | 0.64-0.67 (2 unsure, 2 AI) | **0.76-0.79 (all AI)** | 0.79-0.83 |
| | replay | 0.19-0.31 (human) | 0.22-0.33 (human) | 0.28-0.41 |

Owner files with a model that never saw Sanath or any Sanath clone: learned 0.76 / 0.79 clean, fused 0.67 / 0.55 (vs 0.67 /
0.57 with the shipped model): the gain is not memorised from his other clones. n = 2 owner files, 3 ElevenLabs concatenations
(2 voices), 4 QA calls: a direction, not a rate.

## Live replay check (tools/macos/listen.py --file, real time, spare engines: before = main on :8015, after = this branch on :8016)

Both engines: Pellav2 + HF on, local whisper base.en for the transcript, LLM stub. Per-tick raw p_ai (10 s window, 3 s hop) and
the final displayed (stabilised) state. Latency per tick 0.9-1.6 s on both after the fix below (an earlier draft recomputed the
features 28x per window: 3.2 s per tick; caught here, fixed, now tested).

| file | before: raw p_ai per tick | after: raw p_ai per tick | final shown state before -> after |
|---|---|---|---|
| Qwen clone of Sanath, `long_tech_scam` (22 s) | 0.03 0.12 0.19 0.22 0.28 0.38 0.38 | 0.29 0.29 0.41 0.47 0.54 0.57 **0.62** | scam (latched, red) -> scam (latched, red); the voice reaches AI tier only on the last tick |
| Gradium `scam_irs` (16 s) | 0.73 0.53 0.69 0.62 0.62 | 0.65 0.61 0.69 0.70 0.69 | scam (red) -> scam (red) |
| ElevenLabs, all 9 lines (17.8 s, never trained) | 0.76 0.59 0.63 0.64 0.62 0.65 | 0.71 0.68 0.73 0.74 0.72 | unsure at 9 s, then scam (red) -> ai_undisclosed at 9 s, then scam (red) |
| Sanath, real, `scam_irs` (16 s) | 0.04 0.07 0.09 0.17 0.20 | 0.11 0.10 0.11 0.19 0.21 | scam (red, his scam-script read) -> same; voice stays human-side |
| voice-talk attacker demo call (92 s, Qwen) | 0.96 ... 0.53-0.88 (4 ticks raw human/unsure) | 0.96 ... 0.64-0.81 (2 ticks raw unsure) | ai_undisclosed then scam (amber at 83 s, red at 92 s) -> ai_undisclosed throughout (the after run's stream ended at 85 s, before the scam words were transcribed; p_scam path untouched) |

n = 5 files, one run each: a smoke test of the live path, not a rate.

## Other held-out checks

* **All 12 phone memos held out together** (no phone-memo speaker in training): learned score max 0.28 clean, 0.46 opus8k,
  0.37 g711, 0.43 replay; fused max 0.19 / 0.32 / 0.24 / 0.26; 0/12 false alarms in every condition (95% upper bound 26% on 12).
* **Sanath vs his Qwen clones, held out by script** (23 real / 18 Qwen clips; the model saw his other scripts): learned AUC 1.00 /
  1.00 / 1.00 / 0.90 [0.78, 0.98] (clean/opus8k/g711/replay); fused catch at 0.60: current 0.06 / 0.06 / 0.00 / 0.00, new 0.56 /
  0.06 / 0.00 / 0.00, 0 false alarms on his 23 real clips. The learned score separates his clones perfectly through codecs, but
  in the fusion it is outvoted by Pellav2 and the behavioural tells, which read his clones as human under codecs.

## Decision: on by default, and why

The bar (owner): on held-out generators and held-out human speaker groups, more catch in clean AND phone/replay without more
human false alarms at the shipping threshold, golden eval green.
* Clean: met for every held-out generator (Qwen 0.55 -> 0.90).
* Phone codecs (opus8k, G.711): met for every held-out generator (held-out Qwen 0.32 -> 0.44, 0.18 -> 0.42).
* Replay (speaker -> room -> Opus): **not improved at 0.60** (0.00 before and after, every generator); AUC rises (0.51 -> 0.66
  seen, 0.58 -> 0.84 held-out `say`) except held-out Gradium (0.70 -> 0.66). No regression in catch or false alarms there.
* False alarms at 0.60: 0 before and 0 after on 435 held-out human clips in clean/opus8k/g711/replay, 0/12 memos when all are
  held out together; on the lossy paths 156 -> 73 and 161 -> 68.
* Golden eval: PASS, identical to main (transcript 0.98 over 32, synthetic audio 1.00 over 48). Scam-wording path untouched.
I read "phone/replay" as the phone family; replay is reported as not improved rather than claimed. If the owner reads it as
"replay too", set `TELL_LEARNED_TELLS=0`, but then ALSO revert `breath_proxy` (thresholds) because the breath fix without the
voter raises lossy false alarms (156 -> 190). The voter needs Pellav2 (it reads its embedding); with Pellav2 off it is not
applicable and the breath change is harmless (no Pellav2 false alarms to uncover).

## Limits (what this does not show)

* Human speech: 400 audiobook clips, one conversational speaker, 12 quiet-room phone memos. No real phone CALLS from other
  speakers; no accents or ages beyond those. False alarms on real calls are not bounded by this.
* Channels are simulated; the lossy condition uses our crude concealment, not libopus PLC; no measured room, no real captured
  call. The replay chain is unsolved by every model here (best learned AUC 0.74, catch 0 at 0.60).
* Generators: Qwen 0.6B (most fakes), Gradium (2 voices, 18 clips), macOS `say`; ElevenLabs and Qwen 1.7B only as tiny test
  sets, and most of those lines are under 3 s, which the engine does not score.
* Windows of one clip are not independent; AUC intervals resample clips, not speakers. Weight 8 and the Pellav2 clip were
  picked on the same folds they are reported on.
* The interpretable tells explain; they do not detect well on unseen generators (held-out Qwen AUC 0.70).

## What data would push this further

Real phone calls (both sides, consented) from many speakers and phones, including replayed AI (an AI voice played into a phone
mic); 20+ conversational human speakers on different mics; ElevenLabs, Cartesia, OpenAI and Qwen 1.7B clips of 6 s or more at
volume; real codec captures (AMR-NB, EVS, WhatsApp/FaceTime) instead of simulations; a replay-augmented training set with
measured room responses.

## Reproduce

```
export LT_DIR=<scratch>          # caches go here, never in the repo
python3 -I training/learned_tells/extract.py sources && ... audio && ... neural && ... feats      # ~45 min on Apple MPS
python3 -I training/learned_tells/evaluate.py models 12 emb_l2_cal      # + other families; also: single, scripts, lossy
python3 -I training/learned_tells/report.py $LT_DIR/oof_L12_emb_l2_cal.json emb_l2_cal 8
python3 -I training/learned_tells/tells.py; python3 -I training/learned_tells/band.py; python3 -I training/learned_tells/bugfix.py clean,opus8k
python3 -I training/learned_tells/export.py emb_l2_cal 12               # writes learned_tells.json, prints the SHA-256 to pin
python3 -I training/learned_tells/pipeline_eval.py services/api out.json  # real pipeline on the pure test sets
```
Sources: LibriSpeech/Qwen-clone/`say` audio from the head study's local data (`docs/HEAD-FINETUNE.md`), `data/calls`, the
friends' memos converted in the head study, the launch-film VO, the voice-talk QA calls, the two owner files.

## Appendix: full held-out table (learned_tells W 8, `report.py`)

"TPR at matched FA" = catch at the lowest cut that flags no more held-out humans than the current engine does at 0.60 (that
count is in brackets; it is 0 everywhere here). FA / TPR at 0.60 = the shipping threshold. n human / n AI per row.

| scenario | condition | engine | n human / n AI | AUC [95% CI] | TPR at matched FA (FA) | FA at 0.60 | TPR at 0.60 |
|---|---|---|---|---|---|---|---|
| seen | clean | current | 435 / 484 | 0.987 [0.98, 0.99] | 0.90 (0) | 0 | 0.61 |
| seen | clean | fixes only (breath 0, Pellav2 all windows) | 435 / 484 | 0.980 [0.97, 0.99] | 0.95 (0) | 0 | 0.87 |
| seen | clean | **new engine** (fixes + learned_tells W 8) | 435 / 484 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 0.94 |
| seen | clean | learned_tells score alone | 435 / 484 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 0.98 |
| seen | opus8k | current | 435 / 484 | 0.869 [0.84, 0.89] | 0.64 (0) | 0 | 0.38 |
| seen | opus8k | fixes only (breath 0, Pellav2 all windows) | 435 / 484 | 0.849 [0.82, 0.87] | 0.64 (0) | 0 | 0.53 |
| seen | opus8k | **new engine** (fixes + learned_tells W 8) | 435 / 484 | 0.990 [0.99, 0.99] | 0.89 (0) | 0 | 0.57 |
| seen | opus8k | learned_tells score alone | 435 / 484 | 0.998 [1.00, 1.00] | 0.88 (0) | 0 | 0.75 |
| seen | g711_mulaw8k | current | 435 / 484 | 0.831 [0.80, 0.86] | 0.56 (0) | 0 | 0.25 |
| seen | g711_mulaw8k | fixes only (breath 0, Pellav2 all windows) | 435 / 484 | 0.807 [0.78, 0.84] | 0.54 (0) | 0 | 0.42 |
| seen | g711_mulaw8k | **new engine** (fixes + learned_tells W 8) | 435 / 484 | 0.996 [0.99, 1.00] | 0.95 (0) | 0 | 0.51 |
| seen | g711_mulaw8k | learned_tells score alone | 435 / 484 | 1.000 [1.00, 1.00] | 0.97 (0) | 0 | 0.86 |
| seen | chain_replay_call | current | 435 / 484 | 0.510 [0.47, 0.55] | 0.00 (0) | 0 | 0.00 |
| seen | chain_replay_call | fixes only (breath 0, Pellav2 all windows) | 435 / 484 | 0.485 [0.45, 0.52] | 0.00 (0) | 0 | 0.00 |
| seen | chain_replay_call | **new engine** (fixes + learned_tells W 8) | 435 / 484 | 0.662 [0.63, 0.69] | 0.00 (0) | 0 | 0.00 |
| seen | chain_replay_call | learned_tells score alone | 435 / 484 | 0.700 [0.66, 0.73] | 0.06 (0) | 0 | 0.02 |
| no_qwen | clean | current | 435 / 426 | 0.985 [0.98, 0.99] | 0.89 (0) | 0 | 0.55 |
| no_qwen | clean | fixes only (breath 0, Pellav2 all windows) | 435 / 426 | 0.978 [0.97, 0.99] | 0.94 (0) | 0 | 0.85 |
| no_qwen | clean | **new engine** (fixes + learned_tells W 8) | 435 / 426 | 1.000 [1.00, 1.00] | 0.98 (0) | 0 | 0.90 |
| no_qwen | clean | learned_tells score alone | 435 / 426 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 0.94 |
| no_qwen | opus8k | current | 435 / 426 | 0.852 [0.82, 0.88] | 0.60 (0) | 0 | 0.32 |
| no_qwen | opus8k | fixes only (breath 0, Pellav2 all windows) | 435 / 426 | 0.829 [0.80, 0.86] | 0.60 (0) | 0 | 0.49 |
| no_qwen | opus8k | **new engine** (fixes + learned_tells W 8) | 435 / 426 | 0.972 [0.96, 0.98] | 0.77 (0) | 0 | 0.44 |
| no_qwen | opus8k | learned_tells score alone | 435 / 426 | 0.991 [0.99, 1.00] | 0.65 (0) | 0 | 0.50 |
| no_qwen | g711_mulaw8k | current | 435 / 426 | 0.809 [0.78, 0.84] | 0.52 (0) | 0 | 0.18 |
| no_qwen | g711_mulaw8k | fixes only (breath 0, Pellav2 all windows) | 435 / 426 | 0.783 [0.75, 0.81] | 0.49 (0) | 0 | 0.36 |
| no_qwen | g711_mulaw8k | **new engine** (fixes + learned_tells W 8) | 435 / 426 | 0.987 [0.98, 0.99] | 0.91 (0) | 0 | 0.42 |
| no_qwen | g711_mulaw8k | learned_tells score alone | 435 / 426 | 0.997 [0.99, 1.00] | 0.94 (0) | 0 | 0.76 |
| no_qwen | chain_replay_call | current | 435 / 426 | 0.496 [0.46, 0.54] | 0.00 (0) | 0 | 0.00 |
| no_qwen | chain_replay_call | fixes only (breath 0, Pellav2 all windows) | 435 / 426 | 0.461 [0.42, 0.50] | 0.00 (0) | 0 | 0.00 |
| no_qwen | chain_replay_call | **new engine** (fixes + learned_tells W 8) | 435 / 426 | 0.608 [0.57, 0.64] | 0.00 (0) | 0 | 0.00 |
| no_qwen | chain_replay_call | learned_tells score alone | 435 / 426 | 0.651 [0.62, 0.69] | 0.01 (0) | 0 | 0.01 |
| no_gradium | clean | current | 435 / 18 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 0.94 |
| no_gradium | clean | fixes only (breath 0, Pellav2 all windows) | 435 / 18 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_gradium | clean | **new engine** (fixes + learned_tells W 8) | 435 / 18 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_gradium | clean | learned_tells score alone | 435 / 18 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_gradium | opus8k | current | 435 / 18 | 0.999 [1.00, 1.00] | 0.78 (0) | 0 | 0.56 |
| no_gradium | opus8k | fixes only (breath 0, Pellav2 all windows) | 435 / 18 | 0.993 [0.98, 1.00] | 0.89 (0) | 0 | 0.61 |
| no_gradium | opus8k | **new engine** (fixes + learned_tells W 8) | 435 / 18 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 0.72 |
| no_gradium | opus8k | learned_tells score alone | 435 / 18 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 0.94 |
| no_gradium | g711_mulaw8k | current | 435 / 18 | 0.956 [0.91, 0.99] | 0.72 (0) | 0 | 0.28 |
| no_gradium | g711_mulaw8k | fixes only (breath 0, Pellav2 all windows) | 435 / 18 | 0.956 [0.92, 0.99] | 0.61 (0) | 0 | 0.39 |
| no_gradium | g711_mulaw8k | **new engine** (fixes + learned_tells W 8) | 435 / 18 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 0.56 |
| no_gradium | g711_mulaw8k | learned_tells score alone | 435 / 18 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_gradium | chain_replay_call | current | 435 / 18 | 0.697 [0.61, 0.78] | 0.00 (0) | 0 | 0.00 |
| no_gradium | chain_replay_call | fixes only (breath 0, Pellav2 all windows) | 435 / 18 | 0.764 [0.68, 0.84] | 0.00 (0) | 0 | 0.00 |
| no_gradium | chain_replay_call | **new engine** (fixes + learned_tells W 8) | 435 / 18 | 0.661 [0.60, 0.72] | 0.00 (0) | 0 | 0.00 |
| no_gradium | chain_replay_call | learned_tells score alone | 435 / 18 | 0.562 [0.49, 0.63] | 0.00 (0) | 0 | 0.00 |
| no_say | clean | current | 435 / 40 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_say | clean | fixes only (breath 0, Pellav2 all windows) | 435 / 40 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_say | clean | **new engine** (fixes + learned_tells W 8) | 435 / 40 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_say | clean | learned_tells score alone | 435 / 40 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_say | opus8k | current | 435 / 40 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_say | opus8k | fixes only (breath 0, Pellav2 all windows) | 435 / 40 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_say | opus8k | **new engine** (fixes + learned_tells W 8) | 435 / 40 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_say | opus8k | learned_tells score alone | 435 / 40 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_say | g711_mulaw8k | current | 435 / 40 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_say | g711_mulaw8k | fixes only (breath 0, Pellav2 all windows) | 435 / 40 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_say | g711_mulaw8k | **new engine** (fixes + learned_tells W 8) | 435 / 40 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_say | g711_mulaw8k | learned_tells score alone | 435 / 40 | 1.000 [1.00, 1.00] | 1.00 (0) | 0 | 1.00 |
| no_say | chain_replay_call | current | 435 / 40 | 0.575 [0.48, 0.67] | 0.00 (0) | 0 | 0.00 |
| no_say | chain_replay_call | fixes only (breath 0, Pellav2 all windows) | 435 / 40 | 0.616 [0.51, 0.72] | 0.00 (0) | 0 | 0.00 |
| no_say | chain_replay_call | **new engine** (fixes + learned_tells W 8) | 435 / 40 | 0.837 [0.77, 0.90] | 0.00 (0) | 0 | 0.00 |
| no_say | chain_replay_call | learned_tells score alone | 435 / 40 | 0.889 [0.83, 0.93] | 0.12 (0) | 0 | 0.00 |

Human false alarms at p_ai >= 0.60 by speaker domain (each clip scored by a model that never saw its speaker group):

| condition | engine | libri (n) | sanath (n) | friends (n) | max p_ai friends |
|---|---|---|---|---|---|
| clean | current | 0/400 | 0/23 | 0/12 | 0.26 |
| clean | fixes only (breath 0, Pellav2 all windows) | 0/400 | 0/23 | 0/12 | 0.16 |
| clean | **new engine** (fixes + learned_tells W 8) | 0/400 | 0/23 | 0/12 | 0.17 |
| opus8k | current | 0/400 | 0/23 | 0/12 | 0.18 |
| opus8k | fixes only (breath 0, Pellav2 all windows) | 0/400 | 0/23 | 0/12 | 0.19 |
| opus8k | **new engine** (fixes + learned_tells W 8) | 0/400 | 0/23 | 0/12 | 0.27 |
| g711_mulaw8k | current | 0/400 | 0/23 | 0/12 | 0.15 |
| g711_mulaw8k | fixes only (breath 0, Pellav2 all windows) | 0/400 | 0/23 | 0/12 | 0.16 |
| g711_mulaw8k | **new engine** (fixes + learned_tells W 8) | 0/400 | 0/23 | 0/12 | 0.20 |
| chain_replay_call | current | 0/400 | 0/23 | 0/12 | 0.14 |
| chain_replay_call | fixes only (breath 0, Pellav2 all windows) | 0/400 | 0/23 | 0/12 | 0.15 |
| chain_replay_call | **new engine** (fixes + learned_tells W 8) | 0/400 | 0/23 | 0/12 | 0.24 |

## Pause stacker (2026-11-08) - code only, NOT trained, nothing changes until it is

Pause style is a property of the whole call, and a 4 s window rarely holds a sentence-end pause, so pauses are added at the
CALL level: call logit = head_coef * mean(window logit) + sum_i b_i * z(pause_i) + intercept, re-centred on humans like the head.

* Features (`services/api/tell/signals/pauses.py`, numpy, relative speech mask from `shadow._speech_mask`): long pauses
  (>= 300 ms) per minute, median long-pause length, pause CV, pause share of the speech span, median speech-run length.
* Runtime (`signals/learned.py`): an optional `"pauses"` block in `learned_tells.json`. Absent (as shipped) = the plain mean,
  bit-identical; tests in `tests/test_pauses.py` (synthetic gaps, neutral block identical, sign, refusals, training export ==
  runtime decision).
* Training (`training/learned_tells/pauses.py`): `feats` (from the `audio_<cond>.npz` caches), `stack` (held-out head vs
  head+pauses per scenario x channel, stacker fitted only on other groups' out-of-fold head logits in the training channels;
  prints the mean coefficient per scenario so a generator-specific sign shows up), `export` (adds the block, prints the SHA;
  then update `learned.SHA256` and bump `THRESHOLDS_VERSION`). Ship bar unchanged.

Local sanity check only (10 local human-memo vs Qwen-clone pairs, 7 measurable, one speaker family, NOT an eval):

| channel | long pauses/min, human vs Qwen (median) | human > Qwen | median long-pause ms | human > Qwen |
|---|---|---|---|---|
| clean | 19.3 vs 10.6 | 5/7 | 523 vs 625 | 3/7 |
| opus8k | 19.5 vs 10.6 | 6/7 | 495 vs 625 | 2/7 |
| chain_replay_call | 14.6 vs 10.6 | 6/7 | 580 vs 520 | 5/7 |

Long pauses per minute keeps its direction through codec and replay; pause length does not. Whether it holds for Gradium,
`say`, ElevenLabs and real calls is exactly what `stack` answers on the full cache.
