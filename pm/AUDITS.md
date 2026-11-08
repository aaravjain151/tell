# AUDITS

## Wild eval — generalization across generator families (T-012)
_Paste the output of `make eval ARGS="--wild data/calls --verbose"` here once real clips exist. No numbers yet:_
_the only runs so far used `tests/synth.py` fixtures, which test mechanics and say nothing about real voices._

| Condition | AI n | Human n | AUC | EER | FPR@90%TPR | Engines held out (TPR / FPR) |
|---|---|---|---|---|---|---|
| clean | | | | | | gradium · elevenlabs* · voicestudio · qwen3tts |
| opus-8k | | | | | | gradium · elevenlabs* · voicestudio · qwen3tts |

\* ElevenLabs is in the training set of the HF anti-spoof checkpoint, so it is in-domain; judge generalization on the others.
Target: FPR@90%TPR <= 0.15 on opus-8k with every engine held out at least once. thresholds_version: _fill in_.

## Fusion re-weight: Pellav2 up, HF down, acoustic share up (2026-11-07, thresholds 2026-11-07.1 -> .2)
Data: data/calls (gitignored, read-only): AI = gradium 10, gradium_stock 8, qwen3tts 10 (n=28); human = ONE speaker (Sanath), n=10; each clip clean and opus-8k. **n is tiny and the humans are one voice on one mic.** Real pipeline, `run_eval.py --wild`, HF garystafford + Pellav2 on MPS. Shipping P_AI_THRESHOLD stays 0.60.
Change (weights only, scorer.py untouched): W_PELLA 1.6 -> 4.0, W_HF 1.4 -> 0.7, ACOUSTIC_SHARE 0.6 -> 0.8.

Before (2026-11-07.1) vs after (2026-11-07.2), real pipeline, at the shipping threshold:

| Condition | Slice | AUC before -> after | FPR@90%TPR before -> after | Caught @0.60 before -> after | Humans flagged |
|---|---|---|---|---|---|
| clean | all AI (28) | 0.85 -> 0.92 | 0.20 -> 0.10 | 7/28 -> 14/28 | 1/10 -> 1/10 (see note) |
| clean | gradium (10) | 0.90 -> 0.95 | 0.20 -> 0.10 | 2/10 -> 5/10 | |
| clean | gradium_stock (8) | 0.93 -> 0.99 | 0.20 -> 0.10 | 3/8 -> 7/8 | |
| clean | qwen3tts (10) | 0.76 -> 0.84 | 0.30 -> 0.20 | 2/10 -> 2/10 | |
| opus-8k | all AI (28) | 0.82 -> 0.88 | 0.40 -> 0.40 | 5/28 -> 9/28 | 1/10 -> 1/10 (see note) |
| opus-8k | gradium (10) | 0.85 -> 0.91 | 0.20 -> 0.10 | 2/10 -> 2/10 | |
| opus-8k | gradium_stock (8) | 0.91 -> 0.97 | 0.20 -> 0.10 | 2/8 -> 6/8 | |
| opus-8k | qwen3tts (10) | 0.71 -> 0.78 | 0.40 -> 0.40 | 1/10 -> 1/10 | |

Note: the one "human flagged" is `human/sanath/sales_disclosed`, p_ai exactly 0.600: the human read a script that says "I'm an AI", and scorer.py floors p_ai at the threshold when disclosure is detected (tier ai_disclosed). That is the disclosure rule, not the voice, and is identical before and after. It also inflates "caught" by the AI clips reading disclosure scripts. Raw-formula replay (`eval/replay_weights.py`, no floor): caught 5/28 clean, 3/28 opus before -> 13/28, 7/28 after; highest human raw p_ai 0.25 clean / 0.26 opus (margin to 0.60: 0.35), lowest AI 0.14. AUC raw 0.92/0.88 -> 0.97/0.94.

