"""Plain-English meaning of every interpretable tell: (what it measures, a HIGH value in words, a LOW value in words).
At export the phrase for the AI-pushing side is picked from the sign of the learned coefficient (meaning_json)."""

MEANING = {
    "f0_std_st": ("spread of the pitch (semitones)", "wide pitch spread", "narrow pitch spread"),
    "f0_range_st": ("pitch range, 5th to 95th percentile (semitones)", "wide pitch range", "narrow pitch range"),
    "f0_rate_st_s": ("how fast the pitch moves (semitones/s)", "fast-moving pitch", "slow-moving pitch"),
    "f0_micro_st": ("tiny pitch wobble left after smoothing (semitones)", "pitch micro-wobble", "almost no pitch micro-wobble"),
    "jitter_pct": ("period-to-period pitch change (%)", "high pitch jitter", "very low pitch jitter"),
    "shimmer_db": ("frame-to-frame loudness change in voiced speech (dB)", "loudness flutter", "very steady loudness"),
    "f0_energy_corr": ("how tightly pitch follows loudness", "pitch tied to loudness", "pitch independent of loudness"),
    "hnr_db": ("harmonics-to-noise ratio (dB)", "noise-free voicing", "breathy, noisy voicing"),
    "cpp_db": ("cepstral peak prominence (dB): how regular the voicing is", "voice too regular and clean", "rough, irregular voicing"),
    "harm_valley_db": ("depth of the valleys between harmonics (dB)", "clean gaps between harmonics", "noise between harmonics"),
    "harm_if_dev": ("how far harmonics stray from exact multiples of the pitch", "harmonics stray from the pitch", "harmonics exactly in tune"),
    "group_delay_ms": ("spread of phase group delay across 300-3400 Hz (ms)", "scattered phase", "orderly phase"),
    "env_roughness_db": ("roughness of the loudness envelope inside phrases (dB)", "jumpy loudness envelope", "smooth loudness envelope"),
    "mod_4_16": ("share of loudness modulation at syllable rate (4-16 Hz)", "strong, even syllable beat", "weak syllable beat"),
    "spectral_flux": ("how fast the spectrum changes frame to frame", "fast spectral change", "slow spectral change"),
    "spectral_tilt_db": ("energy 1-3.4 kHz relative to 0.1-1 kHz (dB)", "bright voice", "dark voice"),
    "lowmid_balance_db": ("energy 500-1000 Hz relative to 100-500 Hz (dB)", "strong low-mids", "weak low-mids"),
    "speech_flatness": ("spectral flatness of speech frames", "noise-like speech spectrum", "tonal speech spectrum"),
    "pause_share": ("share of the window that is pause", "many pauses", "few pauses"),
    "max_gap_ms": ("longest pause in the window (ms)", "long pauses", "short pauses"),
    "pause_depth_db": ("how far pauses sit below speech (dB, negative)", "shallow pauses (room tone)", "very deep, silent pauses"),
    "pause_flatness": ("noise texture inside pauses (1 = hiss)", "hiss-like pause noise", "structured pause noise"),
    "pause_wobble_db": ("level variation inside pauses (dB)", "pause level jumps (rendered silence)", "steady room tone in pauses"),
    "breath_rate": ("breath-like noises before phrases per 10 s of speech", "breath noises before phrases", "no breath noises"),
    "noise_floor_dbfs": ("background level (dBFS); channel", "loud background", "very quiet background"),
    "snr_db": ("speech-to-background ratio (dB); channel", "very clean recording", "noisy recording"),
    "hi_band_rel_db": ("5-7.5 kHz relative to 1-4 kHz (dB); channel", "bright top octave", "dull top octave"),
    "digital_zero_frac": ("share of exactly-zero samples; channel", "exact digital silence", "no digital silence"),
}


def meaning_json(coef_by_feature: dict[str, float]) -> dict:
    """{feature: {"what", "ai", "human"}}: "ai" is the words for the side of the feature that pushes toward AI."""
    out = {}
    for k, c in coef_by_feature.items():
        what, hi, lo = MEANING[k]
        out[k] = {"what": what, "ai": hi if c > 0 else lo, "human": lo if c > 0 else hi}
    return out
