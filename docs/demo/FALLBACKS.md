# Fallbacks: what to do when a step fails

Rule for every fallback: say out loud what the room is now seeing ("recorded", "stored sample", "replay"). Never present a replay as live. Never refresh the page or re-run a clip to hunt for a red cell. If the screen shows something unexpected, read it and say "that's the answer it gave".

All commands run from `~/Downloads/tell` unless noted. Set these once in every terminal during preflight:

```bash
cd ~/Downloads/tell
PY=.venv/bin/python
CALL=$(ls -t ~/Downloads/voice-talk/qa_out/demo_escalating_scam_test_*/call.wav | head -1)   # newest recorded attacker run
```

`$CALL` is a real recording of the voice-talk attacker (bot side only, about 92 s, fictional "Example Bank" wording). Round 1 of the rehearsal records a fresh one with the voice you will use on stage.

## Step V: record the backup video (at rehearsal, once)

QuickTime Player > File > New Screen Recording, then record the whole screen during the best full rehearsal run (round 3). Save it as `~/Desktop/tell-demo.mov`. Keep the run even if a verdict is unsurprising. Also take four screenshots (Cmd-Shift-4) into `~/Desktop/tell-shots/`: `1-waiting.png`, `2-attacker-red.png`, `3-human.png`, `4-zero.png`. In the video the attacker portion carries the TEST ATTACKER bar the whole time. If you play the video on stage, say "This is a recording from this morning's rehearsal."

## 0. Before anything: the page says "Not connected to the Tell engine"

1. Operator: Ctrl-C `make demo`, run `make demo` again, wait for the banner line, then refresh Chrome (Cmd-R).
2. Run `python3 scripts/demo_preflight.py --no-session`. Pellav2 may need a warm-up replay: `$PY tools/macos/listen.py --file data/calls/qwen3tts/casual_clone.wav --i-understand`.
3. If it is not back in 60 s, play the backup video (step V) and narrate over it. The speaker lines stay the same, with "recorded" added.

## 1. Hook and problem

There is nothing to fail except the page. See step 0. If the projector is dead, give the hook and the problem without slides. They work without a screen.

## 2. Wi-Fi toggle (segment 5 only)

Wi-Fi stays on through both demos and goes off only in the privacy proof, after the iPhone call has ended.

- The Wi-Fi menu does not respond in segment 5: skip it. Drop the "Wi-Fi is off now" sentence and show the counter and terminal C only.

## 3. Live demo 1: the TEST ATTACKER

| Symptom | Do this | Say |
|---|---|---|
| Terminal B never prints `=== LISTENING` | Ctrl-C, then run `$PY tools/macos/listen.py --now --i-understand` again. If it prints `hearing SILENCE` later, the tap permission is off: switch to the `--file` path in the last row. | "One second." |
| voice-talk does not start, or the bot is silent | Check that the voice-talk tab shows no error and that Ollama is running (`curl -s 127.0.0.1:11434/api/tags`). Do not debug on stage. Replay the recorded run through the speakers while terminal B listens: `afplay "$CALL"` | "Here's the same test bot, recorded this morning. Still the TEST ATTACKER, fictional." |
| The bot's reply takes more than 4 s | Press **Escalate**: stage lead lines are cached and play at once. | (nothing) |
| The bot drifts off script | Press **Escalate**. The next line is a fixed canned line. | (nothing) |
| No red by 1:30 | Do not replay or refresh. Read the screen. | "It hasn't gone red. It needs two scam signs that agree before it alerts. We don't override it." |
| Room cannot hear the bot (speakers dead) | Ctrl-C terminal B. Stream the recording straight to the engine, in real time, with no speakers involved: `$PY tools/macos/listen.py --file "$CALL" --i-understand`. The card still updates. | "You can't hear it, but the engine is getting the same recording. Watch the card." |
| The attacker app is down and `$CALL` is missing too | Stored test clips, Qwen voice: `afplay data/calls/qwen3tts/casual_clone.wav && afplay data/calls/qwen3tts/scam_bank_otp.wav` while terminal B listens. Note that this script names a real brand ("Amazon security"), so call it a test script, not a fictional brand. | "These are stored test clips of a cloned voice. A test script, not a real call." |
| Nothing at all works | Page > **More** > **Grandparent scam**. The provenance line says it is a stored sample. | "Stored sample, not a live call." |

