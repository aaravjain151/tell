"""Single home for every weight and threshold. Bump THRESHOLDS_VERSION when you change anything.

Scores are in [0, 1]. Acoustic/script scores point *toward AI*; intent scores point *toward scam*.
"""

THRESHOLDS_VERSION = "2026-11-08.2"   # .2 = few_pauses voter (abstains unless long pauses are rare; signals/pauses.py).
                                      # .1 = learned_tells voter (W 8), breath_proxy 1.2 -> 0, Pellav2 all windows +
                                      #      logit mean, band_limited re-defined (docs/LEARNED-TELLS.md). 2026-11-07.3 before.

# --- fusion weights (normalised at runtime over the signals that actually ran) ---
ACOUSTIC_WEIGHTS = {
    "pause_regularity": 1.0,
    "breath_proxy": 0.0,   # 1.2 -> 0 (2026-11-08): scored ~0.1-0.27 on every real clip, human AND AI (949 clips), so it only dragged p_ai down; shown, not fused
    "pitch_stability": 0.9,
    "noise_floor": 0.8,
    "high_band": 0.5,  # down-weighted automatically when band_limited
    # 2026-11-08: learned_tells (signals/learned.py), held-out by generator x speaker group x channel: at 8.0 every cell catches
    # at least as much as the 2026-11-07.3 engine at 0 human false alarms, and it halves the false alarms on lossy paths
    # (chain_pstn_voip 156 -> 73 of 435 real voices). 12 lost held-out Qwen opus8k catch. See docs/LEARNED-TELLS.md.
    "learned_tells": 8.0,
    # 2026-11-08.2: few_pauses (signals/pauses.py). Votes ONLY when long pauses (>= 300 ms) are rare over >= 15 s of speech,
    # otherwise abstains, so it can push toward AI but never pulls an engine that pauses naturally toward human. Qwen3-TTS
    # clones leave about half the long pauses of the same speaker (cue study 18 pairs, AUC 0.76-0.80; local pairs 5-6/7).
    "few_pauses": 3.0,
}
# few_pauses: long pauses per minute of speech span. Humans ~15-25 (local memos: median 19 clean, 15 replay), Qwen ~10.
PAUSE_RATE_SUSPECT = 12.0    # at or below -> the voter fires (score PAUSE_VOTE_MIN at this rate)
PAUSE_VOTE_MIN = 0.8         # lowest score of a vote: above any clip's voice mean, so a vote never lowers p_ai
PAUSE_RATE_TTS = 5.0         # at or below -> score 1.0
PAUSE_MIN_SPAN_S = 15.0      # fewer seconds of speech -> abstain (a 10 s live tick holds too few pauses to estimate a rate)
SCRIPT_WEIGHTS = {
    "llm_isms": 1.2,
    "disfluency": 1.0,
    "sentence_uniformity": 0.6,
    "contraction_rate": 0.5,
}
# how much of p_ai comes from acoustic vs script when both present.
# 0.6 -> 0.8 (2026-11-07.2): in the paired wild set the script tells are identical across classes (same text read by human
# and AI), so they only add a constant. Real undisclosed-agent calls still carry script signal, so this stays well below 1.
ACOUSTIC_SHARE = 0.8

INTENT_WEIGHTS = {
    "urgency": 0.8,
    "payment_rails": 1.5,
    "impersonation": 1.0,
    "credential_ask": 1.3,
    "secrecy": 1.0,
    "emergency": 0.9,
    "authority_threat": 1.0,
}

# --- decision thresholds ---
P_AI_THRESHOLD = 0.60        # >= → AI tier
P_SCAM_THRESHOLD = 0.55      # >= → Scam tier (overrides AI/Human)
UNSURE_BAND = 0.12           # |p_ai - threshold| < band and no strong intent → "unsure"
MIN_CONFIDENCE = 0.60        # below → tier "unsure"

# --- acoustic feature calibration (tuned on synthetic fixtures; re-tune on redteam clips) ---
MIN_AUDIO_SECONDS = 4.0
BREATH_MIN_SECONDS = 5.0
BAND_LIMIT_DB = -37.0        # 5-7.5 kHz vs 1-4 kHz level (dB) below this → band_limited (was: >4 kHz < 2% of total, fired on 71% of clean clips)
PAUSE_CV_HUMAN = 0.55        # coefficient of variation of pause lengths; humans are messy (> this)
PAUSE_CV_TTS = 0.25          # TTS is metronomic (< this)
F0_CV_HUMAN = 0.14           # relative F0 variability within voiced regions
F0_CV_TTS = 0.06
NOISE_FLOOR_DB_HUMAN = -55   # real rooms/lines are noisier than this
NOISE_FLOOR_DB_TTS = -70     # digital silence
