# Personal learning (opt-in, on-device, notification sensitivity only)

Like a phone keyboard that learns your next word, Tell can learn **when you want to be interrupted**. It never learns what a call *is*.

**Honest name.** This is *online learning*: a Thompson-sampling contextual bandit over six sensitivity arms per call profile (the default), with an online logistic calibration kept as the tested alternative. It is **not** deep reinforcement learning. The whole state is a few dozen numbers.

Code: `services/api/tell/personal.py`. Tools: `tools/personal/{collect,simulate,fusion}.py`. Tests: `services/api/tests/test_personal.py`.

## What it learns

1. **A per-user alert sensitivity** from the four feedback buttons ("That was a scam", "Not a scam", "It was AI", "It was a person"). Each label becomes "an alert was / was not warranted on this call". "It was AI" on a call that already said it was automated carries no information and is skipped.
2. **A persistent prior per call profile**, with decay. Profiles: automated-and-said-so without payment words, automated-and-said-so with payment words, undisclosed synthetic voice, a person who mentions urgency or money, everything else. Each profile keeps a decayed count of "warranted" vs "not warranted" (every new label multiplies old counts by 0.97, half-life about 23 labels), and its shrunken rate adds a small extra shift.

Per call it builds a small feature vector (`CallFeatures`): final `p_ai`, `p_scam`, peak scores, highest `stable.alert` level reached, how many intent families fired, whether the caller disclosed, band-limited flag, shadow cues (`snr_db`, `bandwidth_hz`, `noise_floor_std_db`, `gate_transitions_per_min`) and a duration bucket. Numbers and booleans only, built from an allowlist.

### Bounds (enforced in `decide()`, re-clipped there, tested)

| What | Range | Meaning |
|---|---|---|
| amber notification threshold shift | -0.10 .. +0.15 on the 0.55 scam-score base | + means alert less, - means alert sooner |
| red notification threshold shift | -0.10 .. 0.00 on the 0.80 base | red can only become easier to reach |
| extra profile prior | -0.03 .. +0.05 | added to the amber shift, then the sum is clipped again |

With no feedback every shift is exactly 0 and `personal_alert` equals `stable.alert`.

## What it never does

- It does not touch `scorer.py`, `thresholds.py`, tier, `p_ai`, `p_scam`, `confidence`, the signature, the stored verdict, or the `stable` object of the live stream. The UI verdict is unchanged.
- It **never lowers a stabiliser red** (every red carries corroboration, two intent families with a payment or credential ask, or `p_scam` >= 0.8).
- It **never lowers any alert on a call where the caller disclosed nothing and payment or credential intent fired.**
- It never speaks, uploads, or shares anything.

The only output is one extra field in the live event, `personal_alert: none|amber|red`, present only when the feature is on. `stable.alert` stays authoritative; a UI that wants to notify less simply reads `personal_alert` for the *notification* and still shows `stable` as before.

## Privacy

- Off by default. Active only if `TELL_PERSONAL=1` **and** the user switched it on (`POST /personal`).
- On-device only. `personal.py` has no network code (checked by `test_import_scan` / `test_network_guard`).
- Encrypted at rest with AES-256-GCM through `secure_store` (key in the OS keychain, never on disk). If the keychain is unavailable the feature stays off (fails closed). File mode 0600, atomic replace. A tampered or corrupt file is ignored.
- Holds only weights and decayed counts. No audio, no transcript, no evidence strings, no per-call log. Recent per-call feature vectors live in memory only (last 50) so a feedback label can be matched to its call.
- Wipeable: `DELETE /personal` removes the file and the in-memory calls.

## HTTP contract (loopback client, allowed Origin and Host)

- `GET /personal` -> `{enabled, available, n_feedback, sensitivity, explain:[str]}`. `sensitivity` = `{amber:{profile:shift}, red:shift, amber_range, red_range, learner}`.
- `POST /personal` `{enabled:bool}` -> same shape. Cannot enable while the env flag is off.
- `DELETE /personal` -> `{wiped:true}`.

