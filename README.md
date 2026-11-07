# Tell

*Every voice has a tell.* A privacy-first detector that classifies the voice on a call as **Human · AI (identified itself) · AI (undisclosed) · Scam pattern**, shows the exact tells that fired, and never sends caller audio off the device.

Built at HACK1984 (Privacy-First track · Best use of Gradium).

## Run it
```
make setup && make test && make eval     # 17 tests · eval ≥ 0.85 / 0.90
make api                                 # http://localhost:8000  (docs at /docs)
make web                                 # http://localhost:5173
```
Optional: `cp .env.example .env`, add `GRADIUM_API_KEY`, then `make redteam` generates attacker clips and the 🔊 button speaks the verdict.

## How it works
See `skills.md` (architecture) and `services/api/skills.md` (signals). Short version: numpy acoustic tells (breath, pauses, pitch wander, noise floor) + script tells (assistant-style phrasing, zero disfluency) + intent tells (urgency, payment rails, impersonation, credential asks, secrecy) → deterministic fusion → signed verdict. Privacy is enforced by `services/api/tests/test_privacy.py`.

## Repo map
`skills.md` is the source of truth. Domains: `apps/` `design/` `services/api/` `tools/redteam/` `marketing/` `feedback/` `pm/`. Tooling: `scripts/pm.py`, `council/ask.py`, `agents/ROUTING.md`.
