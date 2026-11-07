# macOS call audio capture (`tap_audio`)

Captures the Mac's system audio mix with a Core Audio process tap (macOS 14.4+),
before it reaches any output device. No virtual driver (BlackHole etc.) is needed and
it works whatever the output is (speakers, AirPods). Output is a 16 kHz mono 16-bit WAV,
which is what the engine wants.

Everything stays local. This tool records ALL system audio (or one app with `--process`).
Recording or analysing a call may need the other party's consent depending on where you are.

## Build

```
cd tools/macos/tap_audio
swift build -c release
.build/release/tap_audio --self-test     # resampler + WAV writer check, no audio capture
```

The `Info.plist` in that folder (with `NSAudioCaptureUsageDescription`) is linked into the binary.

## Use

```
tap_audio --seconds 15 --out /tmp/call.wav             # whole system mix
tap_audio --seconds 15 --process FaceTime --out x.wav  # one app (name or bundle id, helpers included)
tap_audio --list                                       # processes producing audio right now
tap_audio --stream | your_consumer                     # raw PCM16 16 kHz mono on stdout (Ctrl-C to stop)
```

It refuses to run without `--out` (or `--stream`). A live level meter prints to stderr every
0.5 s, then a summary (duration, peak, RMS, SILENT or audio present).

Exit codes: 0 ok; 2 only silence captured; 3 permission/API failure or `--process` not found; 64 bad arguments.

Per-app caveat: `--process` taps the process objects that exist when you start. An app that
starts a new process mid-capture is not followed. For a call, prefer the default whole-mix tap.

## Permission

macOS asks once: the terminal you run it from (Terminal, iTerm, VS Code, Claude Code ...) is
the "responsible process", so the prompt and the entry are attributed to that terminal, not to
`tap_audio`. Allow it, or enable it in System Settings > Privacy & Security >
"Screen & System Audio Recording" (the "System Audio Recording Only" / "Audio Capture" list),
then quit and reopen the terminal.

If permission is missing, macOS usually delivers silence rather than an error, so the tool
exits 2 and prints this hint.

What was observed on the dev Mac (macOS 27.0.1, run from Claude Code): the first run started
capturing immediately with real audio, exit 0. No prompt could be clicked or seen by the
agent, so the prompt text is unrecorded; the host app appears to have had access already.
On your Mac, if the first run says "only silence" while sound is playing, that is the
permission: enable your terminal in the list above and rerun.

## End-to-end test during a real iPhone call

1. Start the engine (`make api` or however you normally do; check `curl localhost:8000/health`).
2. Answer the iPhone call on the Mac (Phone or FaceTime app) so the caller plays through the Mac.
3. While they speak, run:
   `tools/macos/tap_audio/.build/release/tap_audio --seconds 15 --out /tmp/call.wav`
   Watch the meter: it should move when the caller talks.
4. `curl -F audio=@/tmp/call.wav http://localhost:8000/analyze`
   or upload `/tmp/call.wav` in the web UI at http://localhost:5173.

Success: exit 0, "audio present", peak well above 0.01 and RMS above about 0.005 while they talk,
and the meter moves with their voice. Silence: exit 2 / "SILENT" / flat meter at -120 dBFS ->
permission not granted, call audio not routed through the Mac, or the call is muted.

Note: your own microphone is not in the system mix, only what the Mac plays (the caller).
Other sounds playing (music, browser tabs) are mixed in; pause them or use `--process`.

## Verified on the dev Mac

Quiet 1 kHz tone via `afplay -v 0.3` with AirPods Pro as the default output: global tap peak 0.39
(includes other ambient audio), dominant frequency 1000 Hz; `--process afplay` peak 0.1500, exactly
0.5 x 0.3. `say` speech: peak 0.75, RMS 0.134, varying envelope. The WAV is accepted by `/analyze`.
Not verified: a real Continuity call, the first-run prompt.
