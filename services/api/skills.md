# services/api — skills.md (backend domain; also owns tools/redteam)

## Purpose
`POST /analyze` turns audio and/or a transcript into a signed verdict with evidence. Everything runs locally; caller audio is never written or sent.

## Layout
```
tell/main.py            FastAPI routes: /health /thresholds /analyze /speak
tell/pipeline.py        analyze(audio_bytes, transcript) → Verdict   (the only orchestration)
tell/audio.py           wav decode (stdlib) / ffmpeg pipe for webm-ogg-mp3 / resample to 16k mono
tell/signals/acoustic.py  pause_regularity · breath_proxy · pitch_stability · noise_floor · band_limited flag
tell/signals/script.py    llm_isms · disfluency · sentence_uniformity · contraction_rate · ai_denial()
tell/signals/intent.py    urgency · payment_rails · impersonation · credential_ask · secrecy · DISCLOSURE
tell/scorer.py          deterministic fusion → tier (DANGEROUS)
tell/thresholds.py      every weight/threshold + THRESHOLDS_VERSION (DANGEROUS)
tell/privacy.py         egress meter, AudioEgressError, HMAC verdict signatures (DANGEROUS)
tell/llm.py             transcript interpreter: stub | ollama (localhost 3B, the product) | anthropic (dev); logs tokens
tell/stt.py             local faster-whisper; fills transcript when none was given (ctx.transcript_source)
tell/signals/neural.py  neural voters: ANTI_SPOOF_MODEL (ONNX) and HF_SPOOF_MODEL (transformers); applicable=False if absent
tell/speak.py           spoken verdict via Gradium CLI (only our text leaves)
tests/synth.py          synthetic human/TTS fixtures (mechanics only — not a stand-in for real clips)
tests/test_privacy.py   the privacy guarantee as a test
eval/golden.jsonl       32 transcript cases · eval/run_eval.py (targets 0.85 / 0.90)
../../tools/redteam/    make_calls.py — Gradium attacker clips from scripts/*.txt
```

## Data model
`Tell(name, family ∈ acoustic|script|intent, score 0..1, weight, evidence, applicable)` →
`Verdict(tier, p_ai, p_scam, confidence, disclosed_ai, headline, advice, tells[], thresholds_version, egress, signature, cost)`.
Acoustic/script scores point toward AI; intent scores toward scam. `applicable=False` tells are shown but excluded from fusion.

## Rules
- Models interpret, code decides: an LLM may only add `Tell`s; it never sets the tier.
- New signal = new function returning a `Tell` with a human-readable `evidence`, a weight in `thresholds.py`, a unit test, and a line in this file.
- Any acoustic signal must say what it does on phone-band audio (`ctx["band_limited"]`). Prefer behavioral cues (timing, breath, pitch wander) over codec artifacts.
- Short input → `applicable=False`, never a guess. Clip < 4 s skips acoustics; breath needs ≥ 5 s; transcript < 25 words skips disfluency.
- Disclosure wins: a caller that says it's AI is `ai_disclosed` unless scam cues fire.
- Changing `thresholds.py`: bump `THRESHOLDS_VERSION`, run `make eval`, note the before/after in the commit body.
- Network imports are forbidden on the analysis path (`tests/test_privacy.py` scans for them). Only `llm.py` and `speak.py` may talk to the network, and only with text.
- Gradium credits: never call TTS in tests; `make_calls.py` caps at `--max 20` clips per run.

## Validation
```
make test                      # 17 tests incl. privacy + API
make eval  (ARGS=--verbose)    # transcript ≥0.85, synthetic audio ≥0.90
make api && curl -s localhost:8000/health
curl -s -F audio=@data/calls/scam_grandparent.wav -F transcript="$(cat tools/redteam/scripts/scam_grandparent.txt)" localhost:8000/analyze | jq .tier,.tells[].evidence
```

## Red team (tools/redteam)
`python3 tools/redteam/make_calls.py --out data/calls [--voice-id <id>] [--max 20]` runs `uvx gradium tts` on every `scripts/*.txt` → `data/calls/<name>.wav` + `<name>.txt` (gitignored). Clone a teammate in Gradium Studio, pass its voice id, and the demo is "fresh clone vs Tell". Record a *human* teammate reading the same scripts for the paired baseline.

