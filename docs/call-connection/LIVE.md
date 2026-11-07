# Live call detection

The verdict updates while the call goes on, can change mid-call, and a listener starts by itself when a call app
starts producing audio. Everything runs on this laptop; nothing is recorded or sent (D-003, D-004, D-009, D-011).

## Pieces

```
call app audio --> tap_audio --stream --> tools/macos/listen.py --WS /ws/stream--> API (RAM ring, ticks every 3 s)
                   (Core Audio tap)       (loopback only)                              |
                                                                    Stabiliser (display only) --> WS verdict + stable
                                                                                         \--> GET /live/events (SSE) --> page
```

* `tools/macos/listen.py` spawns `tap_audio --stream`, opens a session (`POST /session`, allowed Origin), does the
  token hello (side `far`), pipes 100 ms PCM frames, prints one status line per verdict.
* The API keeps a 30 s RAM ring, analyses the last 10 s every 3 s of audio, and runs a `Stabiliser` over the tick
  verdicts. It changes only what the live stream DISPLAYS. The stored per-window tier, `scorer.py` and
  `thresholds.py` are untouched (golden eval identical).
* `GET /live/events` is a read-only Server-Sent-Events feed for the page (schema in `doublespeak/live.py` and
  `services/api/skills.md`). `POST /live/dismiss` or the WS message `{"type":"dismiss"}` acknowledges a red alert.

## Using it

```
python3 tools/macos/listen.py --watch --i-understand     # arms by itself for a call app, stops when it ends
python3 tools/macos/listen.py --now   --i-understand     # start immediately (system audio, or --process NAME)
python3 tools/macos/listen.py --file data/calls/gradium/scam_bank_otp.wav --i-understand   # demo, real-time pace
```

Build the tap once: `cd tools/macos/tap_audio && swift build -c release`. The first run asks for the audio-capture
permission for your terminal (a denied tap delivers silence, not an error). Without `--i-understand` it asks `y/N`
interactively and prints the consent line first.

### How arming works (`--watch`)

Every 2 s it runs `tap_audio --list` (processes currently producing audio) and compares names/bundle ids, exactly and
case-insensitively, with the call-app list: FaceTime, Phone, callservicesd, avconferenced, zoom.us, WhatsApp,
Microsoft Teams (override with repeated `--call-process`). It never arms on music or browsers by default. A match
arms: it starts `tap_audio --stream --process <app>` and the terminal shows `=== LISTENING ===` (and the tab title
changes). The call is over after 3 consecutive polls (about 6 s) without the app producing audio, which bridges short
silent gaps. It also stops on Ctrl-C, on tap exit, or after 90 s of silence. Stopping sends `stop`; the API wipes the
ring.

## What the display does

* Warm-up: until 8 s of speech and 20 words, the shown tier is `warming_up` (only a corroborated red can break through).
* Escalate in 2 ticks, de-escalate only after 5 lower ticks and 20 s dwell, so it does not flap.
* Evidence (urgency, payment, impersonation, credential ask, secrecy) is sticky for the call.
* Red needs corroboration: two intent families including payment or credentials together with a scam tick, or a scam
  verdict with p_scam >= 0.8 on 2 ticks in a row. A single scam tick never alerts; sustained scam ticks give amber
  (held 15 s so a notification does not flap). Red latches until dismissed; dismissing clears the evidence, so only
  fresh corroboration can raise it again.
* A friendly call that turns into a scam goes from `steady/human` to an alert within a few ticks; a long human call
  with stray blips never alerts (both in `tests/test_live.py`). The notification fires only when the alert CHANGES to
  amber or red, with fixed wording, no sound unless `--sound`, and never any caller text.

## Measured (replay, this branch, real API, whisper + stub LLM)

Per-tick latency from the moment the audio for a window was sent to its verdict: 0.3 to 1.0 s. A call that starts
friendly (two copies of `long_appointment.wav`) and turns into `scam_bank_otp.wav` at 36.8 s showed `human/steady`
through 51.8 s and `scam/latched/red` at 54.8 s (the third scam tick). See the PR for the event timeline.

## What is and is not heard

Heard: audio that the chosen process (or the whole system mix with `--now`) plays to this Mac, analysed on this
machine. With a Continuity call (iPhone calls via the Mac) the caller's voice comes out of `callservicesd` /
`avconferenced` / FaceTime, which is why those are in the default list. Your own microphone is NOT captured by the tap
(side `far` is the caller). Not heard: calls on the iPhone alone, calls in a browser tab (not armed by default), anything
when permission is denied. Nothing is written to disk, the SSE feed carries the window transcript to the local page
only (loopback), and the API never speaks to the caller.

## Honest limits

* Not yet verified on a real phone call: the per-process tap on `callservicesd`/`avconferenced` and Continuity audio
  routing are untested; `--watch` depends on those processes showing as "producing audio".
* A speakerphone or a mixed capture blends both voices; use `--side mix` (the API caps displayed confidence at 0.6).
* Cold start: the first tick after server start can lag by many seconds while models load. Start the API ahead of time.
* Phone-band audio (8 kHz) is the weakest case for the acoustic voters; the content (intent) side still works.
* The stabiliser trades speed for stability: red needs two agreeing ticks (about 6 s of audio) after the evidence is in.
