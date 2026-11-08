
### pella_mlp  (head params 262426, train 74.0 s for all folds)

| scenario | voter | condition | n real | n fake | AUC [95% CI] | EER | FPR@TPR90 | TPR@FPR5% | TPR@0.5 | FPR@0.5 |
|---|---|---|---|---|---|---|---|---|---|---|
| loo_qwen | pella_mlp | clean | 440 | 442 | 1.00 [0.99, 1.00] | 0.02 | 0.00 | 0.99 | 0.48 | 0.00 |
| loo_qwen | pella_mlp | opus8k | 440 | 442 | 0.96 | 0.11 | 0.11 | 0.85 | 0.38 | 0.00 |
| loo_qwen | pella_mlp | g711_mulaw8k | 440 | 442 | 0.97 | 0.11 | 0.12 | 0.88 | 0.46 | 0.00 |
| loo_qwen | pella_mlp | chain_replay_call | 440 | 442 | 0.65 [0.61, 0.68] | 0.40 | 0.79 | 0.16 | 0.06 | 0.01 |
| loo_qwen | pella_mlp | g711_alaw8k | 440 | 442 | 0.96 | 0.11 | 0.13 | 0.86 | 0.44 | 0.00 |
| loo_qwen | pella_mlp | chain_pstn_voip | 440 | 442 | 0.78 | 0.29 | 0.61 | 0.33 | 0.14 | 0.01 |
| loo_qwen | current | clean | 440 | 442 | 1.00 [1.00, 1.00] | 0.00 | 0.00 | 1.00 | 0.85 | 0.00 |
| loo_qwen | current | opus8k | 440 | 442 | 0.98 | 0.07 | 0.04 | 0.91 | 0.50 | 0.00 |
| loo_qwen | current | g711_mulaw8k | 440 | 442 | 0.99 | 0.05 | 0.02 | 0.95 | 0.36 | 0.00 |
| loo_qwen | current | chain_replay_call | 440 | 442 | 0.58 [0.54, 0.62] | 0.43 | 0.85 | 0.06 | 0.01 | 0.01 |
| loo_qwen | current | g711_alaw8k | 440 | 442 | 0.99 | 0.06 | 0.02 | 0.94 | 0.33 | 0.00 |
| loo_qwen | current | chain_pstn_voip | 440 | 442 | 0.76 | 0.33 | 0.58 | 0.30 | 0.88 | 0.55 |
| loo_gradium | pella_mlp | clean | 440 | 72 | 1.00 [1.00, 1.00] | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 |
| loo_gradium | pella_mlp | opus8k | 440 | 72 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 | 0.04 |
| loo_gradium | pella_mlp | g711_mulaw8k | 440 | 72 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 | 0.02 |
| loo_gradium | pella_mlp | chain_replay_call | 440 | 72 | 0.82 [0.77, 0.88] | 0.28 | 0.47 | 0.38 | 0.25 | 0.03 |
| loo_gradium | pella_mlp | g711_alaw8k | 440 | 72 | 1.00 | 0.01 | 0.00 | 1.00 | 1.00 | 0.02 |
| loo_gradium | pella_mlp | chain_pstn_voip | 440 | 72 | 0.96 | 0.13 | 0.14 | 0.68 | 0.83 | 0.10 |
| loo_gradium | current | clean | 440 | 72 | 1.00 [1.00, 1.00] | 0.00 | 0.00 | 1.00 | 0.97 | 0.00 |
| loo_gradium | current | opus8k | 440 | 72 | 1.00 | 0.01 | 0.01 | 1.00 | 0.74 | 0.00 |
| loo_gradium | current | g711_mulaw8k | 440 | 72 | 1.00 | 0.02 | 0.00 | 1.00 | 0.46 | 0.00 |
| loo_gradium | current | chain_replay_call | 440 | 72 | 0.42 [0.35, 0.50] | 0.53 | 0.89 | 0.03 | 0.00 | 0.01 |
| loo_gradium | current | g711_alaw8k | 440 | 72 | 1.00 | 0.03 | 0.00 | 1.00 | 0.54 | 0.00 |
| loo_gradium | current | chain_pstn_voip | 440 | 72 | 0.90 | 0.19 | 0.33 | 0.56 | 1.00 | 0.55 |
| loo_say | pella_mlp | clean | 440 | 94 | 1.00 [1.00, 1.00] | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 |
| loo_say | pella_mlp | opus8k | 440 | 94 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 | 0.02 |
| loo_say | pella_mlp | g711_mulaw8k | 440 | 94 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 | 0.01 |
| loo_say | pella_mlp | chain_replay_call | 440 | 94 | 0.92 [0.88, 0.96] | 0.14 | 0.20 | 0.66 | 0.54 | 0.02 |
| loo_say | pella_mlp | g711_alaw8k | 440 | 94 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 | 0.01 |
| loo_say | pella_mlp | chain_pstn_voip | 440 | 94 | 1.00 | 0.01 | 0.00 | 1.00 | 1.00 | 0.25 |
| loo_say | current | clean | 440 | 94 | 1.00 [1.00, 1.00] | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 |
| loo_say | current | opus8k | 440 | 94 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 |
| loo_say | current | g711_mulaw8k | 440 | 94 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 |
| loo_say | current | chain_replay_call | 440 | 94 | 0.73 [0.67, 0.80] | 0.32 | 0.69 | 0.19 | 0.03 | 0.01 |
| loo_say | current | g711_alaw8k | 440 | 94 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 |
| loo_say | current | chain_pstn_voip | 440 | 94 | 1.00 | 0.03 | 0.01 | 0.97 | 1.00 | 0.55 |
| sanath_only_loo_qwen | pella_mlp | clean | 40 | 34 | 0.98 [0.90, 1.00] | 0.04 | 0.00 | 0.94 | 0.26 | 0.00 |
| sanath_only_loo_qwen | pella_mlp | opus8k | 40 | 34 | 0.95 | 0.18 | 0.17 | 0.79 | 0.32 | 0.00 |
| sanath_only_loo_qwen | pella_mlp | g711_mulaw8k | 40 | 34 | 0.95 | 0.15 | 0.28 | 0.82 | 0.09 | 0.00 |
| sanath_only_loo_qwen | pella_mlp | chain_replay_call | 40 | 34 | 0.80 [0.70, 0.88] | 0.31 | 0.50 | 0.26 | 0.06 | 0.03 |
| sanath_only_loo_qwen | pella_mlp | g711_alaw8k | 40 | 34 | 0.93 | 0.15 | 0.28 | 0.74 | 0.06 | 0.00 |
| sanath_only_loo_qwen | pella_mlp | chain_pstn_voip | 40 | 34 | 0.96 | 0.09 | 0.10 | 0.85 | 0.06 | 0.00 |
| sanath_only_loo_qwen | current | clean | 40 | 34 | 1.00 [0.99, 1.00] | 0.01 | 0.00 | 0.97 | 0.38 | 0.00 |
| sanath_only_loo_qwen | current | opus8k | 40 | 34 | 0.97 | 0.16 | 0.17 | 0.79 | 0.09 | 0.00 |
| sanath_only_loo_qwen | current | g711_mulaw8k | 40 | 34 | 0.94 | 0.19 | 0.30 | 0.79 | 0.00 | 0.00 |
| sanath_only_loo_qwen | current | chain_replay_call | 40 | 34 | 0.65 [0.53, 0.75] | 0.44 | 0.82 | 0.29 | 0.00 | 0.00 |
| sanath_only_loo_qwen | current | g711_alaw8k | 40 | 34 | 0.92 | 0.15 | 0.33 | 0.76 | 0.00 | 0.00 |
| sanath_only_loo_qwen | current | chain_pstn_voip | 40 | 34 | 0.86 | 0.22 | 0.30 | 0.59 | 0.85 | 0.30 |
| seen_gen | pella_mlp | clean | 440 | 608 | 1.00 [1.00, 1.00] | 0.00 | 0.00 | 1.00 | 0.99 | 0.00 |
| seen_gen | pella_mlp | opus8k | 440 | 608 | 0.99 | 0.04 | 0.00 | 0.97 | 0.95 | 0.02 |
| seen_gen | pella_mlp | g711_mulaw8k | 440 | 608 | 0.99 | 0.02 | 0.00 | 0.98 | 0.95 | 0.00 |
| seen_gen | pella_mlp | chain_replay_call | 440 | 608 | 0.81 [0.78, 0.84] | 0.26 | 0.54 | 0.37 | 0.25 | 0.01 |
| seen_gen | pella_mlp | g711_alaw8k | 440 | 608 | 0.99 | 0.03 | 0.00 | 0.98 | 0.95 | 0.01 |
| seen_gen | pella_mlp | chain_pstn_voip | 440 | 608 | 0.91 | 0.17 | 0.28 | 0.64 | 0.69 | 0.07 |
| seen_gen | current | clean | 440 | 608 | 1.00 [1.00, 1.00] | 0.00 | 0.00 | 1.00 | 0.89 | 0.00 |
| seen_gen | current | opus8k | 440 | 608 | 0.99 | 0.06 | 0.03 | 0.94 | 0.61 | 0.00 |
| seen_gen | current | g711_mulaw8k | 440 | 608 | 0.99 | 0.04 | 0.01 | 0.97 | 0.47 | 0.00 |
| seen_gen | current | chain_replay_call | 440 | 608 | 0.59 [0.55, 0.62] | 0.43 | 0.85 | 0.08 | 0.01 | 0.01 |
| seen_gen | current | g711_alaw8k | 440 | 608 | 0.99 | 0.05 | 0.01 | 0.95 | 0.46 | 0.00 |
| seen_gen | current | chain_pstn_voip | 440 | 608 | 0.81 | 0.29 | 0.52 | 0.43 | 0.91 | 0.55 |

