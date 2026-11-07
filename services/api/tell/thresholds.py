"""Single home for every weight and threshold. Bump THRESHOLDS_VERSION when you change anything.

Scores are in [0, 1]. Acoustic/script scores point *toward AI*; intent scores point *toward scam*.
"""

THRESHOLDS_VERSION = "2026-11-07.1"

# --- fusion weights (normalised at runtime over the signals that actually ran) ---
ACOUSTIC_WEIGHTS = {
    "pause_regularity": 1.0,
    "breath_proxy": 1.2,
    "pitch_stability": 0.9,
    "noise_floor": 0.8,
    "high_band": 0.5,  # down-weighted automatically when band_limited
}
SCRIPT_WEIGHTS = {
    "llm_isms": 1.2,
    "disfluency": 1.0,
    "sentence_uniformity": 0.6,
    "contraction_rate": 0.5,
}
# how much of p_ai comes from acoustic vs script when both present
ACOUSTIC_SHARE = 0.6

INTENT_WEIGHTS = {
    "urgency": 0.8,
    "payment_rails": 1.5,
    "impersonation": 1.0,
    "credential_ask": 1.3,
    "secrecy": 1.0,
}

# --- decision thresholds ---
P_AI_THRESHOLD = 0.60        # >= → AI tier
P_SCAM_THRESHOLD = 0.55      # >= → Scam tier (overrides AI/Human)
UNSURE_BAND = 0.12           # |p_ai - threshold| < band and no strong intent → "unsure"
MIN_CONFIDENCE = 0.60        # below → tier "unsure"

# --- acoustic feature calibration (tuned on synthetic fixtures; re-tune on redteam clips) ---
MIN_AUDIO_SECONDS = 4.0
BREATH_MIN_SECONDS = 5.0
BAND_LIMIT_RATIO = 0.02      # energy above 4 kHz / total < this → band_limited
PAUSE_CV_HUMAN = 0.55        # coefficient of variation of pause lengths; humans are messy (> this)
PAUSE_CV_TTS = 0.25          # TTS is metronomic (< this)
F0_CV_HUMAN = 0.14           # relative F0 variability within voiced regions
F0_CV_TTS = 0.06
NOISE_FLOOR_DB_HUMAN = -55   # real rooms/lines are noisier than this
NOISE_FLOOR_DB_TTS = -70     # digital silence
