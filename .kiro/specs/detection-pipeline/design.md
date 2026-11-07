# Detection Pipeline - Design

## Overview

The pipeline is a single module, `doublespeak/detector.py`, exposing one cached
entry point and a result dataclass. It composes three on-device models (pellav2
for voice, faster-whisper for text, Ollama for scam judgement) plus a regex
safety net, and fuses their outputs into one risk level.

Supporting modules:

- `doublespeak/secure_store.py` - AES-256-GCM encrypted alert history.
- `doublespeak/net_monitor.py` - outbound-connection counter + Streamlit panel.
- `app.py` - Streamlit demo UI.
- `download_models.py` - one-time online model fetch.
- `run_pipeline_tests.py` - batch scorer over `test_audio/`.

Offline enforcement (`offline_guard`) and shared constants (`config`) are reused
from the existing package.

```
load_audio(path) ─► float32 16 kHz mono, peak-normalised
      │
      ├─► VoiceChecker (pellav2)  ─► mean fake prob + per-window scores
      ├─► Transcriber (whisper)   ─► transcript text
      │        └─► ScamChecker (Ollama json, temp 0) ─┐
      │                      └─► RegexRules (fallback / safety net)
      │                                   └─► scam risk 0-1 + reasons
      └─► fuse(voice, scam) ─► risk, level ─► PipelineResult(dataclass)
```

## Components

### `load_audio(path) -> np.ndarray`

1. Decode with `librosa.load(path, sr=16000, mono=True)` (handles downmix +
   resample in one call).
2. Peak-normalise: `x / max(|x|)` when the peak is > 0, else return unchanged.
3. Return float32. No file is written.

### VoiceChecker (pellav2)

Reuses the verified `DeepfakeDetector` preprocessing already ported from the
model's reference `pellav2_infer.py` (DC removal, 20 Hz high-pass, 4 s centre
crop, -23 LUFS normalise, pad). The checker adds windowing on top:

- If `len(audio) <= 4 s`: score the single centre crop.
- Else: slide a 4 s window with a 2 s hop. For each window, skip if its RMS
  energy is below `SILENCE_RMS` (silent). Otherwise preprocess + score.
- Return `VoiceResult(mean_probability, per_window=[...])`. Mean is over scored
  (non-silent) windows only; empty list => mean 0.0.

The model (backbone + weights) is loaded once via the existing lazy loader.

### Transcriber (faster-whisper)

Reuses the existing `Transcriber` (base, int8, CPU, `vad_filter=True`). We only
need the joined text here.

### ScamChecker (Ollama + regex safety net)

`scam_risk(transcript) -> ScamResult(risk: float 0-1, reasons: [str])`

1. **LLM path:** POST to `localhost:11434/api/generate` with
   `format="json"`, `temperature=0`, and a prompt instructing the model to
   return `{"risk": 0-100, "reasons": [...]}` and to look for urgency, secrecy,
   emergencies (arrest/accident/kidnapping), money, gift cards, crypto, wire
   transfers, codes/PINs. Parse and clamp risk to 0-100, then scale to 0-1.
2. **Regex path (always computed):** a small rule table of patterns, each with a
   weight and a plain-language reason. Sum matched weights, clamp to 0-1.
3. **Fusion within scam check:** start from the LLM result (or regex if the LLM
   is unavailable/unparsable). If the regex risk is higher, take the regex risk
   and merge its reasons in (safety net). Deduplicate reasons.

Rule table (weights are illustrative, tuned to cross 0.5 on a clear scam):

| Pattern (case-insensitive) | Weight | Reason |
| --- | --- | --- |
| gift ?card / steam card / google play card | 0.6 | Asked you to buy gift cards |
| bitcoin / crypto / wire transfer / western union | 0.55 | Asked for crypto or a wire transfer |
| arrest / warrant / jail / police / lawsuit | 0.5 | Threatened you with arrest or police |
| accident / hospital / kidnap / bail | 0.5 | Claimed an emergency to scare you |
| otp / one time code / pin / password / verification code | 0.6 | Asked for a code, PIN or password |
| social security / ssn / bank account number | 0.55 | Asked for sensitive personal numbers |
| don't tell / keep this secret / between us | 0.4 | Told you to keep it secret |
| act now / right now / immediately / urgent / within the hour | 0.35 | Pressured you to act immediately |
| gift card number / scratch the back | 0.5 | Asked for the gift card number |

