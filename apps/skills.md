# apps/ — skills.md (frontend domain; see also design/skills.md)

## Purpose
`apps/web/index.html` is the whole UI: one self-contained page, no build step, opens from `file://`, `make web`, or as a Claude Artifact.

## Layout
Two-column instrument panel: left = input (samples, transcript, audio file / mic, Analyze, Speak), right = verdict card → three gauges → tells grouped by family → privacy proof (bytes-out counter, signature, request log). Stacks at ≤ 780 px.

## Data contract (from `POST /analyze`)
`{tier, p_ai, p_scam, confidence, disclosed_ai, headline, advice, tells[{name, family, score, weight, evidence, applicable}], thresholds_version, egress{caller_audio_bytes_sent, bytes_sent_external, external_requests, context}, signature, cost{latency_ms}}`.
`render(v)` is the only function that touches the verdict DOM. Samples embedded in `#samples-data` are real engine output (regenerate with `./.venv/bin/python apps/web/build_samples.py` if thresholds change).

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
- 2026-11-07 · frontend · A context line under the gauges shows duration, band-limited, transcript source and local scam-talk model from `egress.context`/`cost`; the bytes counter reads the server's `caller_audio_bytes_sent` (verified 0 with whisper + wav2vec2 + Ollama all on).
- 2026-11-07 · frontend · Doublespeak UI rebuild: paper (the call, caller's own words marked where a tell fired) beside a telescreen (verdict) with the privacy proof as its own card. Marks come from the quoted phrases in `tells[].evidence` matched against `verdict.transcript` (new additive field), so every evidence string that quotes a phrase becomes an underline; unquoted tells (pause rhythm etc.) stay in the list.
- 2026-11-07 · frontend · The page had no `<meta charset>` and `python -m http.server` sends no charset, so `·`, `—` and emoji rendered as mojibake; always declare utf-8 and use inline SVG icons, never emoji.
- 2026-11-07 · frontend · No web fonts or CDNs on purpose: the privacy demo must work with Wi-Fi off. System stacks only (Charter/Iowan for the transcript, system-ui for UI).
- 2026-11-07 · frontend · Testing recipe without a browser extension: headless Chrome `--screenshot` with `--virtual-time-budget`. Headless enforces a ~500 px minimum window, so check phone layout by screenshotting a wrapper page with a 390 px `<iframe>`. Virtual time freezes CSS transitions mid-flight (faded chips, empty bars): add `--force-prefers-reduced-motion` to see the final state, and confirm JS state with `--dump-dom`. `?theme=light|dark` forces a theme.
- 2026-11-07 · frontend · Red-team chip row (`#rt`) is built only after `probe()` succeeds and `/redteam/samples` returns >= 1 clip; any failure hides it. Chips reuse `.sample` so existing aria-pressed resets cover them; `attach()`/`clearAudio()` reset `rtCur`. A class that sets `display` beats the `hidden` attribute: `.rt-q{display:inline-flex}` kept the Opus toggle visible with no clip selected until `.rt-q[hidden]{display:none}` was added. Long chip lists collapse to 6 (4 at <= 480 px) behind "Show all N" instead of a clipped scroll box. :8000 is often taken by another worktree's API; to test a branch, copy index.html with the API const swapped to another port into the scratchpad (never edit the real one).