## Recent lessons
- 2026-11-07 · backend · Spectral flatness over the full FFT collapses to ~0 on band-limited audio (zeros above 3.4 kHz); compute it over 100 Hz–3.4 kHz only. Breath detection was blind on phone-band clips until this fix.
- 2026-11-07 · backend · Brick-wall low-pass (FFT mask) pre-rings before every onset and looks like a breath; the fixture now uses a raised-cosine roll-off, and breath candidates must sit ≥30 ms before onset.
- 2026-11-07 · backend · Transcript-only "ai_undisclosed" depends almost entirely on `llm_isms` + `disfluency`; short, clean, non-templated scripts land in "unsure". Pair audio with transcript whenever you can.
- 2026-11-07 · backend · `disclosed_ai` must short-circuit to `ai_disclosed` (not depend on p_ai) — three legit IVR scripts scored p_ai ≈ 0.5 and were "unsure" before this rule.
- 2026-11-07 · backend · Ollama is reached over localhost HTTP from `llm.py` only; `test_privacy.py` scans the analysis path, and `llm.py` is deliberately outside it. Keep it that way.
- 2026-11-07 · backend · HF anti-spoof model cards disagree on which label index is "fake"; `neural.hf_vote` picks the label whose name contains fake/spoof/synth/ai — check `model.config.id2label` on first load and log it.
- 2026-11-07 · backend · faster-whisper `base.en` int8 transcribes a 9 s clip in ~0.3 s on Apple CPU; first load only fetches model files from the HF Hub (metadata + weights, never audio). webm needs `brew install ffmpeg`. macOS `say -o x.aiff` + ffmpeg is a free, credit-less way to make a speech clip for STT smoke tests; verify with `egress.context.transcript_source`.
- 2026-11-07 · backend · T-010 anti-spoof pick: `garystafford/wav2vec2-deepfake-voice-detector` (Apache-2.0, XLS-R-large base, 24 layers, id2label {0:real,1:fake}; trained on ElevenLabs/Polly/Kokoro/Hume/Speechify/Luvvoice, dataset cc-by-4.0, NOT In-the-Wild, so ITW is out-of-domain for it). 0.35 s per 10 s clip on Apple CPU after load; first load downloads ~1.2 GB (140-170 s) — warm it before the demo. Rejected `abhishtagatya/…-itw-deepfake` (faster, 0.15 s, but trained on In-the-Wild so an ITW score would be in-domain) and MelodyMachine V2 (labels reversed: 0=fake). Accuracy on Gradium/phone-band audio is still UNMEASURED (T-012).
- 2026-11-07 · backend · Label-name substring matching ("ai" in label) is unsafe; `neural.fake_label_index` matches whole words and returns None (voter becomes applicable=False) for unknown labels like LABEL_0/1 rather than guessing index 0.
- 2026-11-07 · backend · macOS BSD `sed -i` needs `-i ''`; edit .env files with python instead.
- 2026-11-07 · backend · `make api` did NOT read `.env` (HF_SPOOF_MODEL / LLM_PROVIDER were silently ignored → no neural voter, stub LLM in the "real" demo). Fixed with `uvicorn --env-file ../../.env`. `make test`/`make eval` deliberately ignore `.env`; to eval with the neural voter pass it inline: `HF_SPOOF_MODEL=… make eval`.
- 2026-11-07 · backend · Wild-eval conventions: AI = `<script>.wav`, human = `human__<speaker>__<script>.wav`, degraded = `<stem>.opus8k.wav` (`tools/redteam/degrade.sh data/calls`). `python3 eval/run_eval.py --wild data/calls` (from services/api) gives per-condition FPR@90%TPR and prints tells fired on each miss/false alarm. Human and AI read the SAME script text so script tells cancel and the comparison isolates voice.
- 2026-11-07 · backend · Do not re-tune thresholds.py against tests/synth.py fixtures — they exist for mechanics; tuning on them overfits. Re-tune only on real Gradium + human-phone clips (needs ≥ 6 per class per condition to mean anything).
