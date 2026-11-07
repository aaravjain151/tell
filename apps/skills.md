# apps/ — skills.md (frontend domain; see also design/skills.md)

## Purpose
`apps/web/index.html` is the whole UI: one self-contained page, no build step, opens from `file://`, `make web`, or as a Claude Artifact.

## Layout
Two-column instrument panel: left = input (samples, transcript, audio file / mic, Analyze, Speak), right = verdict card → three gauges → tells grouped by family → privacy proof (bytes-out counter, signature, request log). Stacks at ≤ 780 px.

## Data contract (from `POST /analyze`)
`{tier, p_ai, p_scam, confidence, disclosed_ai, headline, advice, tells[{name, family, score, weight, evidence, applicable}], thresholds_version, egress{caller_audio_bytes_sent, bytes_sent_external, external_requests, context}, signature, cost{latency_ms}}`.
`render(v)` is the only function that touches the verdict DOM. Samples embedded in `#samples-data` are real engine output (regenerate with the snippet in `services/api/skills.md` if thresholds change).

## Rules
- Vanilla JS, CSS vars only; colours and fonts come from `design/tokens.json` (copy the values, keep names aligned).
- Status is never colour-only: tier label + coloured rail + headline.
- Demo mode (no API) must still show a complete, honest verdict; never fake a live analysis.
- Mic → `MediaRecorder` webm → API needs ffmpeg; the status line says so.
- The artifact sandbox refuses the mic; that's expected. The real demo runs from `make web` + `make api` on the laptop.
- Never write "safe"/"illegal" in UI copy (design/skills.md voice rules).

## Validation
```
make web   # http://localhost:5173 — check at 380 px and 1200 px, light and dark
make api   # verdict card updates from the live engine; log shows "loopback only"
```
Regenerate samples after a thresholds change (see services/api/skills.md), re-inject into `#samples-data`.

## Recent lessons
- 2026-11-07 · frontend · Samples are injected at build time (`__SAMPLES__` placeholder) because an artifact can't fetch a sibling JSON unless it is published alongside; keep them inline.