Leave-one-engine-out (replay; setting picked on the other engines = most clips caught at 0.60 with 0 humans flagged): held gradium picks (6,1.4,.8) -> 7/10 clean, 4/10 opus; held gradium_stock picks (8,0,.85) -> 8/8, 6/8; held qwen3tts picks (10,.7,.85) -> 1/10, 0/10. Reading: weights learned from the Gradium-family clips do not transfer to Qwen3-TTS (Pellav2 alone scores qwen 0.66 at best, many clips ~0); the fusion cannot fix a voter that is blind on an engine. Qwen3-TTS stays the weak spot at 2/10 and 1/10.
Pellav2 single-point-of-failure stress (replay): if Pellav2 wrongly said 1.0 on a human, that human's p_ai would be ~0.62 at the chosen weights (flagged by 0.02), 0.69 at W_PELLA 6, 0.57 at the old 1.6. That is the price of catching more: the chosen W_PELLA 4 is the largest tested weight where a false positive from Pellav2 alone is nearly (not fully) absorbed by the behavioural tells. Pella is 44% of acoustic weight, HF stays on.
Why 0.80 and not 0.9: the paired design reads the same text for human and AI, so script tells are identical across classes and a high share only drops a constant. Real undisclosed-agent calls differ in wording, so the script family keeps 20%.
Not done: P_AI_THRESHOLD stays 0.60. At these weights 0.45 would catch 20/28 clean and 15/28 opus with 0 humans flagged (0.20 margin over the highest human), but one speaker cannot justify it; needs a second speaker and a phone line first.
Golden eval unchanged: transcript 0.98 (32), synthetic audio 1.00 (48).

## Shadow layers (not used by the scorer) (2026-11-07)
**One human speaker (Sanath) and tiny n. Everything here is a sanity check. Any separation may be speaker identity (his mic and room), and nothing supports a claim of generalisation.** Scorer, thresholds, stabiliser and signature are untouched; the features are computed in `signals/shadow.py`, stored only in `egress.context.shadow` after fusion, and a test proves tier/p/confidence/signature are bit-identical with the module on or patched out. Golden eval before and after: transcript 0.98 (32), synthetic audio 1.00 (48), identical.

Data: a copy of data/calls (AI 37: gradium 11, gradium_stock 8, qwen3tts 10, elevenlabs 4, voicestudio 4; human 11, all Sanath). The 8 elevenlabs/voicestudio clips are 5 s and score a flat p_ai 0.49 in every condition (cause not investigated; it looks like no usable voter output), so they only add a constant. Conditions made by `tools/redteam/degrade.py` identically for every class; `amr_nb` was NOT run (this ffmpeg has no libopencore_amrnb encoder; skipped, not faked). Loss in `opus_lowbitrate_with_loss` is our own burst-loss + repeat-and-decay concealment (measured 8% on one clip), the RIR is synthetic.

**Per-condition p_ai (real pipeline, `run_eval.py --wild`, shipping threshold 0.60). n is AI / human in every row.**

| Condition | AI n / human n | AUC | EER | FPR@90%TPR | Caught @0.60 | Qwen3-TTS AUC (n=10) | LOEO TPR range (FPR) |
|---|---|---|---|---|---|---|---|
| clean | 37 / 11 | 0.79 | 0.26 | 0.36 | 3/37 | 0.77 | 0.62-1.00 (0.36) |
| opus-8k | 37 / 11 | 0.78 | 0.27 | 0.36 | 3/37 | 0.76 | 0.70-1.00 (0.36) |
| g711_mulaw8k | 37 / 11 | 0.78 | 0.27 | 0.36 | 3/37 | 0.77 | 0.62-1.00 (0.36) |
| g711_alaw8k | 37 / 11 | 0.78 | 0.27 | 0.36 | 3/37 | 0.77 | 0.70-1.00 (0.36) |
| opus_lowbitrate_with_loss | 37 / 11 | 0.79 | 0.27 | 0.36 | 3/37 | 0.77 | 0.80-1.00 (0.36) |
| speaker_rerecord_sim | 37 / 11 | 0.72 | 0.27 | 0.64 | 3/37 | 0.60 | 0.60-1.00 (0.36-0.64) |
| chain_pstn_voip | 37 / 11 | 0.80 | 0.19 | 0.36 | 3/37 | 0.80 | 0.80-1.00 (0.36) |
| chain_replay_call | 37 / 11 | 0.72 | 0.27 | 0.55 | 3/37 | 0.60 | 0.60-1.00 (0.36-0.73) |
| amr_nb | not run | | | | | | |

