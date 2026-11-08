# Tell

> The product is called **Tell** (D-013; it was briefly "Doublespeak", D-010). This first section describes the early
> Streamlit prototype, whose Python package keeps its old folder name `doublespeak/` at the repo root. The product
> engine is `services/api/tell` (see the second half of this file and `skills.md`).

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

## Sample clips

The app has a third tab, **Sample clips**, for trying the detector without
recording anything yourself. It lists any audio placed under `data/calls/`
grouped by dataset folder, so you can pick a clip and run it through the exact
same on-device pipeline as a live call.

The example datasets are kept on the dedicated `data/sanath-voice-clips` branch
(they are not committed to the code branches, and `data/` is git-ignored). Pull
them into your working copy with:

```bash
git checkout origin/data/sanath-voice-clips -- data/calls
```

That drops clips under `data/calls/` such as:

| Folder | Voice | Use for |
| --- | --- | --- |
| `human/sanath` | real recordings | should score ~0 on fake-voice |
| `gradium`, `gradium_stock` | AI-cloned | fake-voice score should rise |
| `qwen3tts` | AI-generated (TTS) | fake-voice score should rise |

Each folder has matching scenarios (`scam_irs`, `scam_bank_otp`,
`scam_grandparent`, `casual_clone`, `long_appointment`, ...), so you can load the
real and the cloned version of the same script and compare the fake-voice
column. The 8 kHz `*.opus8k.wav` variants are hidden from the picker to keep the
menu short.

### Running fully locally (notes)

- Use **Python 3.11** in a virtual environment; this is a NumPy 1.x stack
  (`torch`, `faster-whisper`, `librosa`). Do not upgrade to NumPy 2 - packages
  that require it (e.g. `pyarrow>=18`) are pinned below that line on purpose.
- In-app recording (the **Record now** tab) needs **Streamlit >= 1.40**
  (`st.audio_input`). On older versions the tab degrades to a message pointing
  at **Upload a file**.
- Ollama is optional. Without it, scam scoring uses the regex safety net, so
  obvious scams are still flagged - they may land at *Medium* rather than *High*
  because the fused risk (`0.4*voice + 0.6*scam`) stays just under the High
  threshold when the voice is a real human (score ~0).

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

---

# Tell

*Every voice has a tell.* A privacy-first detector that classifies the voice on a call as **Human · AI (identified itself) · AI (undisclosed) · Scam pattern**, shows the exact tells that fired, and never sends caller audio off the device.

Built at HACK1984 — targeting the Privacy-First (main) track, Most Startup-able, and the Best Use of Gradium side prize (it stacks with Privacy-First). We used Gradium to clone our own teammates' voices for the red-team attacker clips and to speak the verdict; only our own script text is ever sent to Gradium, never a caller.

## Run it
```
make setup && make test && make eval     # pinned deps · eval ≥ 0.85 / 0.90 · same as CI
make api                                 # http://localhost:8000  (docs at /docs)
make web                                 # http://localhost:5173
```
Optional: `cp .env.example .env`, add `GRADIUM_API_KEY`, then `make redteam` generates attacker clips and the 🔊 button speaks the verdict.

## How it works
See `skills.md` (architecture) and `services/api/skills.md` (signals). Short version: numpy acoustic tells (breath, pauses, pitch wander, noise floor) + script tells (assistant-style phrasing, zero disfluency) + intent tells (urgency, payment rails, impersonation, credential asks, secrecy) → deterministic fusion → signed verdict. Privacy is enforced by `services/api/tests/test_privacy.py`.

## Repo map
`skills.md` is the source of truth. Domains: `apps/` `design/` `services/api/` `tools/redteam/` `marketing/` `feedback/` `pm/`. Tooling: `scripts/pm.py`, `council/ask.py`, `agents/ROUTING.md`.