## 4. Live demo 2: a real human

**4a. The iPhone call does not reach the Mac within 15 s** (no banner, or Answer does nothing). Sanath hangs up. Do not try a second time on stage. Go to 4b if the Android phone is set up, otherwise 4c.

**4b. Plan B: Android over USB** (works with Wi-Fi off; the phone is the ears, the laptop is the brain). This only works if it was set up in preflight: phone plugged in, `adb devices` shows `device`, `adb reverse tcp:8000 tcp:8000`, and the engine started with `make api-android` instead of `make demo`, because the installed app's origin needs it (see `docs/android/ANDROID.md`). Aarav opens Tell on the Android phone and taps **Start listening**. Sanath walks over and talks next to the phone for 25 s, using the same lines. Show the phone's verdict to the room by holding it up (no screen mirroring is installed; `scrcpy` is absent). Say: "Same engine, the phone is just the ears, over the cable." Speaker-mode audio is a mix of voices, so the engine caps "how sure" at 0.6. Expect "not sure" more often here.

**4c. Plan C: replay Sanath's real recording** (no call, no network). Terminal B: `$PY tools/macos/listen.py --now --i-understand`, then `afplay data/calls/human/sanath/long_checkin.wav` (26 s, his real voice; `morning_routine.wav` is 30 s). Ctrl-C terminal B afterwards. Say: "This is Sanath's real recorded voice, not a live call: same voice the attacker copied." Read the card.

**4d.** The card stays on warming up: keep Sanath talking ("Keep going, Sanath"). Tell needs about 8 s of speech and 20 words before it answers. Never click **Start listening now**.

**4e.** Terminal A shows `=== LISTENING` but the page stays on **Waiting for a call**: press Cmd-R on the page. The chip must say **On this machine**.

**4f.** Sanath's call is shown as **AI voice** (a false alarm): say so plainly. "That's a false alarm on a real person, on a phone line. That's exactly why we show the evidence and say Tell can be wrong." Do not repeat the call.

## 5. Privacy proof

- The terminal C one-liner errors: run `curl -s http://127.0.0.1:8000/health` and read the raw JSON numbers.
- Any number is not 0, or os_check is not `ok`: "That number is not zero. We won't talk past it." Point at it. Do not explain it away on stage. Q&A can cover it. `os_outbound_seen` in `/health` lists what the OS saw.
- The page counter is off screen or missing: show terminal C only.

## 6–11. Talk segments

Nothing technical can fail. If a speaker blanks, Aarav says that speaker's one-line summary: how it works = "Pellav2 for the voice, Whisper and a small local model for the words, all on your own computer"; Gradium = "Sanath cloned his voice in Gradium for our test scripts; Gradium got our script text, never a caller".

## Total failure

Play `~/Desktop/tell-demo.mov` full screen (QuickTime, Cmd-F) and give the script over it. Afterwards, offer judges a live run at the table during Q&A. If the video is also missing, use `~/Desktop/tell-shots/*.png` in order.

## Reset between rehearsal runs (and after a failed attempt)

```bash
# stop terminal B if running (Ctrl-C), then:
curl -s -X POST http://127.0.0.1:8000/panic -H 'Origin: http://localhost:5173'   # wipes live sessions, the block list and feedback (export the block list first if it matters)
# page: Cmd-R, scroll to top; voice-talk: Stop, reload, re-tick Demo mode + set + auto-advance off
```

`/panic` also deletes the local block list and feedback files (`docs/BLOCK-SPAM.md`). On the demo Mac that is fine. Elsewhere, export first.
