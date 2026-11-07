# Tell — root skills.md (source of truth)

Every tool and every human reads this first. Edit *this* file; `CLAUDE.md`, `AGENTS.md` and `.cursor/rules/tell.mdc` are thin pointers.

## 1. Overview
Tell is a privacy-first detector that classifies the voice on a call as **Human · AI (disclosed) · AI (undisclosed) · Scam**, with the specific "tells" that fired, and never sends caller audio off-device. Built at HACK1984 (Privacy-First track + Gradium side prize). Product brief: `pm/PRODUCT.md`. Decisions: `pm/DECISIONS.md`.

Core loop: user feeds a clip or mic → local analysis → verdict card with evidence + "bytes leaving device: 0".

## 2. Stack
| Layer | Choice | Why |
|---|---|---|
| API | Python 3.11+, FastAPI, uvicorn | fast to write, every teammate knows it |
| Signals | numpy only (no librosa/torch in v1) | installs in seconds, runs on any laptop, judge can run it offline |
| Optional LLM | `LLM_PROVIDER=stub` by default; `anthropic` opt-in | tests/eval run with no keys; model interprets, code decides |
| Web | one self-contained `apps/web/index.html` | no build step; works as an Artifact and from `file://` |
| Red team | Gradium CLI (`uvx gradium tts`) | generates fresh synthetic attacker calls; voice-clone a teammate |
| Spoken verdict | Gradium TTS (optional) | only *our* text leaves the device |
| Storage | none in v1 (in-memory). SQLite if v2 needs call history | privacy by not having data |
| Tests | pytest | |

## 3. Architecture
```
 mic / file ──► apps/web/index.html ──POST /analyze──► services/api (localhost)
                                                          │
                     ┌────────────────────────────────────┼─────────────────────────────┐
                     │ signals/acoustic.py (numpy)        │ signals/script.py  (LLM-isms, disfluency)
                     │ pause regularity, breath proxy,    │ signals/intent.py  (urgency, payment rails,
                     │ pitch stability, noise floor,      │   impersonation, credential asks, AI disclosure)
                     │ band-limit flag                    │ llm.py: optional interpreter (stub by default)
                     └────────────────────────────────────┴─────────────────────────────┘
                                                          │
                                               scorer.py (deterministic rules, thresholds.py)
                                                          │
                              {tier, p_ai, p_scam, confidence, tells[], egress, signature}
                                                          │
                                       verdict card  ◄────┘      (+ optional spoken verdict via Gradium)
```
Rule: **models interpret, code decides.** Audio bytes are never written to disk or sent anywhere unless `TELL_DEBUG_SAVE=1`.

## 4. Folder structure
```
apps/web/            frontend (index.html)            → apps/skills.md
design/              tokens.json, build_tokens.py      → design/skills.md
services/api/        FastAPI app, signals, tests, eval → services/api/skills.md
tools/redteam/       Gradium attacker-call generator   → services/api/skills.md (backend domain)
marketing/           positioning, hooks, calendar      → marketing/skills.md
feedback/            interview script, log             → feedback/skills.md
pm/                  PRODUCT, BOARD, DECISIONS, SESSION_LOG, AUDITS, inbox/ → pm/skills.md
agents/ROUTING.md    which tool for which job
council/             multi-model consultant council (ask.py)
scripts/pm.py        session/message/decision/audit CLI
data/calls/          generated clips (gitignored except .gitkeep)
```

## 5. Commands
```
make setup        # venv + pip install -r services/api/requirements.txt
make test         # pytest services/api/tests
make eval         # golden eval, prints accuracy vs target
make api          # uvicorn on :8000 (CORS open for file:// and artifacts)
make web          # serves apps/web on :5173 (python http.server)
make redteam      # generates attacker clips into data/calls (needs GRADIUM_API_KEY)
python3 scripts/pm.py status|start <domain>|msg|done|log|decide|audit
python3 council/ask.py "question" --paste
```

## 6. Conventions
- Python: type hints, `ruff`-clean, no classes where a function will do. Tells are `Tell(name, weight, score, evidence)` records.
- Every signal returns a score in [0,1] *toward AI* (acoustic/script) or *toward scam* (intent) plus a one-line evidence string a non-engineer can read.
- Thresholds and weights live only in `services/api/tell/thresholds.py` (versioned; bump `THRESHOLDS_VERSION` when changed).
- Frontend: vanilla JS, CSS vars from `design/tokens.json`, no frameworks.
- Commits: `backend:`, `web:`, `design:`, `pm:`, `redteam:`, `marketing:` prefixes.

## 7. Editing rules
- Every session: read this file → your domain `skills.md` → `pm/inbox/<domain>.md` → summarize constraints → plan → small steps → run the validation commands.
- One domain per session. Cross-domain asks go through `python3 scripts/pm.py msg <from> <to> "..."`.
- Never edit `CLAUDE.md` / `AGENTS.md` / `.cursor/rules/*` — edit skills.md files.
- After a bug fix, correction, or architectural discovery: add a *specific, reusable* lesson to the relevant skills.md (format `YYYY-MM-DD · domain · lesson`). No vague advice.
- No secrets in code. `.env.example` lists every env name.

## 8. Dangerous areas
- **Privacy guarantee** (`services/api/tell/privacy.py`, `tests/test_privacy.py`): any code path that could send audio bytes over the network. Changing it requires a decision in `pm/DECISIONS.md`.
- **Scorer thresholds**: a 0.05 change flips verdicts on real family-emergency calls. Only change with the eval green and a note.
- **Verdict copy**: never "safe", never "illegal". See `design/skills.md` voice rules.
- **Gradium credits**: `tools/redteam` and spoken verdict spend credits; cap batch sizes, never loop TTS in tests.
- **Recording consent**: v1 analyzes clips the user supplies. Any v2 call-recording feature needs a consent review (two-party-consent states).

## 9. Debugging playbook
- Verdict looks wrong → `curl -F audio=@clip.wav -F transcript="..." localhost:8000/analyze | jq .tells` and read evidence lines before touching weights.
- Acoustic score ~0.5 on everything → clip is band-limited or < 4 s; check `tells[].evidence` for "band-limited" / "too short"; acoustic weight is auto-reduced then.
- Eval dropped → `make eval -- --verbose` prints each miss with fired tells; fix the signal, not the threshold, unless the fix is clearly a calibration.
- Web says "API offline" → it falls back to demo mode; start `make api`, check CORS in `main.py`.
- Gradium CLI fails → `uvx gradium --help`; confirm `GRADIUM_API_KEY` in env; the CLI reads `gsk_…` keys.

## 10. Recent lessons
- 2026-11-07 · backend · Phone-band audio (≤ 4 kHz content) kills spectral tells; always compute `band_limited` first and down-weight spectral signals when true.
- 2026-11-07 · backend · Breath detection needs ≥ 5 s of audio; shorter clips return `score=0.5, evidence="too short"` so they don't bias the verdict.
- 2026-11-07 · design · Light primary teal failed 4.5:1 on white; use `signal.600` in light, `signal.400` in dark.
- 2026-11-07 · pm · iOS exposes no third-party access to cellular call audio; real-call v2 on iOS must be a VoIP/screener design, not a listener.