`explain` uses fixed wording only, for example: "Tell has learned to alert you slightly less for automated appointment calls that say they are automated." (or "slightly sooner for ..."). Until 5 labels are in: "Tell is still learning from your feedback and has not changed anything yet." The last line is always: "This only changes when you are notified. It never changes what a call is judged to be, and a strong scam alert is always shown."

## Feedback adapter

Feedback storage (`POST /feedback`, `feedback.recent(n)`) is built on another branch. `personal.py` consumes an abstract list of dicts `{id?, call_id?, label, tick?, ts?}` through `FeedbackSource.recent(n)`. `feedback_adapter()` imports `tell.feedback` if it exists (reversing newest-first output) and otherwise returns an empty `FakeFeedback`, so the layer is inert, not broken. Records are de-duplicated by `id` (else by `ts|call_id|label|tick`). A record with an unknown or missing `call_id` is attributed to the most recent finished call (assumption: feedback follows the call). Learning runs when a call ends and on `GET /personal`.

## Why Thompson sampling (the simulation choice)

Both learners were run on the same simulated streams (below). Thompson had the lower miss-weighted cost (false alert = 1, missed scam = 3) in 9 of 9 cells, with intervals clearly separated only in the scam-exposed persona; in the other cells the two are statistically indistinguishable. Logistic gave slightly fewer false alerts when feedback was clean but lost that under 20% label noise. Thompson was kept as the default because it was never worse on cost and degrades more gently under noise. This is a weak preference, not a finding. The cost weight (3x) is also the weight the learners use, so the metric partly rewards what they optimise.

## Offline simulation

**LOUD CAVEAT: the call stream is simulated.** Real inputs: the clips in `data/calls` (3 TTS engines + 1 human speaker, 39 clip templates x 2 conditions) and the owner's two Qwen files (no owner recordings were present). On those real clips the fixed stabiliser already makes no mistakes (scam clips have `p_scam` >= 0.84, others 0), so there is nothing to learn from them. Three categories (a reminder that mentions urgency, a person who mentions urgency, a soft scam below the scam threshold) are **synthesised from assumed score ranges**. Personas, their call mixes, the feedback habits (60% of alerted calls and 25% of quiet calls get a label) and the label noise are assumptions. Calls are replayed through the real `StableTracker`. No audio is committed or read at simulation time (`collect.py` extracts numbers once).

Setup: 100 simulated streams x 300 calls per cell; metrics over the last two thirds of each stream; mean over streams with a 95% percentile bootstrap over streams (2000 draws). Noise = probability a feedback label is flipped. n per cell = 100 streams (about 20,000 evaluated calls, from only ~39 distinct clips plus synthetic ranges).