Reading: the codec conditions barely move p_ai on these clips (AUC 0.78-0.80), so opus-8k is not a harder test than G.711 here; the replay-style conditions (synthetic RIR + 4 kHz band-limit) are the ones that hurt (AUC 0.72, Qwen3-TTS 0.60 = chance-ish, FPR@90%TPR up to 0.64). That is consistent with the replay failure on the real Continuity call, but a synthetic RIR is not that call. Only 3/37 AI clips pass 0.60 in every condition (the disclosure-script floor accounts for some of those; see the re-weight note above). Full per-engine rows: `run_eval.py --wild DIR`.

**Shadow features, clean and opus-8k** (`tools/shadow_report.py DIR --conditions clean,opus8k`; AUC = P(AI value > human value), 95% CI = bootstrap over clips, 2000 draws). AI n=37, human n=11 in all rows unless shown (loudness needs >= 3 utterances).

| Feature | clean AI / human mean | clean AUC [95% CI] | opus-8k AI / human mean | opus-8k AUC [95% CI] |
|---|---|---|---|---|
| noise_floor_dbfs | -60.6 / -48.3 | 0.30 [0.13, 0.48] | -62.3 / -50.2 | 0.30 [0.13, 0.48] |
| noise_floor_std_db | 10.8 / 14.6 | 0.30 [0.14, 0.50] | 10.2 / 11.1 | 0.54 [0.37, 0.71] |
| digital_zero_run_ms | 0.4 / 153 | 0.08 [0.00, 0.25] | 0.8 / 4.5 | 0.10 [0.00, 0.29] |
| gate_transitions_per_min | 0 / 0.88 | 0.36 [0.23, 0.50] | 0 / 0 | 0.50 [0.50, 0.50] |
| modulation_4_16_ratio | 0.242 / 0.245 | 0.58 [0.43, 0.73] | 0.246 / 0.246 | 0.59 [0.43, 0.74] |
| spectral_flatness_300_3400 | 0.102 / 0.097 | 0.60 [0.42, 0.78] | 0.092 / 0.083 | 0.59 [0.41, 0.77] |
| loudness_std_db (n 27-28 / 10) | 1.29 / 1.62 | 0.43 [0.22, 0.63] | 1.43 / 1.47 | 0.48 [0.26, 0.71] |
| bandwidth_hz | 7219 / 6619 | 0.66 [0.47, 0.83] | 4608 / 4719 | 0.45 [0.29, 0.62] |
| snr_db | 40.3 / 24.0 | 0.72 [0.57, 0.87] | 41.9 / 25.7 | 0.72 [0.57, 0.87] |

Reading, with the caveats up front: (1) intervals that exclude 0.5 are noise_floor_dbfs (AI floor lower, both conditions), snr_db (AI higher), digital_zero_run_ms and, in clean, noise_floor_std_db. All four are properties of the recording room and recorder, and the human clips come from one person on one mic: the 153 ms digital-zero runs in his clean files are a recorder artefact that opus-8k removes (4.5 ms), and the noise-floor and SNR gaps are what a TTS file with no room looks like against a real room. Research B's anecdote (floor -77/-70 vs -51 dBFS) is the same effect. These would read "human" for an AI voice played through a speaker into a phone (acoustic relay, see the speaker_rerecord_sim row), so they must never be a human-confirming signal. (2) The modulation-spectrum ratio, flatness, loudness consistency and bandwidth do not separate (intervals span 0.5); the earlier 0.28-vs-0.54 syllable-rate anecdote does not reproduce with this definition. (3) bandwidth_hz is a channel descriptor: it drops from ~7.2 kHz to ~4.6 kHz in opus-8k for both classes, as it should. (4) Persistence features (per-voter mean/min/fraction > 0.5/longest 0.2-0.6 run) are n/a on single clips (the neural voters score at most 3 windows per analysis); they are computed per call in the live stream (`call_persist_*` in the tick's `egress.context.shadow`) and have NO measurements yet. Windows overlap across ticks, so treat them as a descriptive proxy.

Next step before anything graduates from shadow: at least 3-5 more human speakers on different mics, and real Continuity/phone captures including AI audio injected digitally versus played acoustically.

