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
apps/web/build_samples.py  regenerates the 4 inline demo verdicts (deterministic: stub LLM, no heavy models) — run after any thresholds change; tests/test_web_samples.py guards it
../../tools/redteam/    degrade.sh (opus-8k) · make_calls.py — Gradium attacker clips from scripts/*.txt
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
`make redteam ARGS="--engine all"` (or `python3 tools/redteam/make_calls.py --engine gradium|elevenlabs|voicestudio|qwen3tts|all [--voice <id|ref.wav>] [--voice-text '...'] [--max 6]`; `--max` is per engine) → `data/calls/<engine>/<script>.wav` + `.txt` (gitignored); humans go in `data/calls/human/**`. `--engine all` skips engines with no key / app not running and says why. Engines live in `tools/redteam/engines.py` (stdlib HTTP, injectable opener, tested without network). Clone a teammate in Gradium Studio, pass its voice id, and the demo is "fresh clone vs Tell". Record a *human* teammate reading the same scripts for the paired baseline.

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
- 2026-11-07 · backend · Ollama llama3.2:3b via /api/generate: 0.5-0.7 s warm per ~45-word script, 2.5 s cold; whole `/analyze` (whisper + wav2vec2 + ollama) 1.3 s warm, 7.7 s on the first request after boot → `main.warm_up()` preloads all three at startup (TELL_WARMUP=0 disables). Transcript is capped to the last 120 words (`TELL_LLM_MAX_WORDS`) and the HTTP timeout is 10 s (`OLLAMA_TIMEOUT_S`); on failure `llm.py` returns no tells and `cost.error`, never an exception.
- 2026-11-07 · backend · The 3B model hallucinates `disclosed_ai: true` on an undisclosed sales script and answers `assistant_style` 1.0 on both sales scripts. That is why disclosure stays in code (`signals/intent.DISCLOSURE`; the LLM `ai_disclosure` tell is applicable=False, weight 0). Scores from the 3B are clamped and non-numeric values fall back to defaults (`llm._score`).
- 2026-11-07 · backend · Background processes started with `&` die when the Bash call ends in this harness; start `make api` with run_in_background and poll /health.
- 2026-11-07 · web · Inline samples come from `./.venv/bin/python apps/web/build_samples.py` (refuses to write if a tier changes; `--check` to dry-run). It forces LLM_PROVIDER=stub and unsets HF/ONNX models so the file:// demo is identical on every laptop; live API verdicts will differ (neural + Ollama on). The page's context line reads `egress.context` + `cost.local`; `transcript_source` is absent when the user supplied the transcript.
- 2026-11-07 · backend · Red-team engines: Gradium (CLI, credits), ElevenLabs (`/v1/text-to-speech/{voice}?output_format=pcm_16000`, header `xi-api-key`, raw PCM wrapped to WAV), VoiceStudio (local app, OpenAI-style `POST :3900/v1/audio/speech`, `response_format: wav`, loopback needs no auth, first call downloads ~2.3 GB model). VoiceStudio is AGPL-3.0: call it over HTTP, never copy its code into this repo.
- 2026-11-07 · backend · ElevenLabs is IN-DOMAIN for `garystafford/wav2vec2-deepfake-voice-detector` (its card lists ElevenLabs in the training set), so a high catch rate on `ai__elevenlabs__*` proves little; judge generalisation on `ai__gradium__*` and `ai__voicestudio__*`. `run_eval.py --wild` tags this per engine.
- 2026-11-07 · backend · Voice clones are of consenting teammates only; paid engines get script text only (never caller audio) and live under tools/, outside the analysis package (`test_redteam_engines.py` greps `tell/` for TTS service names).
- 2026-11-07 · backend · T-018 local scam-talk judge bench (`eval/llm_bench.py`, 32 golden transcripts, full pipeline): llama3.2:3b tier acc 0.78 / p95 665 ms; qwen2.5:3b 1.00 / 911 ms; qwen3:4b 1.00 / 2192 ms (needs `think:false`, set automatically). All: scam recall 1.00, framing false-positive 0.00. llama's drop comes from overconfident `assistant_style` on human and sales scripts. Default is now qwen2.5:3b. Caveat: the golden set is what the regex signals were built against, so 1.00 means no regression, not generalization.
- 2026-11-07 · backend · Wild-eval layout is `data/calls/<engine>/<script>.wav`, `data/calls/human/<speaker>/<script>.wav`, and `*.opus8k.wav` beside each (recursive `degrade.sh`; ffmpeg needs `-nostdin` inside a `while read` loop or it eats the file list). `run_eval.py --wild DIR` prints per condition AUC / EER / FPR@90%TPR, then per engine caught-count, AUC and a leave-one-engine-out row (threshold from the OTHER engines' 90% TPR, applied to the held-out engine; humans are one pool). The old flat glob silently skipped engine folders.
- 2026-11-07 · backend · Qwen3-TTS (`pip install -U qwen-tts`, Apache-2.0): `Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-0.6B-Base", device_map="mps"|"cpu", dtype=...)` then `generate_voice_clone(text, language, ref_audio, ref_text)` -> `(wavs, sr)`; sr is 24 kHz, not 16 kHz (eval resamples). `ref_text` must be the exact words in the reference clip. Engine lives in `tools/redteam/engines.py`; tested with a fake model, never downloaded in tests.
- 2026-11-07 · backend · `run_eval --wild` compares raw p_ai to the threshold; a clip at 0.5999 prints as 0.60 but is below 0.6. MISS/FALSE ALARM lines now print 3 decimals.