### Fusion and levels

```python
risk = 0.4 * voice + 0.6 * scam
if voice > 0.7 and scam > 0.5:
    risk = max(risk, 0.9)
level = "High" if risk >= 0.65 else "Medium" if risk >= 0.35 else "Low"
```

### `PipelineResult` dataclass

```python
@dataclass
class PipelineResult:
    risk: float            # 0.0-1.0 fused
    level: str             # "High" | "Medium" | "Low"
    voice_score: float     # 0.0-1.0 mean fake probability
    scam_score: float      # 0.0-1.0
    reasons: list[str]     # plain language
    per_window_voice: list[float]
    transcript: str
```

### Caching

A module-level `@lru_cache`-style singleton (`get_pipeline()`) holds one
`Pipeline` instance; the whisper and pellav2 models inside it are themselves
lazily loaded once. Streamlit uses `@st.cache_resource` to reach the same
singleton.

## `secure_store.py`

- Key: `AESGCM.generate_key(bit_length=256)` once; stored base64 in the OS
  keychain via `keyring` under a service/username from `config`. Never on disk.
- Record: `{"timestamp", "level", "reasons"}` only. JSON-encoded, then
  `AESGCM(key).encrypt(nonce, plaintext, None)` with a fresh 12-byte (96-bit)
  `os.urandom` nonce. Line format: `base64(nonce):base64(ciphertext)`.
- `save_alert(level, reasons)`, `load_alerts() -> list[AlertRecord]`,
  `wipe_all()` (deletes the file; key left in keychain).
- Tests (in `tests/test_secure_store.py`): save a record, read the raw file
  bytes, assert the plaintext reasons/level strings are absent; assert decrypt
  with the key recovers them; assert decrypt with a wrong key fails.

## `net_monitor.py` + panel

- `count_outbound() -> OutboundReport`: `psutil.Process(pid).net_connections
  (kind="inet")`, keep entries with a remote address whose IP is not in
  `{127.0.0.1, ::1}` (and not empty). Report holds the list + count.
- `render_panel(st)`: large green metric "0 outside connections" when clean;
  red error listing `ip:port` when not. Uses `st.fragment(run_every=2)` so it
  refreshes about every 2 seconds without rerunning the whole app.
- `.streamlit/config.toml`: `[browser] gatherUsageStats = false`.

## `app.py`

- Global CSS for large fonts / high contrast.
- Always-visible net panel (fragment) at the top.
- Input: tabs for `st.audio_input` (record) and `st.file_uploader`.
- On run: decode upload to a temp file only long enough for librosa, delete it,
  keep samples in memory; call `get_pipeline().run(audio)`.
- Alert: full-width colored banner (red/amber/green) with big text.
- Reasons: bulleted plain-language list.
- Contact: button rendering a saved contact's real number (display only).
- Chart: `st.bar_chart` / `st.line_chart` of `per_window_voice`.
- On a High/Medium result, save an alert via `secure_store.save_alert`.

## `download_models.py`

Online-only. Downloads pellav2 (`pellav2_detector.pt` + `config.json`) into
`models/`, pre-caches the w2v-BERT backbone, and downloads the faster-whisper
`base` model into `models/faster-whisper-base`. Prints the `ollama pull
llama3.2:3b` reminder. Does not import the offline-enforcing package.

## `run_pipeline_tests.py`

Iterates `test_audio/*.{wav,mp3,m4a,flac,ogg}`, runs the full pipeline on each,
and prints an aligned table: filename, voice score, scam score, fused risk,
level. Lets us eyeball real-vs-cloned and scam-vs-normal separation.

## Error handling

- `load_audio` on a missing/undecodable file raises a clear `FileNotFoundError`
  / `ValueError` caught by the UI and shown in plain language.
- Ollama unavailable: scam check silently falls back to regex (Requirement 4.4).
- pellav2 weights missing: raise `FileNotFoundError` pointing at
  `download_models.py`.

## Testing strategy

- Unit: `load_audio` normalisation, fusion math and level thresholds, regex rule
  scoring, scam fusion safety-net (regex > LLM), secure_store round-trip +
  ciphertext-unreadable-without-key.
- Integration/manual: `run_pipeline_tests.py` over `test_audio/`.