## Neural head on frozen SSL layers: held-out generator and speaker eval (2026-11-07) - NOT wired
Full write-up and tables: docs/HEAD-FINETUNE.md. Data: LibriSpeech dev/test-clean (80 speakers, CC BY 4.0) + Sanath real = 410 clips; fakes = 419 local Qwen3-TTS clones (80 LibriSpeech voices, 2 synthetic demo voices, repo Sanath clones) + 18 Gradium + 40 macOS `say`; no ElevenLabs clip exists (paid API not used). Head = learned layer weights + 2-layer MLP on mean/std pooled frozen w2v-BERT 2.0 states, 262,426 params, trained with tools/redteam/degrade.py channels on both classes; leave-one-generator-out x leave-speakers-out (5 folds), same windows scored by the shipped Pellav2 and HF voters.
Result: on the replay chain (speaker_rerecord_sim then opus8k) the head beats Pellav2 for all three held-out generators (AUC 0.65 vs 0.58 Qwen, 0.82 vs 0.42 Gradium, 0.92 vs 0.73 say; n = 440 real / 442, 72, 94 fake windows); on clean it ties; on held-out Qwen opus8k/g711 it is slightly worse (TPR at 5% FPR 0.85 vs 0.91, 0.88 vs 0.95) and false alarms at the 0.5 cut on held-out real speakers are 0.02 to 0.04 in several cells vs 0.00. Bar was "beats without raising false alarms", so no `neural_head` voter, W_* and thresholds untouched. Owner files (n=2): Pellav2 0.67/0.02 clean, 0.67/0.00 opus8k -> head 0.59/0.62 clean, 0.93/0.57 opus8k with no Qwen in training (0.78/0.69, 0.98/0.96 with other Qwen clones seen). HF-backbone head beats the shipped HF voter everywhere but not Pellav2.
Caveats: real class is read audiobook speech plus ONE conversational speaker; synthetic channels only; one Qwen family; no ElevenLabs; Gradium/say have few sources. Golden eval untouched (scorer.py/thresholds.py not edited).

## 2026-11-07 Qwen3-TTS cue study (branch feat/qwen-cues)

Question (owner, human listener): two Qwen3-TTS clones of Sanath's voice (`rough_morning` p_ai 0.39, `long_tech_scam` 0.25) were not caught; a person hears them as non-human instantly. Method: paired real-vs-Qwen features on 8 scripts (same speaker, same words), clean + opus8k + g711 + chain_replay_call, bootstrap CIs over scripts, ~70 features. Full write-up in `docs/QWEN-CUES.md`; tables in `docs/qwen-cues-paired-table.md`.

Findings that survive phone-band (paired, n=8 scripts): voice too clean (CPPS +2.9 dB, dz +2.6-3.0 in every condition; jitter lower, 7/8), sentence-end pauses half as long (649 vs 324 ms; articulation rate equal), pitch moves less and slower (F0 rate 30.9 vs 25.2 st/s, F0 std 3.1 vs 2.4 st), stronger 4-16 Hz syllable rhythm (existing shadow layer, clip AUC 0.92 on these pairs vs 0.58 over all AI engines, so it is Qwen-specific). Not supported: "timbre drifts less" (MFCC and wav2vec2 drift equal within noise), "pauses at regular spacing", mid-phrase pause placement. Mostly recorder, not voice: pause floor depth (-20 vs -40 dB) and onset sharpness (collapses under the noise-matched control, 21 -> 10.6 vs 9.0 real). Above 8 kHz the 24 kHz Qwen files are empty (about -47 dB re 1-4 kHz vs about -23 dB in the 48 kHz real originals) but that is lost at 16 kHz / on any call.

Shadow layers added (never scored): qwen_cpp_db, qwen_f0_rate_st_s, qwen_long_pause_per_min, qwen_onset_sharpness_db, qwen_lowmid_balance_db. Leave-one-script-out clip AUC (clean/opus8k/g711/replay): cpp 1.00/1.00/1.00/0.92, long-pause 0.97/0.98/0.98/0.96, f0-rate 0.81/0.69/0.81/0.89, onset 0.92/0.88/0.90/0.80 (0.67 noise-matched), lowmid 0.88 throughout (likely mic). Scorer, thresholds untouched; golden eval identical (transcript 0.98 / synthetic 1.00 before and after); tests 549 passed.

Caveat that governs all of it: ONE speaker, ONE engine, 8 scripts; real and Qwen differ in recording chain as well as synthesis. Not promotable. Next step: more speakers/mics, a second TTS engine, Qwen in real phone captures, and a short listening test to confirm which cues people actually use; then decide whether a "too clean voice" tell belongs in `acoustic.py`.