| persona | feedback noise | policy | false-alert rate | missed-scam rate | alerts / 100 calls | cost / 100 calls (miss x3) |
|---|---|---|---|---|---|---|
| appointment-heavy | 0 | fixed | 47.5 [46.8, 48.2]% | 44.8 [42.7, 46.9]% | 48.2 [47.6, 48.9] | 56.1 [55.2, 56.9] |
| appointment-heavy | 0 | logistic | 40.2 [39.4, 40.8]% | 49.1 [47.1, 51.1]% | 41.3 [40.6, 42.0] | 51.2 [50.3, 52.2] |
| appointment-heavy | 0 | thompson | 45.2 [44.3, 46.2]% | 32.1 [28.9, 35.4]% | 47.6 [46.6, 48.6] | 50.6 [49.6, 51.6] |
| appointment-heavy | 0.1 | fixed | 47.5 [46.7, 48.2]% | 44.8 [42.7, 46.9]% | 48.2 [47.5, 48.9] | 56.1 [55.2, 56.9] |
| appointment-heavy | 0.1 | logistic | 42.6 [41.9, 43.4]% | 42.5 [40.2, 44.7]% | 44.2 [43.5, 45.0] | 51.2 [50.2, 52.1] |
| appointment-heavy | 0.1 | thompson | 46.4 [45.5, 47.3]% | 28.1 [24.8, 31.3]% | 49.1 [48.1, 50.1] | 50.4 [49.5, 51.4] |
| appointment-heavy | 0.2 | fixed | 47.5 [46.8, 48.1]% | 44.8 [42.7, 46.9]% | 48.2 [47.5, 49.0] | 56.1 [55.2, 56.9] |
| appointment-heavy | 0.2 | logistic | 46.1 [45.4, 46.8]% | 33.1 [30.6, 35.7]% | 48.3 [47.5, 49.0] | 51.5 [50.7, 52.4] |
| appointment-heavy | 0.2 | thompson | 47.6 [46.7, 48.4]% | 27.4 [24.4, 30.5]% | 50.2 [49.3, 51.3] | 51.1 [50.2, 52.0] |
| scam-exposed | 0 | fixed | 14.9 [14.2, 15.6]% | 64.3 [63.4, 65.2]% | 25.3 [24.8, 25.9] | 104.1 [102.4, 106.0] |
| scam-exposed | 0 | logistic | 26.2 [25.3, 27.0]% | 5.1 [4.5, 5.6]% | 60.8 [60.2, 61.5] | 20.6 [19.7, 21.5] |
| scam-exposed | 0 | thompson | 20.1 [19.3, 20.9]% | 5.1 [4.6, 5.6]% | 57.7 [57.1, 58.4] | 17.7 [16.9, 18.6] |
| scam-exposed | 0.1 | fixed | 14.9 [14.2, 15.6]% | 64.3 [63.4, 65.2]% | 25.3 [24.8, 25.9] | 104.1 [102.4, 106.0] |
| scam-exposed | 0.1 | logistic | 26.3 [25.4, 27.1]% | 5.9 [5.2, 6.7]% | 60.5 [59.7, 61.3] | 22.0 [20.9, 23.1] |
| scam-exposed | 0.1 | thompson | 20.4 [19.6, 21.2]% | 5.6 [5.0, 6.2]% | 57.7 [57.0, 58.4] | 18.5 [17.6, 19.5] |
| scam-exposed | 0.2 | fixed | 14.9 [14.2, 15.6]% | 64.3 [63.4, 65.2]% | 25.3 [24.8, 25.9] | 104.1 [102.4, 105.9] |
| scam-exposed | 0.2 | logistic | 26.4 [25.5, 27.4]% | 7.1 [6.1, 8.0]% | 59.9 [59.0, 60.8] | 23.7 [22.4, 25.1] |
| scam-exposed | 0.2 | thompson | 20.5 [19.7, 21.4]% | 6.6 [5.9, 7.5]% | 57.2 [56.4, 58.0] | 20.1 [18.9, 21.4] |
| typical | 0 | fixed | 15.1 [14.6, 15.7]% | 29.4 [27.9, 30.9]% | 23.5 [22.9, 24.1] | 26.2 [25.4, 27.0] |
| typical | 0 | logistic | 8.9 [8.5, 9.4]% | 31.8 [30.2, 33.4]% | 18.1 [17.5, 18.7] | 22.3 [21.3, 23.3] |
| typical | 0 | thompson | 13.2 [12.5, 13.8]% | 21.1 [18.9, 23.3]% | 23.4 [22.5, 24.3] | 20.7 [19.8, 21.7] |
| typical | 0.1 | fixed | 15.1 [14.6, 15.7]% | 29.4 [27.9, 30.9]% | 23.5 [22.9, 24.1] | 26.2 [25.4, 27.1] |
| typical | 0.1 | logistic | 13.6 [12.9, 14.4]% | 23.7 [21.7, 25.7]% | 23.3 [22.4, 24.2] | 22.3 [21.4, 23.2] |
| typical | 0.1 | thompson | 14.2 [13.6, 14.9]% | 19.6 [17.5, 21.6]% | 24.6 [23.7, 25.4] | 21.0 [20.1, 21.9] |
| typical | 0.2 | fixed | 15.1 [14.6, 15.7]% | 29.4 [27.9, 30.8]% | 23.5 [22.9, 24.1] | 26.2 [25.3, 27.1] |
| typical | 0.2 | logistic | 17.6 [16.8, 18.4]% | 16.7 [14.7, 18.7]% | 27.7 [26.7, 28.6] | 22.4 [21.5, 23.3] |
| typical | 0.2 | thompson | 14.9 [14.1, 15.6]% | 18.7 [16.6, 20.9]% | 25.1 [24.2, 26.1] | 21.1 [20.2, 22.0] |

