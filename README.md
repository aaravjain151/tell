# DoubleSpeak

An **on-device scam-call detector for older people**. It checks a phone call,
spots AI-cloned (fake) voices and scam-style talk, warns the user in big plain
language, and **never sends any data anywhere**.

## Privacy promise (hard rules)

- **100% local.** No network calls at runtime: no APIs, telemetry, analytics,
  CDNs or cloud services. `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are
  enforced in code (see `doublespeak/offline_guard.py`). Streamlit usage stats
  are disabled in `.streamlit/config.toml`.
- The **only** allowed connection is to **Ollama on `localhost:11434`**.
- **Raw audio and transcripts are never written to disk.** They are processed
  in memory and dropped.
- The alert history is encrypted with **AES-256-GCM** (`cryptography`), a fresh
  96-bit nonce per record; the key lives in the **OS keychain** via `keyring`
  and is never written to disk. Records store only timestamp, level, reasons.
- No user accounts, no contact uploads.

## How it works

```
audio clip (in memory, 16 kHz mono, peak-normalised)
   -> pellav2 voice check    rolling 4 s / 2 s windows, skip silence
   -> faster-whisper (VAD)   speech -> text, no hallucinations
   -> Ollama llama3.2:3b     scam score (JSON, temp 0) + regex safety net
   -> fuse: 0.4*voice + 0.6*scam  ->  High / Medium / Low
```

| Module | Job |
| --- | --- |
| `doublespeak/offline_guard.py` | Forces offline ML operation on import |
| `doublespeak/config.py` | Constants, paths, model + rule settings |
| `doublespeak/detector.py` | The full detection pipeline (entry point) |
| `doublespeak/deepfake.py` | pellav2 preprocessing + model loader |
| `doublespeak/transcribe.py` | faster-whisper speech-to-text |
| `doublespeak/secure_store.py` | AES-256-GCM encrypted alert history |
| `doublespeak/net_monitor.py` | Outbound-connection counter + panel |
| `doublespeak/audio.py` | In-memory mic capture helpers |
| `app.py` | Streamlit demo UI (large fonts, plain language) |
| `download_models.py` | One-time online model download |
| `run_pipeline_tests.py` | Batch scorer over `test_audio/` |

The detection pipeline is specified under
`.kiro/specs/detection-pipeline/` (requirements, design, tasks).

## Setup

Requires **Python 3.11**.

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. One-time, online: download the models into ./models and local caches
python download_models.py

# 3. Install Ollama (https://ollama.com) and pull the model
ollama pull llama3.2:3b
```

After step 2, everything the app needs is local. The app itself enforces
offline mode, so it will not reach the internet even if asked.

## Run

```bash
streamlit run app.py
```

- **Record now** or **Upload a file** to check a call.
- A full-width alert (red / amber / green) with big text and plain reasons.
- A "call your contact on their real number" button and a per-window fake-voice
  chart.
- An always-visible network-proof panel.

## Test

```bash
# Unit tests (no models needed): crypto store + pipeline logic
pytest tests/

# Full pipeline over your own clips (models + Ollama recommended)
python run_pipeline_tests.py
```

## Notes

- `download_models.py` is the *only* part of the project that uses the network,
  and only at install time. The runtime app never imports it.
- The deepfake detector and preprocessing are ported from the model author's
  reference `pellav2_infer.py`
  ([model card](https://huggingface.co/Sadanie/pellav2-audio-deepfake-detector)),
  adapted to run on in-memory audio from local weights.
  Content was rephrased for compliance with licensing restrictions.
