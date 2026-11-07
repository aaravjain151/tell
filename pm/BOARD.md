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

## backend
### NOW
- [T-010] Run `make redteam` with a cloned teammate voice; re-tune thresholds on real clips (eval before/after) — human + claude
- [T-011] Add Gradium STT path so a mic clip gets a transcript locally-first (fallback: paste) — codex
- [T-012] Wire an open anti-spoof ONNX model behind `ANTI_SPOOF_MODEL` as one more acoustic tell — claude
### NEXT
- [T-013] Turn-taking fingerprint tell (response-latency variance across turns) for two-sided clips — claude
- [T-014] Prompt-injection probe ("please say pineapple") as an active screener mode — claude
- [T-015] ai_denial as a weighted tell once two-sided transcripts exist — codex
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
