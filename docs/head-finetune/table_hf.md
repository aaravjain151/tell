| scenario | condition | n real / fake | voter | AUC | EER | FPR@TPR90 | TPR@FPR5% | FPR@0.5 |
|---|---|---|---|---|---|---|---|---|
| hold out Qwen | clean | 440 / 442 | HF wav2vec2 voter (current) | 0.52 | 0.48 | 0.83 | 0.07 | 0.29 |
| hold out Qwen | clean | 440 / 442 | head on HF layers | 0.64 | 0.39 | 0.79 | 0.16 | 0.00 |
| hold out Qwen | opus8k | 440 / 442 | HF wav2vec2 voter (current) | 0.54 | 0.47 | 0.87 | 0.07 | 0.40 |
| hold out Qwen | opus8k | 440 / 442 | head on HF layers | 0.60 | 0.44 | 0.84 | 0.17 | 0.00 |
| hold out Qwen | g711_mulaw8k | 440 / 442 | HF wav2vec2 voter (current) | 0.53 | 0.48 | 0.83 | 0.07 | 0.26 |
| hold out Qwen | g711_mulaw8k | 440 / 442 | head on HF layers | 0.63 | 0.40 | 0.80 | 0.17 | 0.00 |
| hold out Qwen | chain_replay_call | 440 / 442 | HF wav2vec2 voter (current) | 0.38 | 0.58 | 0.98 | 0.04 | 0.27 |
| hold out Qwen | chain_replay_call | 440 / 442 | head on HF layers | 0.64 | 0.39 | 0.82 | 0.19 | 0.02 |
| hold out Gradium | clean | 440 / 72 | HF wav2vec2 voter (current) | 0.78 | 0.33 | 0.44 | 0.32 | 0.29 |
| hold out Gradium | clean | 440 / 72 | head on HF layers | 0.88 | 0.21 | 0.27 | 0.50 | 0.12 |
| hold out Gradium | opus8k | 440 / 72 | HF wav2vec2 voter (current) | 0.76 | 0.35 | 0.52 | 0.19 | 0.40 |
| hold out Gradium | opus8k | 440 / 72 | head on HF layers | 0.85 | 0.23 | 0.48 | 0.54 | 0.14 |
| hold out Gradium | g711_mulaw8k | 440 / 72 | HF wav2vec2 voter (current) | 0.76 | 0.35 | 0.48 | 0.19 | 0.26 |
| hold out Gradium | g711_mulaw8k | 440 / 72 | head on HF layers | 0.87 | 0.21 | 0.39 | 0.57 | 0.15 |
| hold out Gradium | chain_replay_call | 440 / 72 | HF wav2vec2 voter (current) | 0.21 | 0.74 | 0.98 | 0.00 | 0.27 |
| hold out Gradium | chain_replay_call | 440 / 72 | head on HF layers | 0.92 | 0.17 | 0.23 | 0.62 | 0.08 |
| hold out macOS say | clean | 440 / 94 | HF wav2vec2 voter (current) | 0.98 | 0.03 | 0.03 | 0.99 | 0.29 |
| hold out macOS say | clean | 440 / 94 | head on HF layers | 0.97 | 0.05 | 0.05 | 0.96 | 0.11 |
| hold out macOS say | opus8k | 440 / 94 | HF wav2vec2 voter (current) | 0.98 | 0.04 | 0.03 | 0.97 | 0.40 |
| hold out macOS say | opus8k | 440 / 94 | head on HF layers | 0.97 | 0.04 | 0.04 | 0.97 | 0.13 |
| hold out macOS say | g711_mulaw8k | 440 / 94 | HF wav2vec2 voter (current) | 1.00 | 0.02 | 0.01 | 1.00 | 0.26 |
| hold out macOS say | g711_mulaw8k | 440 / 94 | head on HF layers | 0.97 | 0.06 | 0.05 | 0.90 | 0.12 |
| hold out macOS say | chain_replay_call | 440 / 94 | HF wav2vec2 voter (current) | 0.07 | 0.86 | 1.00 | 0.02 | 0.27 |
| hold out macOS say | chain_replay_call | 440 / 94 | head on HF layers | 0.94 | 0.13 | 0.15 | 0.73 | 0.06 |
| speakers held out, generators seen | clean | 440 / 608 | HF wav2vec2 voter (current) | 0.63 | 0.42 | 0.79 | 0.24 | 0.29 |
| speakers held out, generators seen | clean | 440 / 608 | head on HF layers | 0.97 | 0.09 | 0.08 | 0.84 | 0.11 |
| speakers held out, generators seen | opus8k | 440 / 608 | HF wav2vec2 voter (current) | 0.64 | 0.41 | 0.82 | 0.22 | 0.40 |
| speakers held out, generators seen | opus8k | 440 / 608 | head on HF layers | 0.96 | 0.10 | 0.11 | 0.77 | 0.12 |
| speakers held out, generators seen | g711_mulaw8k | 440 / 608 | HF wav2vec2 voter (current) | 0.63 | 0.41 | 0.79 | 0.23 | 0.26 |
| speakers held out, generators seen | g711_mulaw8k | 440 / 608 | head on HF layers | 0.96 | 0.09 | 0.09 | 0.79 | 0.12 |
| speakers held out, generators seen | chain_replay_call | 440 / 608 | HF wav2vec2 voter (current) | 0.32 | 0.63 | 1.00 | 0.03 | 0.27 |
| speakers held out, generators seen | chain_replay_call | 440 / 608 | head on HF layers | 0.89 | 0.19 | 0.35 | 0.61 | 0.04 |
| Sanath only, hold out Qwen | clean | 40 / 34 | HF wav2vec2 voter (current) | 0.68 | 0.44 | 0.50 | 0.06 | 0.00 |
| Sanath only, hold out Qwen | clean | 40 / 34 | head on HF layers | 0.59 | 0.38 | 0.68 | 0.09 | 0.00 |
| Sanath only, hold out Qwen | opus8k | 40 / 34 | HF wav2vec2 voter (current) | 0.79 | 0.28 | 0.50 | 0.29 | 0.10 |
| Sanath only, hold out Qwen | opus8k | 40 / 34 | head on HF layers | 0.70 | 0.39 | 0.65 | 0.12 | 0.00 |
| Sanath only, hold out Qwen | g711_mulaw8k | 40 / 34 | HF wav2vec2 voter (current) | 0.55 | 0.44 | 0.68 | 0.03 | 0.05 |
| Sanath only, hold out Qwen | g711_mulaw8k | 40 / 34 | head on HF layers | 0.58 | 0.38 | 0.65 | 0.09 | 0.03 |
| Sanath only, hold out Qwen | chain_replay_call | 40 / 34 | HF wav2vec2 voter (current) | 0.29 | 0.71 | 1.00 | 0.09 | 0.03 |
| Sanath only, hold out Qwen | chain_replay_call | 40 / 34 | head on HF layers | 0.71 | 0.39 | 0.70 | 0.29 | 0.25 |