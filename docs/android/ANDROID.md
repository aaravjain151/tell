# Tell for Android

A thin client. The phone listens through its microphone and sends the audio to the Tell engine on your computer over the USB cable. The engine does the analysis; the phone only shows the verdict. The audio stays on your own devices: it goes from the phone only to your own computer over the USB cable (it does leave the phone), is analysed in memory there, and nothing is recorded or stored. There is no LAN, Wi-Fi, cloud, relay or analytics, and the app never speaks to the caller (D-003, D-009, D-011; the phone-to-computer cable is the PROPOSED exception D-012 to D-004's "never leaves the device").

## What it can and cannot do (read this first)

* **Speaker mode only.** Android gives ordinary apps no call audio. The call has to be on speakerphone; the app hears the caller from the speaker, plus your own voice and the room. It does not hear a call held to the ear, on Bluetooth or on headphones.
* **Confirmed on the Samsung Galaxy S20 FE / Android 13: the OS silences the microphone for third-party apps during an active cellular call, even on speakerphone.** On a real call `AudioRecord` returns no data (`EVENT_MORE_DATA ... returned -1 bytes`) and `Telecom:SamsungAudioRecordingChecker: isAudioRecording false`, while the engine stays reachable over USB the whole time. Real-call capture on this phone is therefore not possible; use the Mac route for live calls (answer the call on your Mac). The phone app still works for a call on **another device's** speaker held near the phone, or a recording played near it.
* The models (Pellav2 600M, Whisper, the LLM) do not run on the phone. The laptop engine must be running and the cable plugged in. Not "fully on-device".
* Speakerphone audio is a blend of both voices, so the app sends it as `side=mix` and the engine caps how sure it says it is (0.6).
* Phone-band audio is the weakest case for the voice checks; the wording (scam pattern) side still works.

## Two ways to run it

| | PWA in Chrome | Installed app (APK) |
|---|---|---|
| Source | `apps/android/` (served by `make android-pwa`) | `apps/android/native/` (Capacitor wrapper of the same files) |
| Origin the engine sees | `http://localhost:5173` | `http://localhost` |
| Screen locked | Chrome may stop the mic | microphone foreground service keeps capture alive |
| Tunnels | `adb reverse` for 8000 and 5173 | `adb reverse` for 8000 |

## Computer setup (both)

```
brew install android-platform-tools          # adb
make api-android                             # the engine, accepting the app's origins (loopback only)
```

`make api-android` is `make api` with `TELL_CORS_ORIGINS=http://localhost,http://localhost:5173,...`. The default engine refuses the installed app's origin (`http://localhost`) with a 403; the app says "The engine refused this page" if you forget.

## Phone setup

1. Settings > About phone > Software information: tap **Build number** 7 times. Settings > Developer options: turn on **USB debugging**.
2. Plug in the cable, accept "Allow USB debugging" on the phone.
3. `adb devices` must list the phone as `device` (not `unauthorized`).
4. `adb reverse tcp:8000 tcp:8000` (this is the only network path: the phone's own `localhost:8000` is the laptop's engine).

### Installed app

```
cd apps/android/native && npm install && npm run apk     # needs JDK 17 and the Android SDK (see native/README.md)
adb install -r apps/android/native/app-debug.apk
adb shell pm grant dev.doublespeak.app android.permission.RECORD_AUDIO
adb shell pm grant dev.doublespeak.app android.permission.POST_NOTIFICATIONS
adb shell am start -n dev.doublespeak.app/.MainActivity
```

(The grants are optional: the app asks on first use.)

### PWA instead

```
make android-pwa                              # serves apps/android on 127.0.0.1:5173
adb reverse tcp:8000 tcp:8000 && adb reverse tcp:5173 tcp:5173
```
Open `http://localhost:5173/` in Chrome on the phone, menu > **Add to Home screen** (or the "Add to Home screen" button in the connection sheet). It then opens full screen and even opens without the cable, showing the connection screen.

## The speaker-mode call test (about 10 minutes)

1. Open the app. The pill top right must say "Your computer". If it says "Not connected", follow the steps on screen.
2. Tap **Start listening**, read the consent sheet, continue. The Listening bar shows a timer and level bars.
3. With the app listening, play the phone's speaker next to you: first just talk, check the bars move.
4. Real call: have someone call you, answer, **switch to speakerphone**, then open Tell and Start listening (keep the screen on). Have the caller read a scripted scam ("this is your bank, read me the code you just received, don't tell anyone").
5. No call needed for a first check: play `data/calls/qwen3tts/scam_bank_otp.wav` from the laptop at normal volume near the phone and Start listening. Expect warming for about 8 s, then human/unsure, amber, then the red takeover with a vibration.
6. Lock the screen for 5 minutes while listening (installed app only): does the verdict keep updating when you unlock?

Write down: phone model and Android version; PWA or app; did the level bars move with the caller's voice on a real call, or stay flat; did the other side of the call sound in the room mic; time to first verdict; how long until amber/red on the scripted call; did listening survive the screen lock; vibration on amber and red; anything that said the wrong thing. Put it in the call-connection issue (see `docs/call-connection/HANDS-ON-TESTS.md`, Test C).

## Auto-listen (start when you answer a call)

Installed app only (the browser cannot see calls). Opt-in, **off by default**. Turn it on with the switch "Listen automatically when I answer a call" on the main screen or in Settings (the sliders button top right). The first time, a sheet shows the fixed consent: "When you answer a call, Tell listens through your microphone in speaker mode and sends the audio only to your own computer over the USB cable. Nothing is recorded or stored. Tell the other person if your state requires it." Then Android asks for the permissions below. Any refusal leaves the setting off and says why; a permission refused for good shows an "Open app settings" link.

### Permissions

| Permission | Why | When asked |
|---|---|---|
| `READ_PHONE_STATE` (Phone) | To see that a call rang, was answered and ended. Tell never reads the number, contacts or call history (it does not request `READ_CALL_LOG`, so Android does not even hand it the number). | When the setting is turned on |
| `RECORD_AUDIO` (Microphone) | To listen in speaker mode. Android 14 also refuses a microphone service without it. | Same moment, if not granted yet |
| `POST_NOTIFICATIONS` (Android 13+) | The "listening" notification with Stop, the "Call answered, tap Listen" prompt and the "could not reach your computer" notice. | Same moment, if not granted yet |

### What happens on a call

* Call rings: nothing yet. A missed or rejected call does nothing.
* Call answered (incoming call: RINGING then OFFHOOK): auto-listen starts, either by itself or after one tap, depending on the Android version and whether Tell is on screen (table below). An outgoing call does not start it; a call waiting that you answer during an outgoing call does. Call waiting during a listened call keeps the same session.
* While listening: an ongoing notification **"Tell is listening to this call"** with **Stop** and **Turn on speaker**, plus Android's green microphone dot. If Tell is on screen, it switches to the live view by itself and shows the verdicts.
* **Microphone silenced vs computer unreachable are two separate states, in the UI and in code.** These were conflated in the first build (an SSE drop during a call wrongly said "check the USB cable"); they are now distinct:
  * **Mic blocked** (the WebSocket/session is up but `AudioRecord` returns no data, or the level stays at digital silence, for ~4 s while a call is active): the honest state "Your phone is blocking the microphone during the call. On this phone, apps can't hear a call even on speaker." + "Use Tell on your Mac for live calls (answer the call on your Mac)." Listening stops cleanly; the cable is never blamed.
  * **Computer unreachable** (cable out, `adb reverse` missing, engine stopped): "Tell could not reach your computer; plug in the USB cable." A 403 (engine started without the app's origin) says to use `make api-android`; a 429 says another session is open. A mid-call drop probes `/health` first: if the engine still answers, it is a clean stop (or a blocked mic), never "check the USB cable"; only a genuinely unreachable engine says "Lost contact with your computer".
* The non-call ambient path keeps the gentler "No sound is reaching the microphone. Is the call on speakerphone? Some phones silence the mic during calls." note (it clears once real sound arrives), so the recorded-clip-near-the-phone demo is unaffected.
* Call ended (Android reports IDLE only when every call has ended), Stop tapped, the setting turned off, or Tell swiped away from Recents: the microphone is released, the stream is closed with `stop`, the engine session is deleted (`DELETE /session/{id}`), the frame buffer is zeroed. Nothing is written to storage at any point. After Stop, auto-listen does not restart for the rest of that call.
* Setting off: the call-state receiver is disabled in the package manager, so a call does not even wake Tell.

### Which path each Android version takes

"In front" = a Tell screen is resumed. When you answer, the phone app's in-call screen usually comes to the front, so on a real call Tell is normally **not** in front (exception: Samsung's pop-up call display while you use Tell).

| Android | Tell in front | Tell in background or screen off | Why |
|---|---|---|---|
| 5.1 to 10 (API 22-29) | starts by itself | starts by itself | Background foreground-service starts allowed; no microphone while-in-use rule |
| 11 (API 30) | starts by itself | **"Call answered" notification, tap Listen** | A microphone service started from the background gets silence (while-in-use rule) |
| 12, 12L, **13** (API 31-33) | starts by itself | **"Call answered" notification, tap Listen** | `startForegroundService` from the background throws `ForegroundServiceStartNotAllowedException`; a call-state broadcast is not an exemption |
| 14+ (API 34+) | starts by itself | **"Call answered" notification, tap Listen** | As 13, and a microphone-type service started from the background throws `SecurityException` |

Tapping **Listen** (or the notification body) starts the service through `PendingIntent.getForegroundService`: a notification tap is an allowed start and grants microphone access on every version. If a direct start is refused anyway (race with the in-call screen), Tell falls back to the notification. The decision is `StartPolicy` (unit-tested for API 22 to 35).

**On the owner's Galaxy S20 FE (Android 13):** expect one tap. Answer, tap Speaker, pull down the shade, tap **Listen** on "Call answered". If you answer from Samsung's call pop-up while Tell is open on screen, it may start without the tap. Swiping the "listening" notification away is not possible on 13 (ongoing foreground-service notification); on 14+ Android lets you swipe it and Tell posts it again while it listens.

### Speakerphone: what Tell can and cannot do

Tell cannot switch a cellular call to speaker on Android 12+ (and does not try). In AOSP, `AudioManager.setSpeakerphoneOn()` is ignored during a cellular call for apps without `MODIFY_PHONE_STATE` (a system-only permission), and `setCommunicationDevice()` only takes effect for the app that owns the audio mode, which is the phone app. The compliant ways around it (becoming the default phone app with `InCallService`) or the non-compliant ones (hidden APIs, an accessibility service pressing the button, an overlay) are deliberately not used and a static test fails if they appear. So **Turn on speaker** opens the phone app's in-call screen (`TelecomManager.showInCallScreen`, public API, needs `READ_PHONE_STATE`) and you tap its Speaker button.

### Honest limits

* **The microphone is silenced during a call (confirmed on the S20 FE / Android 13).** AOSP's audio policy (Android 10+) gives ordinary apps silence from the microphone while a phone call is active unless they are privileged, the assistant or an accessibility service; manufacturers can differ, but Samsung's build does silence it. Auto-listen starts correctly, the WebSocket to the engine opens, then `AudioRecord` returns no data within ~4 s. Tell detects this and shows the honest state **"Your phone is blocking the microphone during the call. On this phone, apps can't hear a call even on speaker."** with **"Use Tell on your Mac for live calls (answer the call on your Mac)."** — it does **not** blame the USB cable (the engine is reachable; a `/health` probe confirms it before any cable message is shown).
* Speaker mode only; a call on the earpiece, Bluetooth or headphones is not heard.
* One tap on Android 11+ when Tell is not on screen (see the table). No full-screen intent, overlay or wake-up trick is used to avoid it: those are restricted to phone/alarm apps or against Play policy.
* If Tell was force-stopped (Settings > Apps > Force stop), Android does not deliver the call broadcast until Tell is opened once.
* The engine must be running with `make api-android` and the cable plugged in; port 8000 is fixed for the native stream.
* Manually started listening and auto-listen do not run at the same time: if you already tapped Start listening, the call does not open a second session.

### Implementation map

`apps/android/native/android/app/src/main/java/dev/doublespeak/app/`: `call/CallStateMachine` (RINGING/OFFHOOK/IDLE rules), `call/StartPolicy` (per-version path), `call/PermissionGate`, `call/AutoListenCore` (glue, never starts with the setting off), `call/CallSession` + `call/LoopbackEngine` (AudioRecord frames to `POST /session` + `WS /ws/stream` on 127.0.0.1:8000, plain Java sockets, `Origin: http://localhost`, 100 ms PCM16 frames, ping every 10 s), `CallStateReceiver` (manifest `PHONE_STATE`, disabled until opted in), `CallMonitor` (TelephonyCallback.CallStateListener on 12+, PhoneStateListener below), `CallListenService` (microphone foreground service, native capture), `Notices`, `SpeakerActivity`, `ListenServicePlugin` (`getAutoListen`, `setAutoListen`, `stopAutoListen`, `openAppSettings`, event `autoListen`). Page side: `lib/autolisten.js` (wording, status line) and the auto-listen block in `app.js`.

A silenced mic (`AudioRecord` returns -1 after a good start, or ~4 s of digital silence) ends the session with `Outcome.MIC_SILENCED` and the honest message; the engine-reachability probe (`LoopbackEngine.reachable()` → `GET /health`) separates a genuinely gone cable (`LOST`) from a reachable engine (`DROPPED`, a clean stop). On the page, `reachable()` gates every "check the USB cable" message, a distinct `.err.blocked` card shows the honest state, and an SSE drop alone no longer blames the cable.

Tests: `cd apps/android/native/android && ./gradlew testDebugUnitTest` (call-state machine incl. missed calls, call waiting, two calls, user stop, setting changes, process restart; per-version start path; permission-denied paths; the not-connected, refused, busy, lost and mic-failed session paths; WebSocket framing and a full session against a fake engine). `TELL_ENGINE_PORT=8077 ./gradlew testDebugUnitTest --tests '*RealEngineIT*'` streams to a real engine (verified: session, verdicts, clean stop). `node --test apps/android/tests/android.test.mjs` checks the wording, the status line and the Play-policy guard.

### Checking it over adb (no call needed)

```
adb shell cmd package query-receivers --components -a android.intent.action.PHONE_STATE | grep doublespeak   # listed only while the setting is on
adb shell dumpsys package dev.doublespeak.app | grep -A3 "runtime permissions" | grep -E "PHONE_STATE|RECORD_AUDIO|NOTIFICATIONS"
adb shell dumpsys activity services dev.doublespeak.app/.CallListenService                                   # during a call: isForeground=true
```

### The 2-minute real-call test (Android 13, S20 FE)

Before: cable in, `make api-android` running, `adb reverse tcp:8000 tcp:8000`, Tell installed, the pill says "Your computer", auto-listen switched on (consent read, Phone, Microphone and Notifications allowed). A second phone to call from.

1. **0:00 Missed call.** Press Home. Call the S20 FE and hang up before answering. Expect: no Tell notification at all.
2. **0:15 Answer.** Call again and answer. Expect within about 2 s: a "Call answered" notification (heads-up) with **Listen** and **Turn on speaker**.
3. **0:25 Speaker.** Tap Speaker on the in-call screen (or **Turn on speaker**, which brings the in-call screen back).
4. **0:30 Listen.** Pull down the shade, tap **Listen**. Expect: "Tell is listening to this call" with **Stop**, and the green microphone dot.
5. **0:40 Does it hear?** Caller reads: "This is your bank, read me the code you just received, don't tell anyone." Open Tell. On the S20 FE the mic is silenced, so within ~4 s expect the honest state "Your phone is blocking the microphone during the call..." and NOT "check the USB cable". (On a phone that does not silence the mic, the level bars would move instead.)
6. **1:10 Stop.** Tap **Stop** in the notification. Expect: the notification and the mic dot disappear; Tell shows "Listening stopped".
7. **1:20 Call end stops it.** Hang up. Call again, answer, tap Listen, then let the caller hang up. Expect: the listening notification disappears by itself within a second or two.
8. **1:40 Not connected.** Run `adb reverse --remove-all` (or stop the engine). Call, answer, tap Listen. Expect: "Tell could not reach your computer; plug in the USB cable." Restore the tunnel afterwards.
9. **Optional: Tell in front.** Open Tell, keep it on screen, receive a call, answer from the pop-up. Note whether it started without a tap.

Write down for each step: what appeared, and the delay. Put it in the call-connection issue next to the speaker-mode test.

## Limits worth knowing

* One engine session at a time per phone; "Another listening session is open" means a previous session has not timed out (about a minute) or a laptop listener is running.
* Vibration only on amber (short double buzz) and red (long pattern).
* The transcript on screen is the last 10 seconds, held in the page only; Stop leaves the last verdict on screen until you tap Clear screen.
* The debug APK is signed with the debug key and has `webContentsDebuggingEnabled` on. Do not distribute it.
* Services in the engine are unchanged. The only repo changes outside `apps/android` are the Makefile targets `api-android` and `android-pwa` and the `.gitignore` lines for native build outputs.
