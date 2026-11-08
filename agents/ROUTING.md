# agents/ROUTING.md — which tool for which job

| Tool | Best at | Avoid for |
|---|---|---|
| Top-tier Claude in Claude Code | architecture, PM, `scorer.py` / `thresholds.py` / `privacy.py` (dangerous areas), reviews | mechanical renames |
| Smaller Claude model | mechanical work: fixtures, regex lists, docstrings, copy tweaks | threshold changes |
| Codex | well-scoped tickets with tests (one signal, one endpoint), branch per task | UI polish |
| Cursor | `apps/web` edit → preview loops | anything in `services/api/tell/scorer.py` or `privacy.py` |
| Claude app (chat) | research, pitch copy, briefs, council questions | code edits |
| Image/video tools | marketing visuals only; never fake users, screenshots of "results", or testimonials | product UI |

## Routing table (reviewer ≠ author tool)
| Job | First choice | Reviewer |
|---|---|---|
| New acoustic/script/intent signal | Claude Code | Codex (writes the adversarial test) |
| Threshold change | Claude Code (with eval before/after in commit) | human |
| Web UI change | Cursor | Claude Code |
| Red-team scripts / Gradium calls | Claude app (writes scripts) → human runs `make redteam` | Claude Code |
| Pitch, demo script, hooks | Claude app | human |
| Privacy guarantee changes | human + Claude Code, logged in DECISIONS | second Claude session that hasn't seen the diff |

## Parallelism
Max 3 coding agents at once, separate branches and files, never self-merge. Cross-domain needs go through `scripts/pm.py msg`.

Model names change; the PM re-checks `.env` model vars monthly. Only `claude-opus-5-5` is hardcoded as a council default.
