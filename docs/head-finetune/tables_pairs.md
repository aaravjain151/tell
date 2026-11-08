Cells: window AUC [95% CI, clip bootstrap; clean and chain_replay only] / TPR@0.5 / FPR@0.5; n real / fake windows in brackets.

### Sanath real vs his Qwen clone (windows of the 18+2 Sanath clips)

| run | block | clean | opus8k | g711_mulaw8k | chain_replay_call |
|---|---|---|---|---|---|
| script split, clones in train | sanath_pairs/current (77/72) | 1.00 [1.00, 1.00] / 0.57 / 0.00 | 0.99 / 0.15 / 0.00 | 0.97 / 0.00 / 0.00 | 0.63 [0.54, 0.73] / 0.00 / 0.00 |
| script split, clones in train | sanath_pairs_seen_gen/head (77/72) | 1.00 [1.00, 1.00] / 0.99 / 0.00 | 1.00 / 0.99 / 0.00 | 1.00 / 0.99 / 0.00 | 0.98 [0.96, 0.99] / 0.47 / 0.00 |
| script split, clones in train | sanath_pairs_loo_qwen/head (77/72) | 1.00 [1.00, 1.00] / 0.50 / 0.00 | 1.00 / 0.67 / 0.00 | 1.00 / 0.61 / 0.00 | 0.88 [0.80, 0.93] / 0.21 / 0.00 |
| script split, clones in train | sanath_pairs_new/current (45/38) | 1.00 [1.00, 1.00] / 0.74 / 0.00 | 1.00 / 0.21 / 0.00 | 1.00 / 0.00 / 0.00 | 0.67 [0.51, 0.81] / 0.00 / 0.00 |
| script split, clones in train | sanath_pairs_new_seen_gen/head (45/38) | 1.00 [1.00, 1.00] / 1.00 / 0.00 | 1.00 / 1.00 / 0.00 | 1.00 / 1.00 / 0.00 | 0.98 [0.93, 1.00] / 0.42 / 0.00 |
| script split, clones in train | sanath_pairs_new_loo_qwen/head (45/38) | 1.00 [0.99, 1.00] / 0.39 / 0.00 | 1.00 / 0.63 / 0.00 | 1.00 / 0.58 / 0.00 | 0.83 [0.70, 0.94] / 0.13 / 0.00 |
| script split, NO clones in train | sanath_pairs/current (77/72) | 1.00 [1.00, 1.00] / 0.57 / 0.00 | 0.99 / 0.15 / 0.00 | 0.97 / 0.00 / 0.00 | 0.63 [0.54, 0.73] / 0.00 / 0.00 |
| script split, NO clones in train | sanath_pairs_seen_gen/head (77/72) | 1.00 [0.99, 1.00] / 0.92 / 0.00 | 1.00 / 0.90 / 0.00 | 0.99 / 0.79 / 0.00 | 0.93 [0.87, 0.97] / 0.18 / 0.00 |
| script split, NO clones in train | sanath_pairs_loo_qwen/head (77/72) | 1.00 [1.00, 1.00] / 0.50 / 0.00 | 1.00 / 0.67 / 0.00 | 1.00 / 0.61 / 0.00 | 0.88 [0.80, 0.93] / 0.21 / 0.00 |
| script split, NO clones in train | sanath_pairs_new/current (45/38) | 1.00 [1.00, 1.00] / 0.74 / 0.00 | 1.00 / 0.21 / 0.00 | 1.00 / 0.00 / 0.00 | 0.67 [0.51, 0.81] / 0.00 / 0.00 |
| script split, NO clones in train | sanath_pairs_new_seen_gen/head (45/38) | 1.00 [1.00, 1.00] / 0.95 / 0.00 | 1.00 / 0.97 / 0.00 | 1.00 / 0.92 / 0.00 | 0.94 [0.86, 0.99] / 0.29 / 0.00 |
| script split, NO clones in train | sanath_pairs_new_loo_qwen/head (45/38) | 1.00 [0.99, 1.00] / 0.39 / 0.00 | 1.00 / 0.63 / 0.00 | 1.00 / 0.58 / 0.00 | 0.83 [0.70, 0.94] / 0.13 / 0.00 |
| Sanath held out entirely | sanath_pairs/current (77/72) | 1.00 [1.00, 1.00] / 0.57 / 0.00 | 0.99 / 0.15 / 0.00 | 0.97 / 0.00 / 0.00 | 0.63 [0.54, 0.73] / 0.00 / 0.00 |
| Sanath held out entirely | sanath_pairs_seen_gen/head (77/72) | 0.99 [0.97, 1.00] / 0.93 / 0.00 | 0.99 / 0.82 / 0.00 | 0.97 / 0.79 / 0.00 | 0.91 [0.85, 0.97] / 0.01 / 0.00 |
| Sanath held out entirely | sanath_pairs_loo_qwen/head (77/72) | 0.99 [0.98, 1.00] / 0.03 / 0.00 | 0.99 / 0.17 / 0.00 | 0.99 / 0.25 / 0.00 | 0.87 [0.81, 0.93] / 0.04 / 0.00 |
| Sanath held out entirely | sanath_pairs_new/current (45/38) | 1.00 [1.00, 1.00] / 0.74 / 0.00 | 1.00 / 0.21 / 0.00 | 1.00 / 0.00 / 0.00 | 0.67 [0.51, 0.81] / 0.00 / 0.00 |
| Sanath held out entirely | sanath_pairs_new_seen_gen/head (45/38) | 1.00 [1.00, 1.00] / 0.95 / 0.00 | 1.00 / 0.92 / 0.00 | 1.00 / 0.92 / 0.00 | 0.96 [0.91, 0.99] / 0.03 / 0.00 |
| Sanath held out entirely | sanath_pairs_new_loo_qwen/head (45/38) | 0.99 [0.98, 1.00] / 0.03 / 0.00 | 1.00 / 0.16 / 0.00 | 1.00 / 0.34 / 0.00 | 0.88 [0.77, 0.96] / 0.03 / 0.00 |

