n rows=440 (AI 152, human 288); groups=47; features=42
| protocol | subset | condition | n AI / human clips | hand-tuned p_ai AUC [95% CI] | learned LR AUC [95% CI] | learned - hand [95% CI] |
|---|---|---|---|---|---|---|
| leave-one-speaker-group-out | Qwen clone vs Sanath (paired) | all | 20 / 20 | 0.76 [0.63, 0.87] | 0.44 [0.28, 0.61] | -0.32 [-0.48, -0.17] |
| leave-one-speaker-group-out | Qwen clone vs Sanath (paired) | chain_replay_call | 20 / 20 | 0.64 [0.45, 0.79] | 0.33 [0.17, 0.50] | -0.31 [-0.51, -0.09] |
| leave-one-speaker-group-out | Qwen clone vs Sanath (paired) | clean | 20 / 20 | 0.95 [0.84, 1.00] | 0.59 [0.41, 0.76] | -0.36 [-0.55, -0.19] |
| leave-one-speaker-group-out | Qwen clone vs Sanath (paired) | g711_mulaw8k | 20 / 20 | 0.68 [0.51, 0.84] | 0.36 [0.20, 0.55] | -0.32 [-0.51, -0.13] |
| leave-one-speaker-group-out | Qwen clone vs Sanath (paired) | opus8k | 20 / 20 | 0.77 [0.61, 0.92] | 0.49 [0.30, 0.67] | -0.29 [-0.47, -0.12] |
| leave-one-speaker-group-out | Qwen clone vs all humans | all | 20 / 72 | 0.74 [0.65, 0.82] | 0.64 [0.52, 0.76] | -0.10 [-0.21, 0.00] |
| leave-one-speaker-group-out | Qwen clone vs all humans | chain_replay_call | 20 / 72 | 0.66 [0.52, 0.78] | 0.58 [0.43, 0.71] | -0.08 [-0.24, 0.07] |
| leave-one-speaker-group-out | Qwen clone vs all humans | clean | 20 / 72 | 0.97 [0.93, 1.00] | 0.80 [0.69, 0.90] | -0.17 [-0.28, -0.07] |
| leave-one-speaker-group-out | Qwen clone vs all humans | g711_mulaw8k | 20 / 72 | 0.63 [0.49, 0.77] | 0.55 [0.41, 0.67] | -0.09 [-0.23, 0.06] |
| leave-one-speaker-group-out | Qwen clone vs all humans | opus8k | 20 / 72 | 0.76 [0.62, 0.89] | 0.64 [0.49, 0.78] | -0.13 [-0.28, 0.02] |
| leave-one-speaker-group-out | all AI vs all humans | all | 38 / 72 | 0.83 [0.77, 0.89] | 0.80 [0.72, 0.89] | -0.03 [-0.10, 0.03] |
| leave-one-speaker-group-out | all AI vs all humans | chain_replay_call | 38 / 72 | 0.73 [0.63, 0.82] | 0.73 [0.63, 0.83] | +0.00 [-0.11, 0.11] |
| leave-one-speaker-group-out | all AI vs all humans | clean | 38 / 72 | 0.98 [0.96, 1.00] | 0.90 [0.83, 0.95] | -0.09 [-0.15, -0.04] |
| leave-one-speaker-group-out | all AI vs all humans | g711_mulaw8k | 38 / 72 | 0.79 [0.69, 0.88] | 0.75 [0.65, 0.85] | -0.04 [-0.12, 0.04] |
| leave-one-speaker-group-out | all AI vs all humans | opus8k | 38 / 72 | 0.87 [0.78, 0.95] | 0.81 [0.71, 0.90] | -0.06 [-0.15, 0.01] |
<!-- leave-one-speaker-group-out chain_replay_call: humans flagged hand p_ai>=0.60 1/72, learned>=0.5 9/72; Qwen caught hand 1/20, learned 4/20 -->
<!-- leave-one-speaker-group-out clean: humans flagged hand p_ai>=0.60 1/72, learned>=0.5 2/72; Qwen caught hand 2/20, learned 3/20 -->
<!-- leave-one-speaker-group-out g711_mulaw8k: humans flagged hand p_ai>=0.60 1/72, learned>=0.5 4/72; Qwen caught hand 1/20, learned 1/20 -->
<!-- leave-one-speaker-group-out opus8k: humans flagged hand p_ai>=0.60 1/72, learned>=0.5 4/72; Qwen caught hand 1/20, learned 3/20 -->
| groups + Sanath by script (5-fold) | Qwen clone vs Sanath (paired) | all | 20 / 20 | 0.76 [0.63, 0.87] | 0.96 [0.92, 0.98] | +0.20 [0.10, 0.32] |
| groups + Sanath by script (5-fold) | Qwen clone vs Sanath (paired) | chain_replay_call | 20 / 20 | 0.64 [0.47, 0.81] | 0.75 [0.58, 0.89] | +0.11 [-0.11, 0.33] |
| groups + Sanath by script (5-fold) | Qwen clone vs Sanath (paired) | clean | 20 / 20 | 0.95 [0.84, 1.00] | 1.00 [1.00, 1.00] | +0.05 [0.00, 0.16] |
| groups + Sanath by script (5-fold) | Qwen clone vs Sanath (paired) | g711_mulaw8k | 20 / 20 | 0.68 [0.50, 0.84] | 0.99 [0.98, 1.00] | +0.31 [0.16, 0.49] |
| groups + Sanath by script (5-fold) | Qwen clone vs Sanath (paired) | opus8k | 20 / 20 | 0.77 [0.62, 0.92] | 1.00 [1.00, 1.00] | +0.23 [0.08, 0.38] |
| groups + Sanath by script (5-fold) | Qwen clone vs all humans | all | 20 / 72 | 0.74 [0.66, 0.82] | 0.98 [0.96, 0.99] | +0.23 [0.15, 0.31] |
| groups + Sanath by script (5-fold) | Qwen clone vs all humans | chain_replay_call | 20 / 72 | 0.66 [0.53, 0.78] | 0.88 [0.80, 0.95] | +0.22 [0.10, 0.36] |
| groups + Sanath by script (5-fold) | Qwen clone vs all humans | clean | 20 / 72 | 0.97 [0.93, 1.00] | 1.00 [1.00, 1.00] | +0.03 [0.00, 0.07] |
| groups + Sanath by script (5-fold) | Qwen clone vs all humans | g711_mulaw8k | 20 / 72 | 0.63 [0.50, 0.77] | 0.99 [0.96, 1.00] | +0.35 [0.22, 0.49] |
| groups + Sanath by script (5-fold) | Qwen clone vs all humans | opus8k | 20 / 72 | 0.76 [0.61, 0.89] | 1.00 [1.00, 1.00] | +0.24 [0.11, 0.39] |
| groups + Sanath by script (5-fold) | all AI vs all humans | all | 38 / 72 | 0.83 [0.77, 0.89] | 0.98 [0.97, 0.99] | +0.15 [0.10, 0.21] |
| groups + Sanath by script (5-fold) | all AI vs all humans | chain_replay_call | 38 / 72 | 0.73 [0.63, 0.82] | 0.92 [0.87, 0.96] | +0.19 [0.10, 0.29] |
| groups + Sanath by script (5-fold) | all AI vs all humans | clean | 38 / 72 | 0.98 [0.96, 1.00] | 1.00 [1.00, 1.00] | +0.02 [0.00, 0.04] |
| groups + Sanath by script (5-fold) | all AI vs all humans | g711_mulaw8k | 38 / 72 | 0.79 [0.69, 0.88] | 0.98 [0.96, 1.00] | +0.19 [0.11, 0.29] |
| groups + Sanath by script (5-fold) | all AI vs all humans | opus8k | 38 / 72 | 0.87 [0.78, 0.95] | 1.00 [1.00, 1.00] | +0.13 [0.05, 0.22] |
<!-- groups + Sanath by script (5-fold) chain_replay_call: humans flagged hand p_ai>=0.60 1/72, learned>=0.5 5/72; Qwen caught hand 1/20, learned 10/20 -->
<!-- groups + Sanath by script (5-fold) clean: humans flagged hand p_ai>=0.60 1/72, learned>=0.5 0/72; Qwen caught hand 2/20, learned 19/20 -->
<!-- groups + Sanath by script (5-fold) g711_mulaw8k: humans flagged hand p_ai>=0.60 1/72, learned>=0.5 1/72; Qwen caught hand 1/20, learned 16/20 -->
<!-- groups + Sanath by script (5-fold) opus8k: humans flagged hand p_ai>=0.60 1/72, learned>=0.5 3/72; Qwen caught hand 1/20, learned 20/20 -->

largest standardised weights (fit on ALL rows, interpretation only): shadow:spectral_flatness_300_3400 -1.67, shadow:qwen_onset_sharpness_db +1.23, tell:neural_hf -1.13, shadow:digital_zero_run_ms -1.12, shadow:qwen_f0_rate_st_s -0.93, shadow:qwen_cpp_db +0.92, tell:neural_pella +0.78, tell:llm_isms +0.78
