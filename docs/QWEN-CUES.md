# Why a human hears Qwen3-TTS as "not human" when the engine does not

Status 2026-11-07. Study tools: `tools/qwen_cues_prep.py`, `tools/qwen_cues.py`, `tools/qwen_cues_stats.py`, `tools/qwen_cues_eval.py` (deps in `tools/qwen_cues_requirements.txt`, study-only, not imported by `services/api`). Tables: `docs/qwen-cues-paired-table.md` (every feature x condition), `docs/qwen-cues-shadow-eval.txt` (shadow layer results).

## Loud caveats

- ONE speaker (Sanath) and ONE TTS engine (Qwen3-TTS clone of that voice). n = 8 scripts that exist as both a real recording and a Qwen render (casual_clone, long_appointment, long_checkin, sales_disclosed, sales_undisclosed, scam_bank_otp, scam_grandparent, scam_irs). Every CI is a bootstrap over those 8 scripts. "Survives" means the interval excludes 0 in that condition; it does not mean it generalises.
- The real and Qwen clips differ in recording chain, not just in synthesis: the real ones went through a phone or laptop mic, a room and an m4a encode; Qwen is a clean render. Any cue that is partly noise floor or mic EQ is marked. A "floor_matched" control (real clip's own pause noise added to the Qwen clip at the same speech-to-noise ratio) is reported for the shadow layers.
- The two owner files (`rough_morning`, `long_tech_scam`) have no real counterpart in the repo (`rough_morning` has no script file at all; ASR words were used). They are compared against the 10 real clips as a distribution, not paired.
- Nothing here changes a verdict. The five new layers are SHADOW (`egress.context.shadow.qwen_*`), the scorer and thresholds are untouched, golden eval is identical.
- Channel conditions come from `tools/redteam/degrade.py`: opus8k, g711_mulaw8k, chain_replay_call (synthetic RIR + 4 kHz band-limit + room noise, then Opus). Word-time-based cues (pause length at punctuation, sentence pace) use the CLEAN audio's ASR timings for every condition, so their "survival" is trivially true and says nothing about phone-band; they are marked clean-only.

## What the data supports (a human listener is hearing these)

Paired = Qwen minus real, same words, same voice. dz is paired effect size; * means the 95% CI excludes 0. Condition columns are clean / g711 / opus8k / chain_replay (dz). Full numbers in the table file.

1. Pauses at sentence ends are about half as long. Mean gap after a full stop 649 ms real vs 324 ms Qwen (diff -325 ms, CI -443 to -212, 8/8 scripts); after commas 378 vs 242 ms (6/7). Articulation rate is the same (4.37 vs 4.48 words/s of actual speech, CI includes 0), so Qwen is not "fast"; it just does not stop and breathe the way the person does (overall pace 3.09 vs 3.97 words/s, dz +2.5, 8/8, all conditions). Silence-based: long pauses (>= 300 ms) per 100 words 12.7 vs 4.7 (dz -2.1/-2.4/-2.1/-1.5, 8/8 everywhere). Clean-only for the ASR gaps; the silence-based version survives all conditions but is partly the noise floor. Supported.
2. The voice is too clean and too regular. Cepstral peak prominence (Praat CPPS) 7.6 vs 10.6 dB (dz +2.9/+3.0/+3.0/+2.6, 8/8 every condition; clean paired diff +2.9 dB, CI +2.2 to +3.5). Harmonics-to-noise 10.1 vs 12.7 dB (dz +1.5, 8/8 in clean/g711/opus8k, but not in chain_replay: +0.5, CI includes 0). Jitter 2.65% vs 2.06% (dz -1.3, 7/8, all four conditions). Real speech has a rough, breathy, slightly irregular edge; this is the strongest and most phone-robust finding. Partly recorder noise, but it survives the floor-matched control (our CPP: real 10.1 vs Qwen 13.8 dB with the real recording's own noise added, AUC 1.00). Supported.
3. The pitch moves less and more slowly. Rate of F0 change 30.9 vs 25.2 semitones/s (dz -1.4/-1.3/-1.4/-1.4, 7/8, all four); F0 standard deviation 3.08 vs 2.36 st (dz -0.9 to -1.0, 6-7/8, all four); per-phrase declination slope varies less (std 3.7 vs 1.6, 7/8). A person's intonation is livelier from phrase to phrase. Supported (phone-robust).
4. Pitch is tied to loudness. Correlation of F0 with level: 0.08 real vs 0.27 Qwen (dz +0.95, 6/8; weakens to +0.7 in chain_replay). Louder-is-higher is a rule a model follows more tightly than a speaker does. Weak support (n=8, 6/8 scripts).
5. Words start abruptly. Largest 10 ms level rise at word onsets 9.0 vs 19.7 dB (dz +2.1, 8/8; +1.2 in chain_replay). Caution: the floor-matched control cuts our onset layer from 21 to 10.6 dB vs 9.0 real, so most of this is the real recording's room noise, not the synthesis. Weak / mostly channel.
6. Stronger syllable rhythm. Share of envelope modulation at 4-16 Hz 0.23 vs 0.34 (dz +1.5, 8/8, all four). The existing `modulation_4_16_ratio` shadow layer sees this in the pairs (clip AUC 0.92) while across all AI engines vs the human set it was only 0.58 (see pm/AUDITS.md), so this cue is Qwen-specific rather than "AI vs human". Supported for Qwen.
7. Tempo is more constant across phrases. Phrase-to-phrase rate CV 0.20 vs 0.13 (dz -1.0, 7/8; clean/g711/opus8k; not significant in chain_replay: -0.4). Supported in clean and codec; weak under replay.
8. Low-mid balance of the voice. Energy at 500-1000 Hz relative to 100-500 Hz is 5 dB higher in Qwen (dz +1.7 to +2.1, 7-8/8, all conditions). This is spectral shape of voice plus mic, probably mostly the recorder (the real files come from a different mic path). Cannot separate. Hypothesis only.
9. Pause floor. Pauses in the real recordings sit about 20 dB under speech; Qwen's sit about 40 dB under (dz -2.1, 7/8; narrower under replay). That is the room/mic noise floor, i.e. a recorder property, not a speech cue (see DETECTION-LAYERS "claims we must not make"). Supported as a difference, not as evidence about the voice.

## What the data does NOT support

- "The same timbre drifts less than a person's": no. Cosine-like distance between mean-pooled 1 s windows: MFCC adjacent-window distance 0.238 real vs 0.271 Qwen (+0.5 dz, CI includes 0 in clean); wav2vec2 (the HF anti-spoof backbone) adjacent distance 0.464 vs 0.435 (dz -0.5, CI includes 0). Qwen drifts as much as the person, within noise.
- "Pauses land at exactly regular spacing": not supported. Spacing CV of pause starts 0.60 vs 0.54 (CI includes 0). The pause DURATION CV is lower in Qwen (0.59 -> 0.33, dz -1.0, 7/8), so durations are more uniform, positions are not.
- "No breath before long phrases": not testable here. My simple breath detector fired on every pause in both classes (useless, discarded). Real pauses are 20 dB louder (item 9), which is consistent with audible breath/room, but we did not isolate inhalations.
- Pauses at the wrong place (mid-phrase): no. Mid-word gaps of >= 120 ms are rare and equal: 0.50 vs 0.33 per 100 words (CI includes 0, 1/8 scripts same sign). Qwen puts its pauses at the right places and makes them too short. Number of gaps >= 120 ms per 100 words is 13.1 vs 12.8.
- Phrase-final fall/rise, creak/fry: inconclusive. Phrase-final unvoiced share is lower in Qwen under codecs (dz -1.2 to -1.3) but only -0.7 in clean (CI includes 0). Final F0 movement variability is lower in Qwen but not significant in 3 of 4 conditions. No claim.
- Formant dynamics: F2 movement per 10 ms and jerk are lower in Qwen but the CIs include 0 in every condition (dz -0.1 to -0.5). F2 spread (std) is higher in Qwen (+1.2 clean) and is not robust under g711. No claim.
- Repetition across sentences: contour sameness is higher in Qwen in clean (0.13 -> 0.25) but n=5 valid pairs and the CI includes 0. Per-sentence pace CV 0.21 vs 0.18, CI includes 0. Hypothesis, not supported.
- Disfluency and fillers: the transcripts are the scripts, so the text carries no disfluency information; Whisper drops fillers. Extra ASR words per script word 1.9% real vs 0.3% Qwen, CI includes 0. Nothing to say.
- Spectral content above 8 kHz: the 24 kHz Qwen files have almost nothing above 8 kHz (4-8 kHz band is -14 to -23 dB re 1-4 kHz; 8-10 kHz is about -47 dB), while the real 48 kHz phone-mic originals carry 8-11.5 kHz at about -19 to -27 dB (5 of 6 comparable originals; casual_clone's original is band-limited at 8 kHz). So Qwen's 24 kHz output has no real top octave; likely an internal 16 kHz or codec ceiling. Real, but gone after the 16 kHz resample the pipeline does and after any phone channel, so useless on calls. 4-8 kHz and 6-8 kHz band levels did not give a consistent paired difference under degradation.

## What a human is hearing, in plain words

- It never really stops to take a breath: sentence-end pauses are half as long and the gaps between sentences are quieter and cleaner. (supported)
- The voice is too perfect: no roughness, no breathiness, no micro-wobble. (supported, strongest, survives phone codecs)
- The melody is flatter: the pitch moves less and more slowly from word to word, and rises and falls with loudness the same way each time. (supported; the loudness-coupling part is weak)
- The rhythm is too even: the same syllable beat and similar tempo phrase after phrase. (supported for syllable rhythm and phrase tempo)
- Words start crisply; real mouths do not. (mostly channel; weak)
- Hypotheses we could not test: no audible inhalations before long phrases; the emotional contour of the sentence not following meaning; over-articulation. These need a listening test or a breath-annotated corpus.

## The two owner files (clean, vs the 10 real clips; paired reference not available)

Values outside the range of the 10 real clips are marked. Real clips span: CPPS 6.2-8.5, HNR 7.3-11.9, f0-energy corr -0.25-0.36, overall pace 1.98-3.43 words/s, period gap 545-900 ms.

`data_calls_qwen3tts_rough_morning.wav` (24 kHz, 20.5 s, engine p_ai 0.39, Pellav2 0.67, HF 0.02): CPPS 10.3 and HNR 14.8 (both above every real clip), F0-energy correlation 0.54 (above), overall pace 3.77 words/s (above), pauses short (mean 249 ms, below the real range; word-gap after full stop about 120 ms, comma gaps 0, both far below 545-900 and 93-690 ms), long pauses 2.7 per 100 words (below 9.5-35), shimmer 0.073 (below). Within the real range: onset sharpness 9.3 dB, modulation ratio 0.28, F0 spread and rate, pause depth -21 dB. So this one is human-like in attack and rhythm but over-clean in the voice, over-regular in pitch-versus-loudness, and rushes through its pauses. Wasn't paired, so those are comparisons to 10 real clips of the same speaker only.

`data_calls_qwen3tts_long_tech_scam.wav` (22.4 s, p_ai 0.25, Pellav2 0.01, HF 0.01): CPPS 11.3 and HNR 13.6 (above), onset sharpness 19.7 dB (above range max 16), modulation ratio 0.37 (above), F0-energy correlation 0.52 (above), contour sameness 0.63 (above the real max 0.39: each phrase has nearly the same pitch shape), overall pace 4.0 words/s (above), long pauses 4.5 per 100 words (below), no comma pauses at all. So the human is hearing a too-clean voice reading every phrase with the same tune at a steady, fast pace without proper pauses. These are comparisons against the real distribution of one speaker; a few of them (onset, contour sameness) are the weak ones in the paired data.

Why the detector misses it: Pellav2 and HF were trained on vocoder/codec artefacts and are near blind to Qwen3-TTS here; the behavioural tells in `acoustic.py` look at pause regularity and pitch stability but not at roughness, pitch-loudness coupling, or sentence-end pause length, which are the cues above. Hypothesis: the human listener is mostly using items 1-3.

## Shadow layers added (`signals/shadow.py`, logged as `qwen_*`, never scored)

`qwen_cpp_db` (cepstral peak prominence; numpy port, r = 0.98 with Praat CPPS over all 36 clips), `qwen_f0_rate_st_s` (numpy autocorrelation F0, r = 0.95 with Praat's rate), `qwen_long_pause_per_min`, `qwen_onset_sharpness_db`, `qwen_lowmid_balance_db`. Unit tests on synthetic signals in `services/api/tests/test_shadow.py`; the existing bit-identical-verdict test covers all of them.

Leave-one-script-out (direction learned on the other 7 scripts, held-out clip z-scored against the training real clips). AUC over the 16 held-out clips [bootstrap 95% CI over scripts]; full table, windows and paired diffs in `docs/qwen-cues-shadow-eval.txt`. n = 8 scripts (onset and pause cues: 6-8, where a clip had too few onsets or pauses).

| layer | clean | opus8k | g711 | chain_replay | floor_matched | clean paired diff (qwen - real) |
|---|---|---|---|---|---|---|
| qwen_cpp_db | 1.00 [1.00,1.00] | 1.00 [1.00,1.00] | 1.00 [1.00,1.00] | 0.92 [0.70,1.00] | 1.00 [1.00,1.00] | +5.7 dB [+4.9,+6.4], dz +5.0 |
| qwen_f0_rate_st_s | 0.81 [0.58,1.00] | 0.69 [0.53,0.89] | 0.81 [0.59,1.00] | 0.89 [0.66,1.00] | 0.83 [0.58,1.00] | -4.5 st/s [-6.8,-1.8], dz -1.2 |
| qwen_long_pause_per_min | 0.97 [0.75,1.00] | 0.98 [0.82,1.00] | 0.98 [0.82,1.00] | 0.96 [0.86,1.00] | 0.84 [0.67,1.00] | -10.4 /min [-16,-4.2], dz -1.3 |
| qwen_onset_sharpness_db | 0.92 [0.78,1.00] | 0.88 [0.76,1.00] | 0.90 [0.77,1.00] | 0.80 [0.53,1.00] | 0.67 [0.62,0.86] | +11.4 dB [+6.5,+15.6], dz +1.8 |
| qwen_lowmid_balance_db | 0.88 [0.62,1.00] | 0.88 [0.62,1.00] | 0.88 [0.62,1.00] | 0.88 [0.62,1.00] | 0.88 [0.62,1.00] | +5.7 dB [+3.2,+7.4], dz +1.75 |
| (existing) modulation_4_16_ratio | 0.92 [0.73,1.00] | 0.91 [0.73,1.00] | 0.91 [0.72,1.00] | 0.89 [0.78,1.00] | 0.94 [0.84,1.00] | +0.10 [+0.05,+0.17], dz +1.1 |

Reading: AUC 1.00 on 16 clips from 8 scripts with a CI of [1.00, 1.00] only says the 16 held-out clips separate; it is not 100% accuracy on Qwen. The bootstrap resamples 8 scripts, so the true uncertainty is much larger than it looks, and speaker identity, mic and engine are all confounded. The low-mid balance and onset cues are the least trustworthy (probably recorder / room). Pellav2's behaviour on these same pairs was not re-run here. The 6 s-window AUCs (cluster bootstrap by script) are in the eval file and agree with the clip-level ones for cpp, rate and pause; for onset (0.54-0.91) and modulation (0.65-0.77) they are lower, and under replay the onset window AUC is 0.54 with a CI spanning 0.18-0.84. The in-between claim "survives phone band" therefore holds for cpp, long-pause and (less so) f0-rate; it is shaky for onset and modulation.

## What was NOT verified

- Any other speaker, any other engine, any real phone capture, a listening test, or whether a person actually uses these cues. All "what a human hears" statements are inferences from measurable differences, not perceptual experiments.
- The real/Qwen difference in recording chain is only controlled by noise matching and by the degrade conditions; mic EQ and room response are not matched.
- Whisper word timings for pause placement (small, int8) are approximate (about 20-50 ms) and were computed on clean audio only.
- Praat settings were defaults for a male voice (70-400 Hz); formant tracks at 4.5 kHz ceiling.
- The breath/lip-noise and creak/fry measures were too crude to report.
- amr_nb condition was not run (encoder unavailable), as elsewhere in the repo.
- Promotion of any of these needs more speakers, mics and engines, real calls, and an entry in `pm/AUDITS.md`.
