# Tell for Android: native wrapper (Capacitor)

Wraps the PWA in `apps/android/` (bundled into the APK, not loaded from a server) and adds a microphone foreground service. The APK is a thin client: audio goes only to the engine on the owner's computer through `adb reverse tcp:8000 tcp:8000`. Speaker mode only (Android gives apps no call audio).

Built and installed on a Galaxy S20 FE (Android 13) as a debug APK. Not built: a release/signed-for-store build.

## What is native here

* `capacitor.config.json`: `dev.doublespeak.app`, `androidScheme: http`, `hostname: localhost` (the page's origin is `http://localhost`; the engine must allow it: `make api-android`). No `server.url`, so no remote content.
* `android/app/src/main/AndroidManifest.xml`: permissions `RECORD_AUDIO`, `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MICROPHONE`, `POST_NOTIFICATIONS`, `READ_PHONE_STATE` (auto-listen only) (+ `INTERNET` to open a socket, `VIBRATE`, `WAKE_LOCK`, `MODIFY_AUDIO_SETTINGS`). `usesCleartextTraffic=false`; `res/xml/network_security_config.xml` allows cleartext to `localhost` and `127.0.0.1` only.
* `ListenService` + `ListenServicePlugin` (Java): the page calls `Capacitor.Plugins.ListenService.start()` after `getUserMedia` succeeds and `stop()` on Stop. The service only shows the "Tell is listening" notification and holds the `microphone` foreground-service type so capture survives the screen locking; capture itself stays in the WebView.
* Auto-listen (opt-in, off by default; `docs/android/ANDROID.md` "Auto-listen"): `READ_PHONE_STATE` asked when the user turns it on, a `PHONE_STATE` receiver disabled until then, `TelephonyCallback.CallStateListener` (12+) / `PhoneStateListener`, and `CallListenService`, a second microphone foreground service that captures natively (AudioRecord, 16 kHz PCM16) and streams to the engine on 127.0.0.1:8000 with plain Java sockets. Logic in `call/` is pure Java with JVM unit tests: `cd android && ./gradlew testDebugUnitTest`.
* Adaptive launcher icon and splash from the repo logo (`design/logo`), navy `#0B1020`.

## Build (JDK 17 + Android SDK 34)

```
export JAVA_HOME=/opt/homebrew/opt/openjdk@17
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
export PATH=$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH
cd apps/android/native
npm install
echo "sdk.dir=$ANDROID_HOME" > android/local.properties
npm run apk                      # build:www, cap sync, gradlew assembleDebug, copies to ./app-debug.apk
adb install -r app-debug.apk
```

`app-debug.apk`, `node_modules/`, `www/` (copied shell), `android/local.properties` and Gradle outputs are git-ignored. Never commit an APK or a keystore.

## Honest limits

* Foreground service keeps the microphone running with the screen locked, but Android can still silence the mic for other apps during a phone call. Unverified on a real call.
* No on-device models. If the engine or the cable is gone the app shows the connection screen and cannot judge anything.
* `INTERNET` is required by Android to open any socket, including loopback; the network security config is what keeps it to localhost.
* Capacitor 6 is pinned (compileSdk 34). Capacitor 7 needs compileSdk 35.
