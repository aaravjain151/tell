# Doublespeak menu bar app (macOS)

A small menu bar app that keeps the local engine and the call listener running, so nobody types a command.
It listens by itself when a call plays on this Mac, shows one icon for the state, and warns on amber or red.
Passive only: it never speaks to the caller, audio stays on this Mac, loopback only, RAM only, no analytics,
no third-party SDKs (D-003, D-004, D-009, D-011).

Source: `apps/macos/DoublespeakBar/` (SwiftUI `MenuBarExtra`, macOS 14+, bundle id `dev.doublespeak.app.mac`, menu bar only).

## Install and run

Prerequisites, once: the repo has its `.venv`, and the audio tap is built.

```
cd /Users/aarav/Downloads/tell/tools/macos/tap_audio && swift build -c release
```

Build (signs locally with your Apple ID team; build output stays out of the repo):

```
cd apps/macos/DoublespeakBar
xcodegen generate
xcodebuild -project DoublespeakBar.xcodeproj -scheme DoublespeakBar -destination 'platform=macOS' \
  -derivedDataPath /tmp/doublespeak_dd -allowProvisioningUpdates DEVELOPMENT_TEAM=<your team id> CODE_SIGN_STYLE=Automatic build
```

Run it from the build folder, or copy it where you like (nothing here copies it for you):

```
open /tmp/doublespeak_dd/Build/Products/Debug/Doublespeak.app
# optional, to keep it: cp -R /tmp/doublespeak_dd/Build/Products/Debug/Doublespeak.app ~/Applications/
```

Tests: `xcodebuild ... test` with the same flags (42 XCTest cases, no network, no real processes).

First launch: a welcome window shows the privacy note (the consent line), then explains the two macOS permissions.
Nothing starts until you press "I understand, continue".

## What it does

* Starts the engine: `.venv/bin/python -m uvicorn doublespeak.main:app --host 127.0.0.1 --port 8000` from `services/api`,
  with `PELLA_MODEL=Sadanie/pellav2-audio-deepfake-detector` and `PELLA_DEVICE=mps` when the weights are in the
  Hugging Face cache. If `.env` exists it passes `--env-file <repo>/.env` to uvicorn. The app only checks that the file
  exists; it never opens, reads or prints it.
* Starts `tools/macos/listen.py --watch --i-understand --no-notify --url http://127.0.0.1:<port>`. The consent sheet is what
  satisfies `--i-understand`. `--no-notify` because the app posts the notification itself.
* If something already answers `/ready` on the port (for example your own `make api`), the app uses it and does not
  start a second engine or stop yours. It also serves `apps/web` on `127.0.0.1:5173` if nothing is there, so "Open
  Doublespeak" works without `make web`.
* Restarts a crashed child after 1, 2, 4, 8, 16, 30 s (cap); after 4 quick failures in a row it shows "Engine problem".
* Subscribes to `GET /live/events` for state, verdict and the stable alert. `/ready` every 3 s for the privacy row.
* Quit stops the listener (SIGINT, so it wipes the RAM ring and closes the tap), the engine and the page server.

## How auto-arming works

The listener (not the app) polls `tap_audio --list` every 2 s. When a known call app (FaceTime, Phone, callservicesd,
avconferenced, zoom.us, WhatsApp, Microsoft Teams) produces audio it starts a tap on system audio and opens a live
session; about 6 s after that app goes quiet it stops. The app just shows it: Waiting for a call, then Listening
while `/live/events` says `listening`. It never arms on music or a browser by default.

## Icons and states

| State | Icon | When |
|---|---|---|
| Off | power circle | Switched off from the menu, or setup not finished |
| Waiting for a call | ear | Engine up, listener armed, no call yet |
| Listening | waveform in a circle (teal) | A call is being listened to. The item has no hide option and `isInserted` is pinned on |
| Amber | warning triangle | Stable alert amber: "Possible scam call. Be careful with money and codes." |
| Red | octagon | Stable alert red: "Likely scam call. Do not share money, codes or passwords." |
| Paused | pause circle | "Pause for 1 hour" (listener stopped; resumes by itself, or press Resume) |
| Engine problem | wrench and screwdriver | Engine not answering, wrong folder, no audio tap, port in use, crash loop |

Every state has its own shape, not just a colour. A single failed health poll never hides a live call.

## Menu

Status and what to do, last verdict in plain words with the voice x content label (for example "Human voice, no scam
pattern heard."), Open Doublespeak (http://localhost:5173), Pause for 1 hour / Resume, Turn off / Turn on,
Launch at login, "Privacy: 0 bytes sent" (shown when every switch in `/ready` `privacy_posture` is off; if one is on the
row says a setting could send data out), the honest-limits sentence, Settings, Quit.

Launch at login uses `SMAppService.mainApp`, off until you flip it. The app never writes a LaunchAgent plist and never
touches login items otherwise. macOS may ask you to approve it in System Settings, Login Items.

Notifications: one per change of the stable alert to amber or red, fixed wording, never caller text, no sound unless you
turn that on in Settings. Sensitivity is shown as a label only (set by the engine).

## Permissions

1. Audio capture. The first time a call plays, macOS asks to let Doublespeak capture audio from other apps. The prompt
   carries this sentence from the app: "Doublespeak listens to the call audio your Mac plays, only to warn you about
   scams. The audio is analysed on this Mac and never recorded or sent anywhere." Choose Allow. Denied means macOS gives
   the tap silence, not an error, so nothing is heard. Fix: System Settings, Privacy & Security, Screen & System Audio
   Recording, allow Doublespeak (the Settings window has a button). The exact title of this prompt differs by macOS
   version and was not captured in testing.
2. Notifications. macOS asks "Doublespeak would like to send you notifications". If you deny, the icon still changes but no
   notice appears; Settings shows "Denied" with a button to the right System Settings pane.

## What is and is not heard

Heard: audio that a call app plays to this Mac, analysed on this machine. Not heard: your own microphone, calls on the
iPhone alone, calls in a browser tab (not armed by default), anything when audio capture is denied. See
`docs/call-connection/LIVE.md` for the pipeline and the stabiliser.

## Troubleshooting

* Engine problem, "port 8000 is used by another program": something else owns the port. Quit it, or set another port in
  Settings (the listener follows). If it is another Doublespeak engine that answers `/ready`, the app adopts it instead.
* Engine problem, "No Python found" or "audio tap is not built": Settings, set the Doublespeak folder; build the tap with the
  command above.
* Stays on Waiting during a call: the call must come out of this Mac (Continuity, FaceTime, WhatsApp, Zoom). Check the
  audio capture permission. Run `tools/macos/tap_audio/.build/release/tap_audio --list` while the call plays to see
  whether the call app shows as producing audio.
* Listening but never a verdict: first verdict can take many seconds while models load on a cold start.
* Nothing starts: finish the welcome window; the app does nothing until the consent button is pressed.

## Honest limits

* Works for calls played on this Mac (iPhone calls answered on the Mac via Calls on Other Devices, FaceTime, WhatsApp, Zoom).
* Not verified on a real incoming call end to end through the app; the macOS permission prompts were not seen.
* macOS lets a user Cmd-drag any menu bar icon away. The app never offers to hide it and keeps it inserted, but it cannot
  stop that gesture; if the icon is gone, relaunch.
* The app is not sandboxed (it must launch processes from your repo), so there is no network entitlement to restrict.
  A test checks that every URL in the source is loopback, that no entitlement beyond a client one could be added, and that
  no analytics words appear.
* If the app crashes (not Quit), children it started may keep running until you end them.
