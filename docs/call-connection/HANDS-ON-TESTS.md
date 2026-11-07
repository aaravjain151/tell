# Getting real call audio into Doublespeak: hands-on tests

Written 2026-11-07 from two research passes (sources in the PR). **Nothing below has been run on real hardware yet.** "Verified" means read from a primary source; the routing questions can only be answered by these tests. Whoever runs one: write the result in the matching GitHub issue, including the sample rate and whether the level meter moved.

## What decides the demo
| Path | Device | You get | Confidence it works | Fallback |
|---|---|---|---|---|
| Continuity + BlackHole | iPhone + Mac | caller voice (call plays on the Mac) | ~80% | speakerphone next to the Mac mic |
| Phone Link call + system audio | Android (or iPhone over Bluetooth) + Windows | caller voice, IF Windows plays it on the default output | ~55%: unverified routing | VB-Cable; then a replayed call |
| Phone on speaker + page on the phone over USB (`adb reverse`) | Android | room mic: speaker + your own voice; the mic may be silenced during a call | ~35% for useful audio | laptop mic next to the phone |
| Replayed scripted call over system audio | any | clean audio, no real call (say so on stage) | ~99% | none needed |

Always keep the replay path ready. If a live route fails, say "the call-audio route is being validated" rather than faking it.

## Test A: Windows laptop + Android phone (about 30 min)
1. Settings > Bluetooth & devices: Bluetooth on; phone is Android 10 or later.
2. Phone Link > Calls > Get started; allow the prompt on the phone and match the PIN (or Phone Link > Settings > Features > Calls > "Allow this app to make and manage calls").
3. Settings > System > Sound: write down the default output and input.
4. Run `pip install PyAudioWPatch` then `python -m pyaudiowpatch` and note the "[Loopback]" entry for the default output.
5. Record that loopback device (the package's example `pawp_record_wasapi_loopback.py`).
6. Place a call from Phone Link to a second phone; have the callee say "one two three".
7. SUCCESS: the WAV contains the callee's voice. SILENCE: flat zero. Check Phone Link > Settings > Features > "Hear audio from" is Computer.
8. Chrome variant: open the Doublespeak page, Share > Entire screen > tick "Also share system audio", confirm the meter moves.
9. If silent, install VB-Cable, set CABLE Input as the default playback device, pick CABLE Output as the input, repeat. Still silent means Phone Link audio bypasses the Windows render path: use the replay path.
10. Note: 8 kHz or 16 kHz? any echo? is the callee's side of YOUR voice clean?

## Test B: Mac + iPhone (about 20 min)
1. Same Apple Account on both, same Wi-Fi, Bluetooth on.
2. iPhone: Settings > Phone > Calls on Other Devices > allow the Mac. Mac: FaceTime > Settings > General > Calls from iPhone.
3. `brew install --cask blackhole-2ch`. In Audio MIDI Setup create a Multi-Output Device = real speakers + BlackHole 2ch, make it the Mac's sound output.
4. Doublespeak page > Audio source > pick "BlackHole 2ch" > Check level.
5. Call the iPhone from a second phone, answer on the Mac. SUCCESS: the level meter moves with the caller's voice. SILENCE: the call is still on the iPhone, or the Multi-Output Device is not the system output.
6. Record 10 s, analyse; compare the verdict with the same call replayed through the speakers.

## Test C: the Android phone itself (3 experiments)
1. Mic during a call: speakerphone call, run an AudioRecord (VOICE_RECOGNITION, then UNPROCESSED) in a microphone foreground service, log `isClientSilenced`, RMS and keep a recording. Is the far end audible, silent, or only the room?
2. Tunnel: `adb reverse tcp:8000 tcp:8000`, open `http://localhost:8000?api=http://localhost:8000` in Chrome on the phone, try the Check level button, then record with the screen locked for 5 minutes. Measure dropouts.
3. On-device timing (only if time): sherpa-onnx Moonshine Tiny / Whisper Tiny and an ONNX Runtime Mobile model; record seconds per 4 s window, RAM, temperature.

## What each path can and cannot honestly claim
- Phone Link and Continuity: the user takes the call on the PC/Mac; Doublespeak hears the caller through the computer's audio. It does not hear a call that stays on the phone.
- Android app: an ordinary app never gets call audio (VOICE_CALL needs a system permission; the mic is often silenced in a call). Speakerphone mode only, labelled as such. Real two-sided audio needs an OEM or dialer partnership, a Bluetooth hands-free box, or Phone Link to a PC.
- Never claim: it hears both sides of a normal call; it works without speakerphone on Android; "fully on-device" for the phone; reliable deepfake detection on phone-call audio (8 kHz codecs are untested); that it beats Pixel/Samsung scam detection.

## Android app: what it would be
| Shape | Hears | Effort for a team new to Android | Verdict |
|---|---|---|---|
| Chrome on the phone over `adb reverse` | speakerphone mic | 1-2 h (reuse the web UI) | safest demo; the mic may be silenced in calls |
| Thin capture client (Kotlin or Capacitor) to the laptop over USB only | speakerphone mic | Capacitor 4-6 h, Kotlin 10-14 h | possible tomorrow if experiment 1 shows audio |
| Full on-device app | speakerphone mic | 3-6 weeks | the anti-spoof model is the blocker: Pellav2 is 600M parameters; a layer-7-truncated XLS-R (~101M params, published In-the-Wild EER 6.6%) in ONNX Runtime Mobile is the evidenced route, unmeasured on a phone; Whisper Tiny via sherpa-onnx runs at RTF ~0.07 on a 2019 phone; a 0.5-1.5B LLM via LiteRT-LM is feasible for a simple judge |
Phases: 0 tomorrow = phone mic over USB to the laptop engine; 1 = move STT, regex/behavioural features, a truncated int8 voter and a small LLM onto the phone; 2 = OEM / dialer partnership or a Bluetooth box.
