# Detection layers: what we have, what each is evidence of, what it cannot see

Status 2026-11-07. Honest map, not a marketing sheet. Evidence base: ONE human speaker, a few dozen clips, three TTS families. Nothing below is a measured real-world accuracy.

Why this page exists: a real iPhone to Mac Continuity call with an AI voice scored p_ai 0.24-0.47 for the whole call, and we said human. Narrowband codecs and replay strip the cues that anti-spoof models lean on, so a mid-range score is "no evidence", not "human".

## Layers

| Layer | What it measures | Evidence of | Cannot see |
|---|---|---|---|
| Acoustic tells (`signals/acoustic.py`): pause regularity, breath proxy (shown, weight 0 since 2026-11-08), pitch stability, noise floor, band-limit flag (5-7.5 kHz vs 1-4 kHz) | Behaviour and recording traits of the waveform | A clean, evenly paced, breathless recording that looks like unprocessed TTS | Anything once a phone line, codec or room has re-shaped the audio. Humans on noise-suppressed lines look "too clean"; TTS replayed into a room looks "natural". Read-aloud speech looks regular too |
| Neural voter: Pellav2 (`neural.py`, `pella.py`) | Spoof probability per window from a local model | Artefacts of specific vocoders it was trained on | Codec TTS and unseen engines (it is near blind on Qwen3-TTS here), phone-band or replayed audio, any engine it never saw. Every window up to 16, mean window logit (2026-11-08) |
| Learned voter `learned_tells` (`learned.py`, docs/LEARNED-TELLS.md) | Logistic regression on a PCA of Pellav2's frozen layer-12 embedding, logit centred on held-in humans; names interpretable tells in its evidence | A voice unlike the 435 real voices it was trained on; held-out generators caught in clean and phone codecs | The replay chain (catch 0 at 0.60); real calls from speakers unlike audiobook readers; it needs Pellav2 running |
| Neural voter: HF anti-spoof checkpoint (garystafford wav2vec2) | Same idea, different model | ElevenLabs-style output (it was trained on it, so that engine is in-domain, not a fair test) | Near chance on Qwen3-TTS in our set; degrades on narrowband |
| Neural voter: optional ONNX anti-spoof (`neural_onnx`) | A user-supplied ONNX model, off unless configured | Whatever that model was trained for | Unknown until someone evaluates the model they plug in; same channel caveats as above |
| Script tells (`signals/script.py`) | Wording of the transcript: contractions, uniform sentences, denial of being an AI | An LLM-written script read out | A human reading a script; an agent prompted to sound casual. Not valid on short ASR snippets for perplexity-style claims |
| Intent tells (`signals/intent.py`) | Scam patterns: payment rails, credential asks, urgency, secrecy, emergency, authority threat | Content that matches known scam scripts | Whether the speaker is a machine. A human scammer scores the same; a real bank warning is guarded by negation rules |
| Stabiliser (`stabiliser.py`) | Smooths what the live page SHOWS across ticks, latches alerts | Persistence of the per-tick verdicts | It adds no evidence. It cannot fix a voter that is wrong every tick |
| Shadow layers (`signals/shadow.py`) | Noise floor level and variability, digital-zero and gate events, 4-16 Hz modulation, long-term flatness, loudness consistency, call-level score persistence, bandwidth and SNR | Descriptors of the recording and channel, logged for measurement | Everything. They are NOT used by the scorer and not shown as a verdict. On our data the only separators are room/recorder properties of one speaker's mic |

## Shadow means shadow

The shadow dict lives in `egress.context.shadow` (and the live tick's copy of it). It is added after fusion, outside the signed payload, and a test asserts tier, p_ai, p_scam, confidence and signature are bit-identical with the module enabled or patched out. `tools/shadow_report.py` and `run_eval.py --wild --dump` log it for offline study. Promotion would need several human speakers on different mics, real phone captures and a decision logged in `pm/AUDITS.md`.

## Channel conditions we evaluate (`tools/redteam/degrade.py`)

clean, opus8k, amr_nb (needs an ffmpeg with libopencore_amrnb; absent on the dev machine, so not run), g711_mulaw8k, g711_alaw8k, opus_lowbitrate_with_loss (our own burst-loss concealment, not libopus PLC), speaker_rerecord_sim (synthetic RIR, 150 Hz to 4 kHz, room noise), and two chains. Applied identically to every class. Wild eval prints per-condition AUC, EER, FPR@90%TPR and leave-one-engine-out with n beside each number.

## Claims we must not make

- Any p_ai below the threshold, however low, means "human". A mid-range score on phone-band or relayed audio is "unclear: detectors not reliable here".
- "No watermark" means human. Watermarks are positive-only evidence, and we have no evidence that Qwen3-TTS or Gradium mark their output.
- A low noise floor, clean silence or digital zeros prove AI, or the reverse. DTX comfort noise, noise-suppression apps, AGC and acoustic replay move these in both directions.
- 12.5 Hz or 25 Hz codec-frame periodicity detects Qwen3-TTS. Our probe found no such line.
- Vendor numbers (99% accuracy, under 1% false positives, per-codec 92-100% tables) are ours. They are unreplicated marketing.
- Latency or overlap behaviour proves a machine. Speech-to-speech agents answer in about 200-300 ms like humans, and people on bad lines are slow. (Dialogue timing is not built yet.)
- Text perplexity or "sounds like ChatGPT" is proof of an AI caller. Detectors misflag non-native speakers and ASR text has no reliable punctuation or fillers.
- Our eval numbers generalise. One human speaker means any separation may be speaker identity; three TTS families and tens of clips do not describe the set of fakes.
- Leaderboard or ASVspoof EERs describe telephone audio. They are wideband and mostly pre-codec-TTS.
- "Safe", "verified human", or that `confidence` is a calibrated probability or accuracy. It measures agreement and coverage of our own signals.
- Pellav2 or HF scores transfer across engines. Leave-one-engine-out shows they do not, especially for Qwen3-TTS.

## Known gaps (not built)

Two-channel dialogue timing (turn latency, barge-in, overlap, backchannels) is the one signal family independent of codec and vocoder; it needs the near channel. Codec/loss-augmented training of a voter. Watermark checks (AudioSeal) as positive-only evidence. A "phone band, detectors unreliable" state when the band-limit flag is on and the neural voters are mid-range. Whether a failing Continuity test injected the AI digitally or played it acoustically into the iPhone mic is unverified, and it decides which of the noise-floor cues could ever help.
