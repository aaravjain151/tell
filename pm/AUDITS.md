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