## Phone-memo humans: false-alarm test and neural-head retrain (2026-11-07) - head still NOT wired
Full write-up: docs/HEAD-FINETUNE.md "Real phone-recorded humans"; tables `docs/head-finetune/tables_humans.md`. Scorer, thresholds, `W_*` untouched.
Data: 12 iPhone Voice Memos (171 s) of the owner's friends, quiet rooms, **voice memos, not calls**; consent relayed by the owner (`consent.txt`, not signed per speaker); audio stays in gitignored `data/finetune/humans_new/`. All 12 are speech (local whisper): 4 "train cancelled" reads, 4 free "my morning", 4 human reads of the scam script.
**Speaker count is ESTIMATED: 4** (wav2vec2 L5 / w2v-BERT L4 mean-pooled embeddings, cosine + agglomerative, silhouette k = 4 / 5; each guessed speaker has one clip of each script). By that guess two speakers recorded at both locations, so the location grouping can leak; a single-group split (all 12 held out together) is reported as the conservative case.

Current shipping pipeline on the 12 clips (`run_eval.py --wild`, Pellav2 + HF, thresholds 2026-11-07.3), n = 12 per row:

| condition | fused p_ai >= 0.60 | max p_ai | Pellav2 >= 0.5 | HF >= 0.5 |
|---|---|---|---|---|
| clean / opus8k / g711_mulaw8k / chain_replay_call | 0/12 each | 0.29 / 0.23 / 0.20 / 0.20 | 0/12 each (max 0.00) | 0/12 each |
| g711_alaw8k / speaker_rerecord_sim | 0/12 each | 0.21 / 0.23 | 0/12 each | 0/12 each |
| opus_lowbitrate_with_loss | 0/12 | **0.54** | **7/12** | 0/12 |
| chain_pstn_voip | 0/12 | **0.56** (1 unsure) | **7/12** | 0/12 |

No human crossed 0.60 (95% upper bound 26% on 12). But Pellav2 calls 7/12 real humans synthetic after 6 kbps Opus with burst loss (our own concealment) and fused p_ai gets within 0.04 of the threshold; Pellav2's FPR@0.5 there is 0.55 on the 485 old+new real windows too. That is the nearest human false alarm in the shipped detector. Scam-script reads correctly land in tier "scam" (2-4 per condition).
Existing head (`head_pella_mlp.pt`, never saw these speakers), 45 windows: share >= 0.5 = 0.02 clean, 0.18 opus8k, 0.13 g711, 0.02 replay, 0.16 alaw, 0.07 pstn (Pellav2: 0.00 except pstn 0.51); every clip mean stays < 0.5.

Retrain with the new humans as reals (same leave-one-generator-out x leave-speaker-group-out protocol, each new group its own fold), held-out generator, chain_replay_call, AUC / TPR@0.5 / FPR@0.5 (485 reals):

| held out | Pellav2 now | head before | head after (cluster grouping) |
|---|---|---|---|
| Qwen (442 fake) | 0.58 / 0.01 / 0.01 | 0.65 / 0.06 / 0.01 | 0.63 / 0.05 / 0.00 |
| Gradium (72) | 0.41 / 0.00 / 0.01 | 0.82 / 0.25 / 0.03 | 0.77 / 0.08 / 0.02 |
| `say` (94) | 0.73 / 0.03 / 0.01 | 0.92 / 0.54 / 0.02 | 0.89 / 0.46 / 0.01 |