owner files (mean P(synthetic) over production windows):
- owner_rough_morning (n windows 3): current {'clean': 0.6665828824043274, 'opus8k': 0.6683056354522705, 'chain_replay_call': 0.0007941715302877128}
    head loo_qwen: {'clean': 0.6551119685173035, 'opus8k': 0.9693653583526611, 'chain_replay_call': 0.161277636885643}
    head seen_gen: {'clean': 0.9483232498168945, 'opus8k': 0.9943235516548157, 'chain_replay_call': 0.33325257897377014}
- owner_long_tech_scam (n windows 3): current {'clean': 0.016651853919029236, 'opus8k': 0.0025740766432136297, 'chain_replay_call': 0.0010424017673358321}
    head loo_qwen: {'clean': 0.7316415905952454, 'opus8k': 0.8874551653862, 'chain_replay_call': 0.4786592423915863}
    head seen_gen: {'clean': 0.9356384873390198, 'opus8k': 0.9907674789428711, 'chain_replay_call': 0.6832900047302246}

### hf_mlp  (head params 262426, train 70.3 s for all folds)

| scenario | voter | condition | n real | n fake | AUC [95% CI] | EER | FPR@TPR90 | TPR@FPR5% | TPR@0.5 | FPR@0.5 |
|---|---|---|---|---|---|---|---|---|---|---|
| loo_qwen | hf_mlp | clean | 440 | 442 | 0.64 [0.60, 0.67] | 0.39 | 0.79 | 0.16 | 0.05 | 0.00 |
| loo_qwen | hf_mlp | opus8k | 440 | 442 | 0.60 | 0.44 | 0.84 | 0.17 | 0.05 | 0.00 |
| loo_qwen | hf_mlp | g711_mulaw8k | 440 | 442 | 0.63 | 0.40 | 0.80 | 0.17 | 0.05 | 0.00 |
| loo_qwen | hf_mlp | chain_replay_call | 440 | 442 | 0.64 [0.60, 0.68] | 0.39 | 0.82 | 0.19 | 0.13 | 0.02 |
| loo_qwen | hf_mlp | g711_alaw8k | 440 | 442 | 0.63 | 0.40 | 0.79 | 0.16 | 0.05 | 0.00 |
| loo_qwen | hf_mlp | chain_pstn_voip | 440 | 442 | 0.55 | 0.46 | 0.90 | 0.13 | 0.06 | 0.00 |
| loo_qwen | current | clean | 440 | 442 | 0.52 [0.48, 0.56] | 0.48 | 0.83 | 0.07 | 0.24 | 0.29 |
| loo_qwen | current | opus8k | 440 | 442 | 0.54 | 0.47 | 0.87 | 0.07 | 0.45 | 0.40 |
| loo_qwen | current | g711_mulaw8k | 440 | 442 | 0.53 | 0.48 | 0.83 | 0.07 | 0.23 | 0.26 |
| loo_qwen | current | chain_replay_call | 440 | 442 | 0.38 [0.34, 0.42] | 0.58 | 0.98 | 0.04 | 0.21 | 0.27 |
| loo_qwen | current | g711_alaw8k | 440 | 442 | 0.53 | 0.48 | 0.84 | 0.07 | 0.22 | 0.25 |
| loo_qwen | current | chain_pstn_voip | 440 | 442 | 0.61 | 0.41 | 0.81 | 0.10 | 0.89 | 0.81 |
| loo_gradium | hf_mlp | clean | 440 | 72 | 0.88 [0.81, 0.93] | 0.21 | 0.27 | 0.50 | 0.67 | 0.12 |
| loo_gradium | hf_mlp | opus8k | 440 | 72 | 0.85 | 0.23 | 0.48 | 0.54 | 0.65 | 0.14 |
| loo_gradium | hf_mlp | g711_mulaw8k | 440 | 72 | 0.87 | 0.21 | 0.39 | 0.57 | 0.71 | 0.15 |
| loo_gradium | hf_mlp | chain_replay_call | 440 | 72 | 0.92 [0.88, 0.96] | 0.17 | 0.23 | 0.62 | 0.71 | 0.08 |
| loo_gradium | hf_mlp | g711_alaw8k | 440 | 72 | 0.88 | 0.19 | 0.36 | 0.57 | 0.72 | 0.15 |
| loo_gradium | hf_mlp | chain_pstn_voip | 440 | 72 | 0.79 | 0.33 | 0.60 | 0.56 | 0.61 | 0.18 |
| loo_gradium | current | clean | 440 | 72 | 0.78 [0.70, 0.85] | 0.33 | 0.44 | 0.32 | 0.57 | 0.29 |
| loo_gradium | current | opus8k | 440 | 72 | 0.76 | 0.35 | 0.52 | 0.19 | 0.75 | 0.40 |
| loo_gradium | current | g711_mulaw8k | 440 | 72 | 0.76 | 0.35 | 0.48 | 0.19 | 0.51 | 0.26 |
| loo_gradium | current | chain_replay_call | 440 | 72 | 0.21 [0.16, 0.27] | 0.74 | 0.98 | 0.00 | 0.03 | 0.27 |
| loo_gradium | current | g711_alaw8k | 440 | 72 | 0.75 | 0.35 | 0.47 | 0.24 | 0.49 | 0.25 |
| loo_gradium | current | chain_pstn_voip | 440 | 72 | 0.84 | 0.23 | 0.42 | 0.33 | 1.00 | 0.81 |
| loo_say | hf_mlp | clean | 440 | 94 | 0.97 [0.95, 0.98] | 0.05 | 0.05 | 0.96 | 1.00 | 0.11 |
| loo_say | hf_mlp | opus8k | 440 | 94 | 0.97 | 0.04 | 0.04 | 0.97 | 1.00 | 0.13 |
| loo_say | hf_mlp | g711_mulaw8k | 440 | 94 | 0.97 | 0.06 | 0.05 | 0.90 | 1.00 | 0.12 |
| loo_say | hf_mlp | chain_replay_call | 440 | 94 | 0.94 [0.90, 0.98] | 0.13 | 0.15 | 0.73 | 0.74 | 0.06 |
| loo_say | hf_mlp | g711_alaw8k | 440 | 94 | 0.97 | 0.06 | 0.05 | 0.93 | 1.00 | 0.14 |
| loo_say | hf_mlp | chain_pstn_voip | 440 | 94 | 0.90 | 0.18 | 0.26 | 0.33 | 0.84 | 0.20 |
| loo_say | current | clean | 440 | 94 | 0.98 [0.97, 0.99] | 0.03 | 0.03 | 0.99 | 1.00 | 0.29 |
| loo_say | current | opus8k | 440 | 94 | 0.98 | 0.04 | 0.03 | 0.97 | 1.00 | 0.40 |
| loo_say | current | g711_mulaw8k | 440 | 94 | 1.00 | 0.02 | 0.01 | 1.00 | 1.00 | 0.26 |
| loo_say | current | chain_replay_call | 440 | 94 | 0.07 [0.03, 0.12] | 0.86 | 1.00 | 0.02 | 0.02 | 0.27 |
| loo_say | current | g711_alaw8k | 440 | 94 | 1.00 | 0.01 | 0.00 | 1.00 | 1.00 | 0.25 |
| loo_say | current | chain_pstn_voip | 440 | 94 | 0.85 | 0.20 | 0.24 | 0.12 | 1.00 | 0.81 |
| sanath_only_loo_qwen | hf_mlp | clean | 40 | 34 | 0.59 [0.44, 0.75] | 0.38 | 0.68 | 0.09 | 0.00 | 0.00 |
| sanath_only_loo_qwen | hf_mlp | opus8k | 40 | 34 | 0.70 | 0.39 | 0.65 | 0.12 | 0.00 | 0.00 |
| sanath_only_loo_qwen | hf_mlp | g711_mulaw8k | 40 | 34 | 0.58 | 0.38 | 0.65 | 0.09 | 0.00 | 0.03 |
| sanath_only_loo_qwen | hf_mlp | chain_replay_call | 40 | 34 | 0.71 [0.58, 0.82] | 0.39 | 0.70 | 0.29 | 0.53 | 0.25 |
| sanath_only_loo_qwen | hf_mlp | g711_alaw8k | 40 | 34 | 0.57 | 0.39 | 0.78 | 0.09 | 0.00 | 0.03 |
| sanath_only_loo_qwen | hf_mlp | chain_pstn_voip | 40 | 34 | 0.69 | 0.32 | 0.68 | 0.24 | 0.06 | 0.00 |
| sanath_only_loo_qwen | current | clean | 40 | 34 | 0.68 [0.50, 0.81] | 0.44 | 0.50 | 0.06 | 0.06 | 0.00 |
| sanath_only_loo_qwen | current | opus8k | 40 | 34 | 0.79 | 0.28 | 0.50 | 0.29 | 0.41 | 0.10 |
| sanath_only_loo_qwen | current | g711_mulaw8k | 40 | 34 | 0.55 | 0.44 | 0.68 | 0.03 | 0.03 | 0.05 |
| sanath_only_loo_qwen | current | chain_replay_call | 40 | 34 | 0.29 [0.16, 0.41] | 0.71 | 1.00 | 0.09 | 0.06 | 0.03 |
| sanath_only_loo_qwen | current | g711_alaw8k | 40 | 34 | 0.55 | 0.44 | 0.70 | 0.03 | 0.03 | 0.05 |
| sanath_only_loo_qwen | current | chain_pstn_voip | 40 | 34 | 0.99 | 0.03 | 0.03 | 0.97 | 1.00 | 0.17 |
| seen_gen | hf_mlp | clean | 440 | 608 | 0.97 [0.96, 0.98] | 0.09 | 0.08 | 0.84 | 0.94 | 0.11 |
| seen_gen | hf_mlp | opus8k | 440 | 608 | 0.96 | 0.10 | 0.11 | 0.77 | 0.91 | 0.12 |
| seen_gen | hf_mlp | g711_mulaw8k | 440 | 608 | 0.96 | 0.09 | 0.09 | 0.79 | 0.93 | 0.12 |
| seen_gen | hf_mlp | chain_replay_call | 440 | 608 | 0.89 [0.86, 0.91] | 0.19 | 0.35 | 0.61 | 0.56 | 0.04 |
| seen_gen | hf_mlp | g711_alaw8k | 440 | 608 | 0.96 | 0.11 | 0.10 | 0.79 | 0.92 | 0.13 |
| seen_gen | hf_mlp | chain_pstn_voip | 440 | 608 | 0.90 | 0.17 | 0.33 | 0.65 | 0.79 | 0.14 |
| seen_gen | current | clean | 440 | 608 | 0.63 [0.58, 0.66] | 0.42 | 0.79 | 0.24 | 0.39 | 0.29 |
| seen_gen | current | opus8k | 440 | 608 | 0.64 | 0.41 | 0.82 | 0.22 | 0.57 | 0.40 |
| seen_gen | current | g711_mulaw8k | 440 | 608 | 0.63 | 0.41 | 0.79 | 0.23 | 0.38 | 0.26 |
| seen_gen | current | chain_replay_call | 440 | 608 | 0.32 [0.28, 0.35] | 0.63 | 1.00 | 0.03 | 0.16 | 0.27 |
| seen_gen | current | g711_alaw8k | 440 | 608 | 0.63 | 0.41 | 0.79 | 0.23 | 0.37 | 0.25 |
| seen_gen | current | chain_pstn_voip | 440 | 608 | 0.67 | 0.36 | 0.78 | 0.13 | 0.92 | 0.81 |

owner files (mean P(synthetic) over production windows):
- owner_rough_morning (n windows 3): current {'clean': 0.04470457509160042, 'opus8k': 0.1822689324617386, 'chain_replay_call': 0.19592833518981934}
    head loo_qwen: {'clean': 0.02064472623169422, 'opus8k': 0.020938856527209282, 'chain_replay_call': 0.21954242885112762}
    head seen_gen: {'clean': 0.6632127165794373, 'opus8k': 0.571033775806427, 'chain_replay_call': 0.40357622504234314}
- owner_long_tech_scam (n windows 3): current {'clean': 0.09958314895629883, 'opus8k': 0.6039038896560669, 'chain_replay_call': 0.007031748536974192}
    head loo_qwen: {'clean': 0.43305858969688416, 'opus8k': 0.5703358054161072, 'chain_replay_call': 0.7722087502479553}
    head seen_gen: {'clean': 0.9997828602790833, 'opus8k': 0.9987409710884094, 'chain_replay_call': 0.905626118183136}
