# Tell for iPhone

A thin client, like the Android app. The phone listens through its microphone and the audio goes over the USB cable to the Tell engine on your Mac. The engine does the analysis; the phone shows the verdict. The audio stays on your own devices: it goes from the phone only to your own computer over the USB cable (it does leave the phone), is analysed in memory there, and nothing is recorded or stored on the phone or the Mac. There is no LAN, Wi-Fi, cloud, relay, analytics or third-party SDK, and the app never speaks to the caller (D-003, D-009, D-011; the phone-to-computer cable is the PROPOSED exception D-012 to D-004's "never leaves the device").

## What it can and cannot do (read this first)

* **Speaker mode only, and NOT for a call on this same iPhone.** iOS gives apps no call audio, and it will not let a third-party app start (or keep) the microphone while a phone call is active on the phone (confirmed on the owner's iPhone 14 Pro Max: "Could not start the microphone" during a call). The app listens through the microphone to a call playing out loud *near* the phone: another device's speaker, or a recording. For a call on this iPhone use the Mac route (Calls on Other Devices, so the call plays on the Mac). The app never claims to hear both sides, and does not hear a call held to the ear, on Bluetooth or on headphones.
* The app detects an active call with CallKit's `CXCallObserver` (it reports only that a call exists: no audio, no entitlement). While a call is active Start is disabled and a calm fixed message says "A phone call is using the microphone. iOS does not let apps listen during a call. Listen to a call on another device, or use the Mac (Calls on Other Devices)." The state clears when the call ends. If a call begins while listening, the screen says "The call interrupted the microphone" and the app tries to resume by itself when the call ends (and on the AVAudioSession interruption-ended notification).
* If the level bars stay flat for 8 seconds the app also says so.
* The models do not run on the phone. The Mac engine must be running and the cable plugged in.
* Speakerphone audio is a blend of both voices, so the app sends `side=mix` and the engine caps how sure it says it is (0.6). The "How sure" label is also honest about the voice: while the voice question is unresolved it can never read High, and a note says "The voice check is not sure." or "The voice checks disagree."

## How the audio gets to the Mac (inverted direction)

An iPhone cannot reach the Mac's `localhost`, so the app runs a tiny WebSocket **server on the phone's own loopback** (127.0.0.1 and ::1, port 8765, Network.framework, loopback interface only). `iproxy` (libimobiledevice, usbmuxd, USB only, never `-n`) forwards the Mac's `127.0.0.1:8765` to that port, and `tools/ios/bridge.py` connects as the client:

```
iPhone mic -> app (PCM16 16 kHz mono, 100 ms frames) -- loopback WS server :8765
   <== USB cable (usbmuxd / iproxy) ==>  tools/ios/bridge.py  -> engine POST /session + WS /ws/stream (side=mix, source=iphone)
engine verdicts on the bridge's OWN /ws/stream session (full verdict + stable + 2x2 + How sure) -> bridge -> phone JSON ticks
```

The phone accepts one client, requires the per-launch **pairing code** shown on its connection screen (the bridge sends it in its first message, within 5 s), and refuses anything with an `Origin` header (a web page). Stop on either side wipes buffers; the engine wipes its ring when the stream closes. If the computer ends the session (panic, closed, longest time reached, engine gone) the phone stops listening and says so. The bridge never reads the engine's global live feed and never follows a redirect; every request it makes is re-checked to be loopback.

## Computer setup

```
brew install libimobiledevice xcodegen      # iproxy / idevice_id, and the project generator
make api                                    # the engine on 127.0.0.1:8000 (default origins are enough)
cd apps/ios && xcodegen generate            # creates Doublespeak.xcodeproj (not committed)
```

## One-time phone and Xcode setup (needs the owner)

This Mac had no code-signing identity when this was built (`security find-identity -v -p codesigning` printed 0), so **the app has not been installed on the phone.** Nothing here creates certificates or touches an Apple ID.

1. Xcode > Settings > Accounts > **+** > Apple ID. A free Personal Team works; its profile **expires after 7 days**, then rebuild and reinstall (the app opens no more after expiry).
2. On the iPhone: Settings > Privacy & Security > **Developer Mode** > on, restart, confirm.
3. Plug the iPhone in, unlock it, tap **Trust This Computer** and enter the passcode. `xcrun devicectl list devices` must show it (UDID `00008120-000E503E0238C01E`).
4. Find your team id: Xcode > Settings > Accounts > the team > or `defaults read com.apple.dt.Xcode IDEProvisioningTeamByIdentifier`. Put it in `apps/ios/project.yml` as `DEVELOPMENT_TEAM` for your own checkout (do not commit it), or pass it on the command line below.

## Build and install

```
cd apps/ios
xcodebuild -project Doublespeak.xcodeproj -scheme Doublespeak -configuration Release \
  -destination 'id=00008120-000E503E0238C01E' -allowProvisioningUpdates \
  DEVELOPMENT_TEAM=YOURTEAMID -derivedDataPath build build

xcrun devicectl device install app --device 00008120-000E503E0238C01E build/Build/Products/Release-iphoneos/Doublespeak.app
xcrun devicectl device process launch --device 00008120-000E503E0238C01E dev.doublespeak.app.ios
```

Or open `Doublespeak.xcodeproj` in Xcode, pick the phone and press Run. The first launch of a Personal Team app may need Settings > General > VPN & Device Management > your Apple ID > **Trust**.

To prove it compiles for a device without signing (done in this repo): `xcodebuild ... -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build`.

## Run it

1. Open **Tell** on the phone. First run shows the consent sheet; read it, continue. The connection screen shows the **pairing code** (for example `K7QM-4TXD`) and the exact command.
2. On the Mac, with the phone plugged in and unlocked, in the repo root:
   ```
   python3 tools/ios/bridge.py --token K7QM-4TXD
   ```
   It prints the consent line, starts `iproxy`, connects, and the phone's pill turns to "Your computer". If `iproxy` or the phone is missing it says so loudly and tells you the fix. `--url`, `--origin`, `--udid` and `--port` exist; the engine URL must be loopback.
3. Tap **Start listening** on the phone. The Listening bar shows a timer, level bars and a big Stop. Amber and red give a haptic; red takes over the screen with **Dismiss** (the bridge sends it on its own engine session only, so it never clears another listener's alert).
4. The code changes every time the app launches. The iOS Simulator shares the Mac's loopback: use `--direct` instead of iproxy.

## The speaker-mode call test (about 10 minutes)

1. Bridge connected (pill says "Your computer").
2. No call needed first: play `data/calls/qwen3tts/scam_bank_otp.wav` from the Mac at normal volume near the phone and tap Start listening. Expect "Listening" for several seconds, then human/unsure, amber, then the red takeover with a vibration.
3. Real call, supported way: call the iPhone-owner from a SECOND device (or play a recording on one) so the call plays out loud near the phone, open Tell on the iPhone, Start listening. Have the caller read a scripted scam ("this is your bank, read me the code you just received, don't tell anyone"). A call answered ON this iPhone cannot be heard by the app (see above); for that use the Mac route.
4. Lock the screen for 5 minutes while listening (audio background mode): does it keep updating when you unlock?

Write down: did the level bars move with the caller's voice on a real call or stay flat; did the call-active message appear and clear; time to first verdict; time to amber/red on the scripted call; screen-lock survival; haptics on amber and red; anything that said the wrong thing. Put it in the call-connection issue (`docs/call-connection/HANDS-ON-TESTS.md`, Test C).

## Not yet verified

* Installing and running on the real iPhone (no signing identity here).
* Screen-locked capture over minutes, and resume after a call that ends while the app is listening (the call-active state and the disabled Start were confirmed by the owner on the phone; the resume path is unit-tested with a fake observer only).
* Layout on the real phone after the safe-area fix (checked in the iPhone 14 Pro Max and 17 Pro simulators only).
* `iproxy` delivering the connection to the app's loopback listener over a real cable (the app listens on 127.0.0.1 and ::1; iproxy was only checked to be installed). The bridge and the app were driven end to end in the simulator with `--direct`.

## Limits worth knowing

* One engine session at a time: "Another listening session is open" means a previous session has not timed out (about a minute) or a laptop listener is running.
* The transcript on screen is the last words the engine returned, held in memory only; Stop leaves the last verdict until you tap Clear screen.
* Debug builds accept launch arguments (`-DSInjectWAV`, `-DSDemo`, `-DSToken`, `-DSPort`, `-DSAutoStart`, `-DSResetConsent`) for testing; they are compiled out of Release.
* The app icon and launch mark come from `design/logo` (the same mark as Android). The font is Outfit (OFL), converted to static TTFs; no network.

## Blocked numbers (Call Directory extension)

The app has a "Blocked numbers" card and sheet (add by typing a number, remove, a note per number) and an embedded Call Directory extension, `CallBlocker` (`CXCallDirectoryProvider`), that gives iOS the list as blocking entries. Design, privacy and limits: `docs/BLOCK-SPAM.md` (on the backend PR). The list is the user's own, local, never uploaded, and there is no database of known spam numbers, so only numbers you add are blocked.

**Turn it on once on the phone:** Settings > Phone > Call Blocking & Identification > switch on Tell Call Blocker (the sheet has an Open Settings button). iOS blocks nothing until you do. After that the app calls `reloadExtension` on every change.

**How the list reaches the extension (verified on this Mac with the owner's free Personal Team; build only, not on the phone):**

* App Groups: a build signed with an App Group entitlement is rejected on the free team ("Provisioning profile ... doesn't match the entitlements file's value for the com.apple.security.application-groups entitlement"). So the default build does not use one. `Entitlements/App.appgroup.entitlements` and `CallBlocker.appgroup.entitlements` are kept for a paid team (`DS_ENTITLEMENTS_APP=... DS_ENTITLEMENTS_EXT=...` on the xcodebuild line); the code uses the App Group container automatically when it exists.
* Fallback (the default): Keychain Sharing. Both targets are signed with `Entitlements/Keychain.entitlements` (group `<TeamID>.dev.doublespeak.shared`), which the free team signs (the device build succeeded and `codesign -d --entitlements` shows the group on the extension). The app mirrors only the sorted numbers (no notes) into one keychain item, "after first unlock, this device only", and the extension reads it. The full list with notes stays in the app's own file under iOS Data Protection.
* If a build has neither, the sheet says "Not connected to call blocking" instead of pretending.

**Not verified:** nothing was installed on the phone. That the keychain item is really readable from the extension at runtime on the free team, and that iOS lists Tell Call Blocker under Call Blocking & Identification, still need a test on the real phone (add a number, enable it, call from a second phone). Limits that remain: exact numbers only (no prefixes), hidden numbers cannot be matched, it never runs during a call, and a Personal Team build still expires after 7 days.

Done here: simulator `xcodebuild ... test CODE_SIGNING_ALLOWED=NO` passes 31 tests (the original 23 plus 8 for the block list); `generic/platform=iOS ... CODE_SIGNING_ALLOWED=NO build` succeeds; a signed device build with `DEVELOPMENT_TEAM` set also succeeds (no install).