### Held-out generators, all reals (LibriSpeech + Sanath + friends)

| run | block | clean | opus8k | g711_mulaw8k | chain_replay_call |
|---|---|---|---|---|---|
| script split, clones in train | loo_qwen/head (522/480) | 1.00 [0.99, 1.00] / 0.51 / 0.00 | 0.96 / 0.38 / 0.00 | 0.96 / 0.46 / 0.00 | 0.67 [0.64, 0.71] / 0.07 / 0.00 |
| script split, clones in train | loo_gradium/head (522/72) | 1.00 [1.00, 1.00] / 1.00 / 0.00 | 1.00 / 1.00 / 0.02 | 1.00 / 1.00 / 0.01 | 0.81 [0.75, 0.86] / 0.22 / 0.02 |
| script split, clones in train | loo_say/head (522/94) | 1.00 [1.00, 1.00] / 1.00 / 0.00 | 1.00 / 1.00 / 0.02 | 1.00 / 1.00 / 0.01 | 0.92 [0.88, 0.96] / 0.47 / 0.01 |
| script split, clones in train | seen_gen/head (522/646) | 1.00 [1.00, 1.00] / 1.00 / 0.00 | 1.00 / 0.97 / 0.02 | 1.00 / 0.98 / 0.01 | 0.85 [0.83, 0.88] / 0.33 / 0.03 |
| script split, clones in train | loo_qwen/current (522/480) | 1.00 [1.00, 1.00] / 0.84 / 0.00 | 0.98 / 0.48 / 0.00 | 0.98 / 0.33 / 0.00 | 0.58 [0.54, 0.62] / 0.01 / 0.01 |
| script split, NO clones in train | loo_qwen/head (522/480) | 1.00 [0.99, 1.00] / 0.51 / 0.00 | 0.96 / 0.38 / 0.00 | 0.96 / 0.46 / 0.00 | 0.67 [0.64, 0.71] / 0.07 / 0.00 |
| script split, NO clones in train | loo_gradium/head (522/72) | 1.00 [1.00, 1.00] / 1.00 / 0.00 | 1.00 / 1.00 / 0.02 | 1.00 / 1.00 / 0.01 | 0.63 [0.54, 0.72] / 0.04 / 0.01 |
| script split, NO clones in train | loo_say/head (522/94) | 1.00 [1.00, 1.00] / 1.00 / 0.00 | 1.00 / 1.00 / 0.02 | 1.00 / 1.00 / 0.02 | 0.88 [0.83, 0.92] / 0.41 / 0.01 |
| script split, NO clones in train | seen_gen/head (522/646) | 1.00 [1.00, 1.00] / 0.99 / 0.00 | 1.00 / 0.96 / 0.02 | 1.00 / 0.96 / 0.02 | 0.84 [0.81, 0.86] / 0.30 / 0.02 |
| script split, NO clones in train | loo_qwen/current (522/480) | 1.00 [1.00, 1.00] / 0.84 / 0.00 | 0.98 / 0.48 / 0.00 | 0.98 / 0.33 / 0.00 | 0.58 [0.54, 0.62] / 0.01 / 0.01 |
| Sanath held out entirely | loo_qwen/head (522/480) | 1.00 [0.99, 1.00] / 0.40 / 0.00 | 0.95 / 0.30 / 0.00 | 0.96 / 0.40 / 0.00 | 0.66 [0.62, 0.70] / 0.05 / 0.00 |
| Sanath held out entirely | loo_gradium/head (522/72) | 1.00 [1.00, 1.00] / 1.00 / 0.00 | 1.00 / 1.00 / 0.02 | 1.00 / 1.00 / 0.01 | 0.78 [0.72, 0.83] / 0.15 / 0.01 |
| Sanath held out entirely | loo_say/head (522/94) | 1.00 [1.00, 1.00] / 1.00 / 0.00 | 1.00 / 1.00 / 0.02 | 1.00 / 1.00 / 0.01 | 0.89 [0.85, 0.94] / 0.39 / 0.02 |
| Sanath held out entirely | seen_gen/head (522/646) | 1.00 [1.00, 1.00] / 0.99 / 0.00 | 1.00 / 0.96 / 0.02 | 1.00 / 0.97 / 0.01 | 0.85 [0.83, 0.88] / 0.26 / 0.01 |
| Sanath held out entirely | loo_qwen/current (522/480) | 1.00 [1.00, 1.00] / 0.84 / 0.00 | 0.98 / 0.48 / 0.00 | 0.98 / 0.33 / 0.00 | 0.58 [0.54, 0.62] / 0.01 / 0.01 |
| 2026-11-07 hum_cluster (old Sanath set) | loo_qwen/head (485/442) | 1.00 [0.99, 1.00] / 0.62 / 0.00 | 0.95 / 0.41 / 0.00 | 0.96 / 0.42 / 0.00 | 0.63 [0.59, 0.67] / 0.05 / 0.00 |
| 2026-11-07 hum_cluster (old Sanath set) | loo_gradium/head (485/72) | 1.00 [1.00, 1.00] / 1.00 / 0.00 | 1.00 / 1.00 / 0.02 | 1.00 / 1.00 / 0.01 | 0.77 [0.71, 0.84] / 0.08 / 0.02 |
| 2026-11-07 hum_cluster (old Sanath set) | loo_say/head (485/94) | 1.00 [1.00, 1.00] / 1.00 / 0.00 | 1.00 / 1.00 / 0.03 | 1.00 / 1.00 / 0.01 | 0.89 [0.84, 0.94] / 0.46 / 0.01 |
| 2026-11-07 hum_cluster (old Sanath set) | seen_gen/head (485/608) | 1.00 [1.00, 1.00] / 0.99 / 0.00 | 0.99 / 0.96 / 0.03 | 0.99 / 0.97 / 0.01 | 0.82 [0.79, 0.85] / 0.27 / 0.01 |
| 2026-11-07 hum_cluster (old Sanath set) | loo_qwen/current (485/442) | 1.00 [1.00, 1.00] / 0.85 / 0.00 | 0.98 / 0.50 / 0.00 | 0.98 / 0.36 / 0.00 | 0.58 [0.53, 0.62] / 0.01 / 0.01 |

