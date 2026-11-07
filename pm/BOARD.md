# BOARD

## pm
### NOW
- [T-001] ~~Confirm name~~ done: Doublespeak (D-009) — human
- [T-002] Create private GitHub repo + push; share with team — human
- [T-003] Write 90-second demo script: human vs Gradium clone, live, bytes-out meter visible — human
### NEXT
- [T-004] Decide v2 call architecture (Android dialer vs iOS screener number) — claude
### LATER
- [T-005] Recording-consent review before any call-recording feature — human

## backend
### NOW
- [T-010] Pick + verify an open anti-spoof checkpoint (HF_SPOOF_MODEL); measure on 6 Gradium clips + 6 human clips through Opus 8 kHz — claude
- [T-011] Install faster-whisper + Ollama 3B; confirm `transcript_source=local_whisper` and `provider=ollama` in /analyze output — human
- [T-012] `make redteam` with a cloned teammate voice; held-out eval table (clean / opus-8k / replayed), FPR at 90% TPR; re-tune thresholds — claude
### NEXT
- [T-013] AudioSeal ONNX detector as a "cooperative AI" voter (synath/audioseal-onnx, MIT) — codex
- [T-014] Logistic head on frozen XLS-R embeddings, retrainable on data/calls in <1 min; export ONNX — claude
- [T-015] Streaming mode: analyze rolling 10 s windows while recording; alert on first red — codex
### LATER
- [T-016] SQLite history (opt-in) + export — codex

## frontend
### NOW
- [T-020] Phone-width pass + light theme check in a real browser — cursor
- [T-021] Show `egress.context` (band-limited, duration) under the gauges — cursor
- [T-022] Load `data/calls/*.wav` + `.txt` pairs as "red-team" samples when API is up — cursor
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
