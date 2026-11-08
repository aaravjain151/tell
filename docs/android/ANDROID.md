# Tell for Android

A thin client. The phone listens through its microphone and sends the audio to the Tell engine on your computer over the USB cable. The engine does the analysis; the phone only shows the verdict. The audio stays on your own devices: it goes from the phone only to your own computer over the USB cable (it does leave the phone), is analysed in memory there, and nothing is recorded or stored. There is no LAN, Wi-Fi, cloud, relay or analytics, and the app never speaks to the caller (D-003, D-009, D-011; the phone-to-computer cable is the PROPOSED exception D-012 to D-004's "never leaves the device").

## What it can and cannot do (read this first)

* **Speaker mode only.** Android gives ordinary apps no call audio. The call has to be on speakerphone; the app hears the caller from the speaker, plus your own voice and the room. It does not hear a call held to the ear, on Bluetooth or on headphones.
* Some phones silence the microphone for other apps during a call. If the level bars stay flat for 8 seconds the app says so. Whether the S20 FE does this is exactly what the call test below finds out. Not yet verified on a real call.
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

## Limits worth knowing

* One engine session at a time per phone; "Another listening session is open" means a previous session has not timed out (about a minute) or a laptop listener is running.
* Vibration only on amber (short double buzz) and red (long pattern).
* The transcript on screen is the last 10 seconds, held in the page only; Stop leaves the last verdict on screen until you tap Clear screen.
* The debug APK is signed with the debug key and has `webContentsDebuggingEnabled` on. Do not distribute it.
* Services in the engine are unchanged. The only repo changes outside `apps/android` are the Makefile targets `api-android` and `android-pwa` and the `.gitignore` lines for native build outputs.