### Human false alarms at 0.5 by source (share of windows; each scored by a model that never saw its speaker group / script)

| run | model | source | clean | opus8k | g711_mulaw8k | chain_replay_call | g711_alaw8k | chain_pstn_voip |
|---|---|---|---|---|---|---|---|---|
| script split, clones in train | head_seen_gen | libri (n=400) | 0.00 | 0.03 | 0.01 | 0.04 | 0.01 | 0.10 |
| script split, clones in train | head_seen_gen | sanath (n=77) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| script split, clones in train | head_seen_gen | friends (n=45) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| script split, clones in train | head_loo_qwen | libri (n=400) | 0.00 | 0.01 | 0.00 | 0.00 | 0.00 | 0.01 |
| script split, clones in train | head_loo_qwen | sanath (n=77) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| script split, clones in train | head_loo_qwen | friends (n=45) | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | 0.00 |
| script split, clones in train | current | libri (n=400) | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | 0.57 |
| script split, clones in train | current | sanath (n=77) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.35 |
| script split, clones in train | current | friends (n=45) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.51 |
| script split, NO clones in train | head_seen_gen | libri (n=400) | 0.00 | 0.03 | 0.02 | 0.02 | 0.02 | 0.15 |
| script split, NO clones in train | head_seen_gen | sanath (n=77) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| script split, NO clones in train | head_seen_gen | friends (n=45) | 0.00 | 0.00 | 0.02 | 0.00 | 0.02 | 0.00 |
| script split, NO clones in train | head_loo_qwen | libri (n=400) | 0.00 | 0.01 | 0.00 | 0.00 | 0.00 | 0.01 |
| script split, NO clones in train | head_loo_qwen | sanath (n=77) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| script split, NO clones in train | head_loo_qwen | friends (n=45) | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | 0.00 |
| script split, NO clones in train | current | libri (n=400) | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | 0.57 |
| script split, NO clones in train | current | sanath (n=77) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.35 |
| script split, NO clones in train | current | friends (n=45) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.51 |
| Sanath held out entirely | head_seen_gen | libri (n=400) | 0.00 | 0.03 | 0.01 | 0.01 | 0.02 | 0.12 |
| Sanath held out entirely | head_seen_gen | sanath (n=77) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Sanath held out entirely | head_seen_gen | friends (n=45) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 |
| Sanath held out entirely | head_loo_qwen | libri (n=400) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 |
| Sanath held out entirely | head_loo_qwen | sanath (n=77) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Sanath held out entirely | head_loo_qwen | friends (n=45) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Sanath held out entirely | current | libri (n=400) | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | 0.57 |
| Sanath held out entirely | current | sanath (n=77) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.35 |
| Sanath held out entirely | current | friends (n=45) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.51 |
