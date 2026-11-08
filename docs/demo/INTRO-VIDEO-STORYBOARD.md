# Intro video storyboard — 55 seconds

Record the real app. Do not build a fake interface, a fake verdict, or a fake counter. Any shot of a staged clip or a stored sample carries the on-screen label `recorded demo` for the whole shot. Caller voices are a consenting teammate, or the disclosed Qwen voice with the TEST ATTACKER label. No other voices.

**Music:** low, steady, no lyrics, no hit on a cut, no siren. Sit under the voiceover so the UI words stay intelligible. Mood is calm and specific.

**Frame:** 1920×1080, the real Chrome window on `http://127.0.0.1:5173`, dark theme, bookmarks bar hidden. Room tone out. Voiceover recorded by a teammate after the pictures are locked, so the words match the frames.

## Shot list

| Time | Picture (real) | On-screen text | Voiceover |
|---|---|---|---|
| 0:00–0:07 | Mac on a table, iPhone beside it, screen recording starts on **Waiting for a call**. No stock footage. | Who is on this call? | "You answer. You cannot tell if the voice is a person or an AI. You cannot tell if it is a scam." |
| 0:07–0:16 | Same recording. A real call banner, click **Answer**, terminal in a corner flips to `=== LISTENING`. Use a consenting teammate on Calls on Other Devices. | Listens live, on this Mac | "Tell hears the call on your own Mac. The listener starts by itself when the call plays. It does not speak to the caller." |
| 0:16–0:28 | Stay on the real page as the card updates. Show the 2×2 and one **Why we think so** line. If this stretch is the staged clip instead of the teammate, the `recorded demo` label is already up. | Human or AI. Scam pattern or not. | "About every 3 seconds it answers two questions, and it shows the evidence in plain words. The answer can change while the call is still going." |
| 0:28–0:40 | Cut to the staged playback (capture notes below). The TextEdit card is in frame the whole shot. The grid sentence changes on the real page. | `recorded demo` / TEST ATTACKER / Fictional scenario / Disclosed Qwen voice | "This clip is a recorded demo. TEST ATTACKER. A disclosed Qwen voice. A fictional script. Watch the two answers move." |
| 0:40–0:48 | Scroll, in the same session, to the real **0** and the caption **bytes of caller audio sent off this device**. Corner terminal shows the health numbers from the capture notes. | 0 bytes of caller audio sent | "Caller audio bytes sent off this device: 0. The operating system reports 0 outbound connections from the engine." |
| 0:48–0:55 | Hold the real page. Title cards are typed text over that recording, not a drawn phone. | Mac: live · Android early access (speaker mode) · iPhone app coming | "Android is early access, speaker mode, and a real call there is not verified. An iPhone app is coming. iOS gives apps no call audio. Tell can be wrong." |

Total 55 seconds. If the edit runs long, drop the platform line before you drop the counter or the caveat.

## How to capture the screen

Do this on the demo Mac. One rehearsal, then one take. Keep the take even if a verdict is unsurprising. Do not reshoot until the card "looks right."

1. From the repo root, start `make demo`. Wait until `curl -s http://127.0.0.1:8000/health` shows `offline_models` true and the byte and OS counts at 0. Confirm Pellav2 with `curl -s http://127.0.0.1:8000/ready` and `components.pellav2.status` equal to `ready`.
2. Chrome → `http://127.0.0.1:5173`. Dark theme. Zoom until **Waiting for a call** is readable at 1920×1080. Hide bookmarks.
3. QuickTime Player → File → New Screen Recording. Record the browser plus a narrow strip of terminal. This is the footage. Do not recreate the page in an editor, and do not paste a screenshot into a mock phone.
4. **Teammate shot (0:07–0:16).** In a terminal: `python3 tools/macos/listen.py --watch --i-understand`. Output device is MacBook Speakers, AirPods disconnected, volume up. Teammate calls the iPhone. Click **Answer** on the Mac banner. Record through the moment the 2×2 appears. The teammate has agreed to be recorded. Hang up. Confirm the terminal says `not listening (waiting for a call app)`.
5. **Staged shot (0:28–0:40).** Ctrl-C the watcher. Start `python3 tools/macos/listen.py --now --i-understand`. When it prints `=== LISTENING`, put this TextEdit window in frame:

   ```text
   TEST ATTACKER
   Fictional scenario
   Disclosed Qwen voice
   recorded demo
   ```

   Then play `afplay data/calls/qwen3tts/casual_clone.wav && afplay data/calls/qwen3tts/scam_bank_otp.wav`. Record the real card as it updates. Leave the `recorded demo` label up for every frame of this shot, including the counter scroll if you scroll during this take.
6. **Counter (0:40–0:48).** Without stopping the recording, scroll to the proof block. In the corner terminal run:

   ```bash
   curl -s http://127.0.0.1:8000/health | python3 -c "import json,sys; h=json.load(sys.stdin); e=h['egress']; n=h['os_network']; print(e.get('caller_audio_bytes_sent'), e.get('bytes_sent_external'), n.get('os_check'), n.get('os_outbound_count'))"
   ```

   Use the take where that print is `0 0 ok 0`. If it is not, do not composite a 0 over the picture. Say the numbers the terminal printed, or cut the counter shot.
7. **Platform cards (0:48–0:55)** are text you add in the editor on top of the real page recording. Do not film a fake Android UI or a fake iPhone app. The spoken line is the whole claim.
8. Export the screen recording untouched except for cuts, the `recorded demo` label on staged frames, the end title cards, and the voiceover. No generated "app" frames. No percentage on screen. No shot of a person in distress.

**If the live answer click fails on the day you record:** keep the failed banner out. Record the staged path for the verdict shots, with `recorded demo` and TEST ATTACKER visible from the start of that recording, and open the video on **Waiting for a call** plus the voiceover. Do not pretend a stored sample is a live call. A stored sample, if you must use one, is **More → Grandparent scam**, and the voiceover says "stored sample."
