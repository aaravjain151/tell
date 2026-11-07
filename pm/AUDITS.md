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