New-human windows >= 0.5 for the retrained head: 0.00-0.02 with location or cluster groups; **up to 0.09 (g711, alaw) in the single-group split**, where no phone-memo speaker was in training. Owner Qwen files (Sanath-held-out fold, never trained on): Qwen-seen head clean 0.81 / 0.73, opus8k 0.98 / 0.97, replay 0.08 / 0.21 (before 0.78 / 0.69, 0.97 / 0.96, 0.17 / 0.31); Pellav2 now 0.67 / 0.02, 0.67 / 0.00, 0.00 / 0.00.
Learned fusion (PR #82): not on main, not refitted.
Bar (replay catch better AND held-out false alarms no higher than the fusion): catch met; false alarms not shown (single-group 2-9% of codec windows, held-out LibriSpeech FPR@0.5 0.01-0.03 vs Pellav2 0.00; 12 clips cannot bound it). **Not wired.**
Caveats: speaker count is estimated; voice memos in quiet rooms, not phone calls; channels simulated; 45 windows from 12 clips are not independent; the loss concealment is ours, not libopus PLC.
Next: more speakers on more devices and real calls; investigate the Pellav2 low-bitrate-loss false alarms before any threshold work.

## Learned tells: logistic regression over every voice clip, held out (2026-11-08, thresholds 2026-11-07.3 -> 2026-11-08.1) - SHIPPED, on by default
Full write-up: docs/LEARNED-TELLS.md. Code: training/learned_tells/, services/api/tell/signals/{learned,tell_features}.py.
Data: 435 human clips (400 LibriSpeech / 80 speakers, 23 Sanath, 12 phone memos / 4 est. speakers) vs 484 AI (426 Qwen3-TTS 0.6B
incl. 18 Sanath clones, 18 Gradium, 40 macOS say); pure tests: 2 owner files, 9 ElevenLabs lines, 4 Qwen 1.7B takes, 4 QA calls.
3,488 windows (4 s, 2 s hop) per condition; degrade.py identical for both classes.
Protocol: every clip scored by a model that never saw its speaker group; leave-one-generator-out; 12 memos also held out together;
Sanath vs his clones split by script. Scaler/PCA/C fitted on training folds only.
Finding 1: our hand-written tells are weak on unseen generators (interpretable L2: AUC 0.83 seen, 0.70 held-out Qwen); the strongest,
phone-robust ones are cepstral peak prominence (too regular), pause-level wobble (rendered silence), slow spectral change, clean gaps
between harmonics. Several directions are generator-specific (pitch speed: up for Gradium/ElevenLabs, down for Qwen/say).
Finding 2: a linear read-out of Pellav2's frozen w2v-BERT layer 12 (PCA-32 + L2 logistic regression) generalises: held-out Qwen AUC
1.00 / 0.99 / 1.00 (clean/opus8k/g711). Calibrated to the human side (logit 0 = 99th pct of held-in humans), it is the voter.
Engine, voice only, catch at p_ai >= 0.60 with 0 human false alarms before and after (n = 435 humans):

| held out | clean | opus8k | g711 | replay |
|---|---|---|---|---|
| nothing (484 AI) | 0.61 -> 0.94 | 0.38 -> 0.57 | 0.25 -> 0.51 | 0.00 -> 0.00 |
| Qwen (426) | 0.55 -> 0.90 | 0.32 -> 0.44 | 0.18 -> 0.42 | 0.00 -> 0.00 |
| Gradium (18) | 0.94 -> 1.00 | 0.56 -> 0.72 | 0.28 -> 0.56 | 0.00 -> 0.00 |
| say (40) | 1.00 -> 1.00 | 1.00 -> 1.00 | 1.00 -> 1.00 | 0.00 -> 0.00 |

Lossy paths (our 6 kbps + burst-loss concealment), human false alarms at 0.60: 156 -> 73 (pstn chain), 161 -> 68 (opus loss).
Owner files (real pipeline): rough_morning clean 0.40 human -> 0.67 AI; long_tech_scam 0.15 -> 0.57 (unsure); both still human under
codecs and replay. ElevenLabs (never trained; concatenation of all 9 lines) 0.69 -> 0.80 AI in clean/opus8k/g711, human in replay;
single lines are < 3 s and not scored. QA calls 0.64-0.67 -> 0.76-0.79 (all AI) except replay.
Engine fixes: Pellav2 all windows (cap 3 -> 16) + mean logit (P clipped 0.01); breath_proxy 1.2 -> 0 (scored ~0.1-0.27 on everything);
band_limited = 5-7.5 kHz vs 1-4 kHz < -37 dB (old rule flagged 71% of clean clips; new: 0/949 clean, 949/949 opus8k/g711/replay).
The fixes alone raise lossy false alarms (156 -> 221); they only ship with the voter. Golden eval identical (PASS).
Not improved: replay chain (catch 0 everywhere at 0.60). Caveats: read speech + one conversational speaker + 12 memos; simulated
channels; weight 8 and the Pellav2 clip were chosen on the same folds; tiny ElevenLabs/owner test sets.
