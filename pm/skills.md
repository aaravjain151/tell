# pm/ — skills.md

## Purpose
The project's operating system: brief (`PRODUCT.md`), board, decisions, session log, audits, inter-session inbox.

## Files
- `PRODUCT.md` — the brief. Change it through a decision, not silently.
- `BOARD.md` — `## <domain>` → `### NOW` (max 3) / `### NEXT` / `### LATER`; tickets `[T-###] title — owner-tool`.
- `DECISIONS.md` — `## D-### · date · title` / Decision / Why. Log via `scripts/pm.py decide`.
- `SESSION_LOG.md` — appended by `pm.py start|log|done|decide|audit`.
- `AUDITS.md` — `pm.py audit` output (stale messages, stale skills files, NOW > 3, root lessons > 10).
- `inbox/<domain>.md` — open cross-session messages; resolve with `pm.py done`.
- `templates/handoff.md` — use for any cross-domain ask bigger than one line.

## Rules
- NOW has at most 3 items per domain. Hackathon mode: backend + frontend are the only active build domains until the demo works.
- Any scope change → `pm.py decide` first, then the board.
- `pm.py audit` at the start of every PM session; fix warnings or log why not.

## Validation
```
python3 scripts/pm.py status
python3 scripts/pm.py audit
```

## Recent lessons
- 2026-11-07 · pm · Hackathon reality: two build domains max; marketing/feedback artifacts exist for the pitch and the week after, not for tonight.
