# Gradium in Tell

Tell uses [Gradium](https://gradium.ai) text-to-speech in exactly two places. Both send **only Tell's own text** to
Gradium, never caller audio and never caller words. This is the privacy rule from D-004 and D-006, made concrete.

## 1. Red-team attacker clips (build/eval time)

`tools/redteam/engines.py` (`gradium()`) turns **our own scripted attacker lines** into WAVs so we can test the
detector against synthetic voices. The script text is ours; caller audio is never involved. See `tools/redteam/`.

## 2. The pre-rendered spoken verdict (the Best-Use-of-Gradium moment)

Tell **speaks its verdict out loud in a Gradium voice**. To keep the privacy guarantee intact and so it works on
stage with Wi-Fi off, the audio is **rendered ahead of time** and played from a local file at call time:

- `tools/render_verdict_audio.py` renders each of Tell's **fixed** spoken lines (one per verdict tier) with the
  Gradium CLI (`uvx gradium tts`) into `apps/web/verdict_audio/<tier>.wav` (16 kHz mono) plus a `manifest.json`
  (line text, file, sha256, voice id, date). It **refuses to render anything that is not in the fixed set**
  (`tell.speak.SPOKEN_LINES`). Run it with `make verdict-audio` (or `make verdict-audio ARGS=--check` to validate
  without calling Gradium). It prints how many Gradium calls / credits it used.
- At call time nothing is sent anywhere. The web page plays `verdict_audio/<tier>.wav` directly (a same-origin,
  loopback read); the macOS listener can play it with `afplay` (`listen.py --speak`); the API's
  `POST /speak` serves the cached bytes in `mode=prerendered`. **No Gradium call, no network, no egress** — the
  egress counters stay `0` at call time. The only Gradium bytes ever spent were at build time, recorded as
  `verdict_tts_prerender` in the egress meter.
- If a pre-rendered file is missing, every surface falls back to the **live** path (`speak.verdict_wav`, which calls
  Gradium now and records `verdict_tts`) and says so, so the feature still works on a fresh checkout.

### The fixed spoken lines

The single source of truth is `tell.speak.SPOKEN_LINES` (one short sentence per tier: a headline verdict + brief
spoken advice). Nothing else may ever be voiced. Current set:

| tier | spoken line |
|---|---|
| scam | Heads up. Scam pattern. Hang up and call back on a number you already have. |
| human | Sounds human. No scam pattern heard. |
| ai_undisclosed | Likely synthetic, and the caller did not say so. Treat it as untrusted and call back on a known number. |
| ai_disclosed | The caller said it is automated. Never share codes or payment with an automated caller. |
| unsure | Unsure. Not enough signal to judge. If money or codes come up, hang up and call back on a known number. |

If these change, re-run `make verdict-audio`. The manifest's `sha256` is verified before a cached file is served, so
a stale or edited file is refused (it falls back to live).

## Why this is a good use of Gradium

Most "AI voice" demos pipe the user's words to a cloud TTS. Tell does the opposite: it uses a premium Gradium voice to
make its **own** safety verdict audible to someone who may not be looking at the screen — the exact moment that
matters on a scam call — while keeping the hard privacy promise that **nothing about the caller ever leaves the
device**. Pre-rendering means the voice is there even with the network off, and the egress meter proves it: `0` bytes
at call time.

## Keys and cost

- `GRADIUM_API_KEY` (and optional `GRADIUM_VOICE_ID`) live in `.env`, loaded into the process env only for the render
  step: `set -a && . ./.env && set +a && make verdict-audio`, or `python3 tools/render_verdict_audio.py
  --env-file .env`. The key is never printed and never committed.
- Rendering the full fixed set is 5 Gradium calls (one per tier). Re-render only when the fixed wording or voice
  changes. The WAVs and manifest are gitignored — audio is never committed.