Reading it:

- **Helps (in this simulated world):** the scam-exposed persona. Missed scams fall from about 64% to 5-7%, because the learner moves the amber threshold earlier for calls the user reports as scams. Cost: alerts per 100 calls rise from 25 to 57-61 and the false-alert rate from 15% to 20-26%. That is a real trade, more interruptions for fewer misses.
- **Helps a little:** appointment-heavy and typical personas, mostly through fewer false alerts or fewer misses depending on the learner; the miss-weighted cost improves by about 9-20%, and for these personas the intervals between learners overlap.
- **Does not help, or hurts:** (1) when the quieted profile also contains true scams (a person who mentions urgency, benign vs soft scam look the same in score), quieting one hurts the other; the learner can only shift a threshold, not separate them. (2) Logistic with noise-free feedback in the appointment-heavy persona raised the miss rate (44.8% to 49.1%). (3) With 20% label noise the logistic learner's false-alert rate in the typical persona is worse than fixed (17.6% vs 15.1%). (4) On the real clips: nothing to improve.
- Not covered: users who give feedback on very few calls, drifting preferences, adversarial feedback, correlated labels (a user who taps "scam" on everything).

## Learned fusion (shadow only, not wired in)

`tools/personal/fusion.py` fits a small L2 logistic regression over every Tell score plus the shadow features and compares it with the hand-tuned `p_ai` on AI-voice vs human-voice, using held-out predictions only.

| protocol | folds | model | AUC [95% CI] | EER [95% CI] |
|---|---|---|---|---|
| leave-one-engine-out | 4 | hand-tuned p_ai | 0.83 [0.62, 0.99] | 0.25 [0.05, 0.42] |
| leave-one-engine-out | 4 | learned LR | 0.97 [0.91, 1.00] | 0.05 [0.00, 0.17] |
| leave-one-engine-out | | AUC difference (learned - hand) | +0.14 [-0.03, 0.37] | |
| leave-one-script-out | 13 | hand-tuned p_ai | 0.83 [0.62, 0.99] | 0.25 [0.05, 0.42] |
| leave-one-script-out | 13 | learned LR | 0.99 [0.98, 1.00] | 0.05 [0.00, 0.13] |
| leave-one-script-out | | AUC difference (learned - hand) | +0.16 [0.00, 0.38] | |

Interpretation, honestly: the learned model looks better (AUC +0.14, +0.16), but the paired-difference intervals touch zero (-0.03 .. 0.37 and 0.00 .. 0.38), n is 78 clips (58 AI, 20 human) from **one** human speaker, and the largest weights (pause regularity, SNR, noise-floor level and variability, bandwidth) are exactly the features that can separate one person's microphone and room from TTS output. Leave-one-speaker-out is **not possible** (one human speaker; the owner's recordings folder holds only a README). Leave-one-engine-out holds out a TTS engine, not a human speaker, so it cannot detect a speaker confound on the human side. Do not wire this in until there are several human speakers recorded on different devices.

## Limits

- One human speaker, tiny n, simulated users. Nothing here is evidence about real-world performance.
- The learner trades interruptions for misses; it can make a user's phone buzz more.
- Feedback is a noisy, self-selected sample. Labels like "It was a person" say nothing about scam intent and are treated as "not warranted".
- Thompson arms are updated with full-information counterfactuals (the label tells us what every arm would have done), so this is closer to Bayesian arm weighting than to a partial-feedback bandit.
- Profiles are coarse (five). A change in one profile cannot separate two look-alike situations inside it.
- Attribution of a label to a call uses the last finished call when no `call_id` is given.
