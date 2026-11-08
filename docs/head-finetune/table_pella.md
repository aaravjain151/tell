| scenario | condition | n real / fake | voter | AUC | EER | FPR@TPR90 | TPR@FPR5% | FPR@0.5 |
|---|---|---|---|---|---|---|---|---|
| hold out Qwen | clean | 440 / 442 | Pellav2 (current) | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| hold out Qwen | clean | 440 / 442 | head on Pellav2 layers | 1.00 | 0.02 | 0.00 | 0.99 | 0.00 |
| hold out Qwen | opus8k | 440 / 442 | Pellav2 (current) | 0.98 | 0.07 | 0.04 | 0.91 | 0.00 |
| hold out Qwen | opus8k | 440 / 442 | head on Pellav2 layers | 0.96 | 0.11 | 0.11 | 0.85 | 0.00 |
| hold out Qwen | g711_mulaw8k | 440 / 442 | Pellav2 (current) | 0.99 | 0.05 | 0.02 | 0.95 | 0.00 |
| hold out Qwen | g711_mulaw8k | 440 / 442 | head on Pellav2 layers | 0.97 | 0.11 | 0.12 | 0.88 | 0.00 |
| hold out Qwen | chain_replay_call | 440 / 442 | Pellav2 (current) | 0.58 | 0.43 | 0.85 | 0.06 | 0.01 |
| hold out Qwen | chain_replay_call | 440 / 442 | head on Pellav2 layers | 0.65 | 0.40 | 0.79 | 0.16 | 0.01 |
| hold out Gradium | clean | 440 / 72 | Pellav2 (current) | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| hold out Gradium | clean | 440 / 72 | head on Pellav2 layers | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| hold out Gradium | opus8k | 440 / 72 | Pellav2 (current) | 1.00 | 0.01 | 0.01 | 1.00 | 0.00 |
| hold out Gradium | opus8k | 440 / 72 | head on Pellav2 layers | 1.00 | 0.00 | 0.00 | 1.00 | 0.04 |
| hold out Gradium | g711_mulaw8k | 440 / 72 | Pellav2 (current) | 1.00 | 0.02 | 0.00 | 1.00 | 0.00 |
| hold out Gradium | g711_mulaw8k | 440 / 72 | head on Pellav2 layers | 1.00 | 0.00 | 0.00 | 1.00 | 0.02 |
| hold out Gradium | chain_replay_call | 440 / 72 | Pellav2 (current) | 0.42 | 0.53 | 0.89 | 0.03 | 0.01 |
| hold out Gradium | chain_replay_call | 440 / 72 | head on Pellav2 layers | 0.82 | 0.28 | 0.47 | 0.38 | 0.03 |
| hold out macOS say | clean | 440 / 94 | Pellav2 (current) | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| hold out macOS say | clean | 440 / 94 | head on Pellav2 layers | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| hold out macOS say | opus8k | 440 / 94 | Pellav2 (current) | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| hold out macOS say | opus8k | 440 / 94 | head on Pellav2 layers | 1.00 | 0.00 | 0.00 | 1.00 | 0.02 |
| hold out macOS say | g711_mulaw8k | 440 / 94 | Pellav2 (current) | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| hold out macOS say | g711_mulaw8k | 440 / 94 | head on Pellav2 layers | 1.00 | 0.00 | 0.00 | 1.00 | 0.01 |
| hold out macOS say | chain_replay_call | 440 / 94 | Pellav2 (current) | 0.73 | 0.32 | 0.69 | 0.19 | 0.01 |
| hold out macOS say | chain_replay_call | 440 / 94 | head on Pellav2 layers | 0.92 | 0.14 | 0.20 | 0.66 | 0.02 |
| speakers held out, generators seen | clean | 440 / 608 | Pellav2 (current) | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| speakers held out, generators seen | clean | 440 / 608 | head on Pellav2 layers | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| speakers held out, generators seen | opus8k | 440 / 608 | Pellav2 (current) | 0.99 | 0.06 | 0.03 | 0.94 | 0.00 |
| speakers held out, generators seen | opus8k | 440 / 608 | head on Pellav2 layers | 0.99 | 0.04 | 0.00 | 0.97 | 0.02 |
| speakers held out, generators seen | g711_mulaw8k | 440 / 608 | Pellav2 (current) | 0.99 | 0.04 | 0.01 | 0.97 | 0.00 |
| speakers held out, generators seen | g711_mulaw8k | 440 / 608 | head on Pellav2 layers | 0.99 | 0.02 | 0.00 | 0.98 | 0.00 |
| speakers held out, generators seen | chain_replay_call | 440 / 608 | Pellav2 (current) | 0.59 | 0.43 | 0.85 | 0.08 | 0.01 |
| speakers held out, generators seen | chain_replay_call | 440 / 608 | head on Pellav2 layers | 0.81 | 0.26 | 0.54 | 0.37 | 0.01 |
| Sanath only, hold out Qwen | clean | 40 / 34 | Pellav2 (current) | 1.00 | 0.01 | 0.00 | 0.97 | 0.00 |
| Sanath only, hold out Qwen | clean | 40 / 34 | head on Pellav2 layers | 0.98 | 0.04 | 0.00 | 0.94 | 0.00 |
| Sanath only, hold out Qwen | opus8k | 40 / 34 | Pellav2 (current) | 0.97 | 0.16 | 0.17 | 0.79 | 0.00 |
| Sanath only, hold out Qwen | opus8k | 40 / 34 | head on Pellav2 layers | 0.95 | 0.18 | 0.17 | 0.79 | 0.00 |
| Sanath only, hold out Qwen | g711_mulaw8k | 40 / 34 | Pellav2 (current) | 0.94 | 0.19 | 0.30 | 0.79 | 0.00 |
| Sanath only, hold out Qwen | g711_mulaw8k | 40 / 34 | head on Pellav2 layers | 0.95 | 0.15 | 0.28 | 0.82 | 0.00 |
| Sanath only, hold out Qwen | chain_replay_call | 40 / 34 | Pellav2 (current) | 0.65 | 0.44 | 0.82 | 0.29 | 0.00 |
| Sanath only, hold out Qwen | chain_replay_call | 40 / 34 | head on Pellav2 layers | 0.80 | 0.31 | 0.50 | 0.26 | 0.03 |