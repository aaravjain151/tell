# Detection Pipeline - Requirements

## Introduction

DoubleSpeak is a 100% on-device scam-call detector for older people. This spec
covers the end-to-end **detection pipeline** (`detector.py`) and its supporting
modules: an encrypted alert store (`secure_store.py`), a network-proof monitor
(`net_monitor.py`), a demo UI (`app.py`), and the model/test tooling
(`download_models.py`, `run_pipeline_tests.py`).

The pipeline takes an audio clip, decides whether the voice is AI-cloned and
whether the words sound like a scam, fuses those into a single risk level, and
returns a plain-language result. Nothing leaves the machine except a local call
to Ollama on `localhost:11434`.

### Hard rules (must never be broken)

- 100% local. No network at runtime except Ollama on `localhost:11434`.
  `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are enforced in code.
- Raw audio and transcripts are never written to disk. Processed in memory,
  then dropped.
- Stored data (alert history) is encrypted with AES-256-GCM via `cryptography`;
  the key lives in the OS keychain via `keyring` and is never written to disk.
- Stored records contain only timestamp, risk level, and reasons. Never audio
  or transcript text.
- No user accounts, no contact uploads.

---

## Requirements

### Requirement 1: Audio loading

**User story:** As the pipeline, I want a single way to load any audio file so
that every downstream model receives consistent input.

#### Acceptance criteria

1. WHEN `load_audio(path)` is called THEN the system SHALL return a 16 kHz,
   mono, float32 NumPy array.
2. WHEN the source audio is multi-channel THEN the system SHALL downmix to mono.
3. WHEN the source sample rate differs from 16 kHz THEN the system SHALL
   resample to 16 kHz.
4. WHEN the loaded signal has a non-zero peak THEN the system SHALL
   peak-normalise it so the maximum absolute sample is 1.0.
5. WHEN the signal is silent (peak is zero) THEN the system SHALL return it
   unchanged rather than divide by zero.

### Requirement 2: Voice (deepfake) check with pellav2

**User story:** As an older user, I want to know if the caller's voice is an AI
copy so that I can be suspicious of impersonation.

#### Acceptance criteria

1. WHEN scoring a clip THEN the system SHALL follow the pellav2 model card and
   its reference inference script exactly for preprocessing (DC removal, 20 Hz
   high-pass, centre-crop to 4 seconds, loudness normalisation to -23 LUFS,
   pad to 4 seconds), scoring a 4-second centre crop.
2. WHEN a clip is longer than 4 seconds THEN the system SHALL score rolling
   4-second windows with 2-second hops.
3. WHEN a window is silent (below an energy threshold) THEN the system SHALL
   skip it and exclude it from the mean.
4. WHEN scoring completes THEN the system SHALL return the mean fake
   probability across scored windows AND the list of per-window scores.
5. WHEN no window is loud enough to score THEN the system SHALL return a mean
   of 0.0 and an empty per-window list.

### Requirement 3: Transcription with faster-whisper

**User story:** As the scam checker, I want an accurate transcript so that I can
judge the words spoken, without hallucinated text during silence.

#### Acceptance criteria

1. WHEN transcribing THEN the system SHALL use faster-whisper (base, int8, CPU)
   with `vad_filter=True` to suppress hallucinations on silence.
2. WHEN transcription completes THEN the system SHALL return the joined
   transcript text.
3. WHEN audio contains no speech THEN the system SHALL return an empty or
   near-empty transcript without inventing content.

### Requirement 4: Scam-talk check with Ollama and a regex fallback

**User story:** As an older user, I want the words checked for scam tactics so
that I am warned even when the voice sounds real.

#### Acceptance criteria

1. WHEN a transcript is available THEN the system SHALL send it to Ollama
   `llama3.2:3b` on `localhost:11434` with `format="json"` and `temperature=0`.
2. WHEN the model replies THEN the system SHALL parse a JSON object of the form
   `{"risk": 0-100, "reasons": [string, ...]}` and clamp risk to 0-100.
3. WHEN judging scam risk THEN the system (LLM prompt and regex rules) SHALL
   look for urgency, secrecy, emergencies (arrest, accident, kidnapping),
   and requests for money, gift cards, crypto, wire transfers, codes or PINs.
4. WHEN Ollama is unavailable or returns unparsable output THEN the system
   SHALL fall back to a regex rule engine that produces the same
   `{"risk", "reasons"}` shape.
5. WHEN the regex rules score higher than the LLM THEN the system SHALL use the
   regex result as a safety net (take the higher risk and merge reasons).

### Requirement 5: Risk fusion and levels

**User story:** As an older user, I want one clear risk level so that I know
whether to worry.

#### Acceptance criteria

1. WHEN both scores are available THEN the system SHALL compute
   `risk = 0.4*voice + 0.6*scam`, where voice and scam are each 0.0-1.0.
2. WHEN `voice > 0.7` AND `scam > 0.5` THEN the system SHALL raise the fused
   risk to at least 0.9.
3. WHEN `risk >= 0.65` THEN the level SHALL be "High".
4. WHEN `0.35 <= risk < 0.65` THEN the level SHALL be "Medium".
5. WHEN `risk < 0.35` THEN the level SHALL be "Low".

### Requirement 6: Pipeline result and caching

**User story:** As the UI, I want a single structured result and fast repeat
runs so that the demo feels responsive.

#### Acceptance criteria

1. WHEN the pipeline finishes THEN it SHALL return a dataclass containing: fused
   risk (0.0-1.0), level, voice score, scam score, plain-language reasons
   (list of strings), per-window voice scores, and the transcript.
2. WHEN models are needed THEN the system SHALL load each model (whisper,
   pellav2) exactly once and reuse the cached instance across calls.
3. WHEN the pipeline returns THEN the audio array and transcript SHALL go out of
   scope and SHALL NOT be written to disk by the pipeline.

### Requirement 7: Encrypted alert history (`secure_store.py`)

**User story:** As an older user, I want past warnings saved privately so that a
caregiver can review them without exposing my calls.

#### Acceptance criteria

1. WHEN a record is saved THEN the system SHALL encrypt it with AES-256-GCM via
   the `cryptography` library using a fresh random 96-bit nonce per record.
2. WHEN a key is needed THEN the system SHALL generate it once and store it in
   the OS keychain via `keyring`, and SHALL NOT write the key to disk.
3. WHEN saving THEN each record SHALL contain only timestamp, risk level, and
   reasons. It SHALL NOT contain audio or transcript text.
4. The module SHALL expose `save_alert()`, `load_alerts()`, and `wipe_all()`.
5. WHEN the on-disk file is read without the key THEN its contents SHALL be
   unintelligible ciphertext (verified by tests).

### Requirement 8: Network-proof monitor (`net_monitor.py` + panel)

**User story:** As an older user, I want visible proof that my call is not sent
anywhere so that I can trust the app.

#### Acceptance criteria

1. WHEN inspecting connections THEN the system SHALL use
   `psutil.net_connections` scoped to this app's process.
2. WHEN a remote address is loopback (`127.0.0.1`, `::1`) THEN the system SHALL
   ignore it.
3. WHEN there are no outside connections THEN the panel SHALL show a large green
   "0 outside connections".
4. WHEN any non-loopback connection appears THEN the panel SHALL show red with
   the remote address(es).
5. WHEN the panel is displayed THEN it SHALL refresh roughly every 2 seconds and
   be visible at all times in the UI.
6. Streamlit usage statistics SHALL be disabled via `.streamlit/config.toml`.

### Requirement 9: Demo UI (`app.py`)

**User story:** As an older user, I want a simple, large, high-contrast screen
so that I can understand the result at a glance.

#### Acceptance criteria

1. WHEN using the app THEN the user SHALL be able to upload a file OR record
   with `st.audio_input`, then run the pipeline.
2. WHEN a result is shown THEN a full-width alert SHALL be red for High, amber
   for Medium, and green for Low, with big text such as "This may be a scam".
3. WHEN a result is shown THEN plain-language reasons SHALL appear as a short
   list, with no jargon.
4. WHEN a result is shown THEN a "Call [contact] on their real number" button
   SHALL display a saved contact's real number (display only for the demo).
5. WHEN a result is shown THEN a chart of per-window voice scores SHALL be
   displayed.
6. WHEN the app is open THEN the network-proof panel SHALL always be visible.
7. The UI SHALL use large fonts and high contrast throughout.

### Requirement 10: Model download and full-pipeline test tooling

**User story:** As a developer, I want to prepare models online once and then
check scores across many clips so that I can tune thresholds.

#### Acceptance criteria

1. WHEN `download_models.py` runs with internet THEN it SHALL download pellav2
   and the Whisper model into the local project, and the README SHALL document
   `ollama pull llama3.2:3b`.
2. WHEN the test script runs THEN it SHALL process every file in `test_audio/`
   (real and cloned, scam and normal) and print a table of voice score, scam
   score, and level per file so the scores can be inspected separately.
