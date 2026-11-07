# BOARD

## pm
### NOW
- [T-001] Confirm name (Tell vs alternates in final message) — human
- [T-002] Create private GitHub repo + push; share with team — human
- [T-003] Write 90-second demo script: human vs Gradium clone, live, bytes-out meter visible — human
### NEXT
- [T-004] Decide v2 call architecture (Android dialer vs iOS screener number) — claude
### LATER
- [T-005] Recording-consent review before any call-recording feature — human

## Branch owners (one person, one branch, PR into main; @aaravjain151 merges)
| Branch | Owner | Task |
|---|---|---|
| backend/stt-whisper | @aaravjain151 | T-011 real mic test |
| web/real-samples | @aaravjain151 | T-020..T-022 browser pass |
| backend/redteam-eval | @sanathNU | T-012 humans + threshold re-tune |
| backend/redteam-engines | @sanathNU | T-017 Gradium + ElevenLabs + VoiceStudio clips |
| backend/anti-spoof | @samarthsrinivas | T-010 per-engine measurement |
| backend/ollama-scam-talk, backend/qwen-scam-talk | @samarthsrinivas | T-018 Qwen vs Llama |

## backend
### NOW
- [T-010] Anti-spoof checkpoint: picked garystafford/wav2vec2-deepfake-voice-detector (HF_SPOOF_MODEL). OPEN: measure per engine (Gradium / VoiceStudio held-out; ElevenLabs is in-domain) + 12 human clips, clean and Opus 8 kHz — claude → @samarthsrinivas · branch backend/anti-spoof
- [T-011] faster-whisper + Ollama installed and verified on a synthetic clip. OPEN: confirm `transcript_source=local_whisper` on a real 10 s mic clip from the web record button — human → @aaravjain151 · branch backend/stt-whisper
- [T-012] Record the 6 scripts read by 2 humans on phone mics (`human__<speaker>__<script>.wav`), run degrade.sh + `run_eval.py --wild data/calls`, re-tune thresholds.py from real numbers (bump THRESHOLDS_VERSION, before/after in commit body) — claude → @sanathNU · branch backend/redteam-eval
- [T-017] Generate attacker calls with ALL engines: `make redteam ARGS="--engine all"` (Gradium, ElevenLabs, VoiceStudio local); clone one consenting teammate in Gradium/ElevenLabs/VoiceStudio and pass the voice ids; install VoiceStudio (github.com/debpalash/voicestudio, AGPL — HTTP only, no code copied) and keep it running on :3900 — claude → @sanathNU · branch backend/redteam-engines
- [T-018] Qwen as the local scam-talk judge: pull qwen2.5:3b / qwen3:4b, run `eval/llm_bench.py`, adopt the winner via OLLAMA_MODEL if it beats llama3.2:3b on scam recall at p95 < 3 s — claude → @samarthsrinivas · branches backend/ollama-scam-talk, backend/qwen-scam-talk
### NEXT
- [T-013] AudioSeal ONNX detector as a "cooperative AI" voter (synath/audioseal-onnx, MIT) — codex
- [T-014] Logistic head on frozen XLS-R embeddings, retrainable on data/calls in <1 min; export ONNX — claude
- [T-015] Streaming mode: analyze rolling 10 s windows while recording; alert on first red — codex
### LATER
- [T-016] SQLite history (opt-in) + export — codex

## frontend
### NOW
- [T-020] Phone-width pass + light theme check in a real browser — cursor → @aaravjain151 · branch web/real-samples
- [T-021] DONE: `egress.context` line under the gauges; samples via apps/web/build_samples.py — claude · web/real-samples
- [T-022] Load `data/calls/*.wav` + `.txt` pairs as "red-team" samples when API is up — cursor → @aaravjain151 · branch web/real-samples
### NEXT
- [T-023] Live "listening" mode: analyze every 10 s while recording — codex
### LATER
- [T-024] Native shell (Android dialer) — claude

## marketing
### NOW
- [T-030] Pitch deck 6 slides from PRODUCT.md + hooks.md — claude app
### NEXT
- [T-031] Waitlist page + r/scams post after the hackathon — claude app
### LATER
- [T-032] Short-video scripts filmed with real parents (consent) — human

## feedback
### NOW
- [T-040] Interview 3 judges/attendees with `feedback/interview.md` during demo hour — human
### NEXT
- [T-041] 10 parent interviews (recruit via team families) — human
### LATER
- [T-042] Weekly metrics table once real calls exist — human
