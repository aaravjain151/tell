# council/ — skills.md

## Purpose
Ask Claude, GPT, Grok and Gemini the same question as a panel of consultants (roles.json), then synthesize. Sessions land in `council/sessions/` (gitignored).

## Use
```
python3 council/ask.py "Should v2 be an Android dialer or an iOS screener number?" --paste   # no keys: prompts to paste into the apps
python3 council/ask.py "..." --roles engineer skeptic --providers anthropic             # with keys in .env
python3 council/ask.py "..." --dry-run
```
Context block = `pm/PRODUCT.md` + `pm/DECISIONS.md` (first 12k chars each). Keep them current.

## Rules
- Council output is advice, not a decision. If it changes direction: `python3 scripts/pm.py decide ...`.
- Model names in `.env`; only `claude-opus-5-5` is a hardcoded default.

## Recent lessons
- 2026-11-07 · council · First question to ask: "What is the cheapest test this week that the passive detector catches a *fresh* Gradium clone at phone bandwidth?"
