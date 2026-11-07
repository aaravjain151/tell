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

## Team · branches
One person, one branch, PR into `main` when `make test` is green. Merge order avoids conflicts: **Sanath → Samarth → Aarav** (Aarav's tuning needs both voters in). Aarav owns `scorer.py` and `thresholds.py`; nobody else touches them.

| Branch | Owner | Owns | Done when |
|---|---|---|---|
| `feat/antispoof` | @sanathNU | `tell/signals/neural.py`, neural tests, T-010, T-013 | HF voter picked + logged id2label, < 5 s / 10 s clip on CPU, AudioSeal "cooperative AI" voter, one skills.md line per voter |
| `feat/local-plumbing` | @samarthsrinivas | `tell/stt.py`, `tell/localhost.py`, `tell/llm.py`, `apps/web/`, T-011, T-018, T-020..T-022 | audio-only `/analyze` → `transcript_source == "local_voicestudio"` (or `local_whisper`), `cost.provider == "ollama"` + both llm_* tells, < 6 s CPU, counter reads 0 with Wi-Fi off |
| `feat/redteam-eval` | @aaravjain151 | `tools/redteam/`, `eval/`, `thresholds.py`, T-012, T-017, pitch | four generator families held out, `pm/AUDITS.md` table, FPR@90%TPR <= 0.15 on opus8k, demo script + Devpost |

Cross-branch asks: `python3 scripts/pm.py msg <from> <to> "..."`. Log: `python3 scripts/pm.py log backend "..."`.

## backend
### NOW
- [T-010] Anti-spoof checkpoint: picked garystafford/wav2vec2-deepfake-voice-detector (HF_SPOOF_MODEL). OPEN: measure per engine (Gradium / VoiceStudio held-out; ElevenLabs is in-domain) + 12 human clips, clean and Opus 8 kHz — claude → @sanathNU · branch feat/antispoof
- [T-011] faster-whisper + Ollama installed and verified on a synthetic clip. OPEN: confirm `transcript_source=local_whisper` on a real 10 s mic clip from the web record button — human → @samarthsrinivas · branch feat/local-plumbing
- [T-012] Record the 6 scripts read by 2 humans on phone mics (`human__<speaker>__<script>.wav`), run degrade.sh + `run_eval.py --wild data/calls`, re-tune thresholds.py from real numbers (bump THRESHOLDS_VERSION, before/after in commit body) — claude → @aaravjain151 · branch feat/redteam-eval
- [T-017] Generate attacker calls with ALL engines: `make redteam ARGS="--engine all"` (Gradium, ElevenLabs, VoiceStudio local); clone one consenting teammate in Gradium/ElevenLabs/VoiceStudio and pass the voice ids; install VoiceStudio (github.com/debpalash/voicestudio, AGPL — HTTP only, no code copied) and keep it running on :3900 — claude → @aaravjain151 · branch feat/redteam-eval
- [T-018] Qwen as the local scam-talk judge: pull qwen2.5:3b / qwen3:4b, run `eval/llm_bench.py`, adopt the winner via OLLAMA_MODEL if it beats llama3.2:3b on scam recall at p95 < 3 s — claude → @samarthsrinivas · branch feat/local-plumbing
### NEXT
- [T-013] AudioSeal ONNX detector as a "cooperative AI" voter (synath/audioseal-onnx, MIT); positive = disclosed/cooperative generator, low weight, never a scam flag — codex → @sanathNU · branch feat/antispoof
- [T-014] Logistic head on frozen XLS-R embeddings, retrainable on data/calls in <1 min; export ONNX — claude
- [T-015] Streaming mode: analyze rolling 10 s windows while recording; alert on first red — codex
### LATER
- [T-016] SQLite history (opt-in) + export — codex

## frontend
### NOW
- [T-020] Phone-width pass + light theme check in a real browser — cursor → @samarthsrinivas · branch feat/local-plumbing
- [T-021] DONE: `egress.context` line under the gauges; samples via apps/web/build_samples.py — claude · feat/local-plumbing
- [T-022] Load `data/calls/*.wav` + `.txt` pairs as "red-team" samples when API is up — cursor → @samarthsrinivas · branch feat/local-plumbing
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
