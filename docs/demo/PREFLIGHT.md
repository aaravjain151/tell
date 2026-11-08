# Preflight: done by 10:45, re-run at 10:55

One command does the machine checks. The people checks below it are done by hand. Fix every red line; read every warning out loud and decide.

```bash
cd ~/Downloads/tell
python3 scripts/demo_preflight.py --video ~/Desktop/tell-demo.mov
```

The script is stdlib only and read-only. It talks only to loopback, never opens `.env` and changes no setting. It checks:

- the engine: `/health` (caller-audio bytes 0, external bytes 0, `os_check ok`, OS outbound 0) and `/ready` (Pellav2 ready, LLM ready, Whisper ready, nothing degraded, privacy switches)
- that only one engine owns :8000, and that the page on :5173 has the title **Tell**
- a listener dry run (`POST /session` with the page's Origin, then `DELETE`; no audio)
- the tap binary, the number of `listen.py` processes, and whether the menu bar app is running
- the voice-talk attacker app on :8765, the Ollama models, and the attacker voices' consent records
- the default audio output device and volume, the Wi-Fi state, an Android phone over adb (when one is plugged in), disk space
- the fallback assets: the stored clips, the newest recorded attacker call, the backup video

Exit code 0 means GO and 1 means at least one red line.

## Last run (Sunday prep, 2026-11-08, on the demo Mac, from this branch's worktree with `--repo ~/Downloads/tell`)

```text
Tell demo preflight

[ OK ] Engine /health: ok · caller audio sent 0 · external bytes 0 · os_check ok · os outbound 0
[WARN] Offline model mode: offline_models false: the engine was started with make api, not make demo
       fix: Ctrl-C the engine, start `make demo` (forces offline model loads). Not fatal: loads are cache-only anyway
[ OK ] Pellav2 voice check: loaded in memory on mps
[ OK ] Local LLM (Ollama): loaded in Ollama memory
[ OK ] Speech to text (Whisper): loaded in memory
[ OK ] Engine ready, nothing degraded: thresholds 2026-11-07.3
[WARN] Privacy switches: gradium_key_set true: the menu bar privacy row may say a setting could send data
       fix: For the stage run start the engine without GRADIUM_API_KEY in the environment, or be ready to say: 'the Gradium key is only for the optional spoken verdict, which we do not click'
[ OK ] One engine on :8000: ../../.venv/bin/python -m uvicorn tell.main:app --port 8000 --env-file ../../.env
[ OK ] Page :5173: title 'Tell'
[ OK ] Listener dry run: POST /session ok, session deleted again (no audio sent)
[ OK ] Audio tap built: tools/macos/tap_audio/.build/release/tap_audio
[ OK ] Listener processes: 1 listen.py running: 1353 .venv/bin/python tools/macos/listen.py --watch --i-understand
[ OK ] voice-talk attacker app: http://127.0.0.1:8765 answers
[ OK ] Ollama models: qwen2.5:3b and llama3.2:3b present
[ OK ] Attacker voice 'sanath': consent record present
[ OK ] Attacker voice 'demo-say': consent record present
[ OK ] Audio output device: MacBook Pro Speakers
[ OK ] Volume: output volume 100, not muted
[ OK ] Wi-Fi: Wi-Fi Power (en0): On (needed ON for the Calls-on-Other-Devices call in demo 2; turned OFF on cue for the privacy proof)
[WARN] Android phone (adb): no phone connected (only needed for the Android segment / plan B)
       fix: Plug in the cable, accept USB debugging, `adb devices` must say device
[ OK ] Disk space: 645 GB free
[ OK ] Fallback clips: qwen3tts casual_clone + scam_bank_otp, human/sanath present
[ OK ] Recorded attacker call: /Users/aarav/Downloads/voice-talk/qa_out/demo_escalating_scam_test_20261107-183606/call.wav
[WARN] Backup demo video: not given (--video PATH)
       fix: Record it at rehearsal (FALLBACKS.md, step V)

20 ok, 4 warnings, 0 red. GO.
```

Things to fix from that run before Sunday:

1. Restart the engine with `make demo` instead of `make api`, so `offline_models` reads true.
2. Decide on the Gradium key. For the stage run, start the engine from a shell without `GRADIUM_API_KEY` (move `.env` aside yourself; the script never reads it), or keep it and use the line from the fix.
3. Record the backup video (`FALLBACKS.md`, step V) and pass `--video`.
4. Earlier `ps` output showed stale engines from before the rename (`doublespeak.main:app` on 8000 and 8011) and several old `http.server` and voice-talk processes. Only one owned :8000 at check time, but quit the stale ones anyway so nothing surprises you: `pkill -f "doublespeak.main:app"`. Make sure **Tell.app** is not running at the same time as the terminal listeners.

## Start order (10:30)

```bash
# 1. Attacker app (separate repo)
cd ~/Downloads/voice-talk && git checkout attacker-demo && ollama serve >/dev/null 2>&1 &
cd ~/Downloads/voice-talk && .venv/bin/python run.py            # http://127.0.0.1:8765

# 2. Tell engine + page, offline models
cd ~/Downloads/tell && make demo                                # API :8000, page :5173

# 3. Warm Pellav2 and the LLM with one replay (no speakers involved)
cd ~/Downloads/tell && .venv/bin/python tools/macos/listen.py --file data/calls/qwen3tts/casual_clone.wav --i-understand

# 4. Terminal A (runs all show long)
.venv/bin/python tools/macos/listen.py --watch --i-understand

# 5. Preflight
python3 scripts/demo_preflight.py --video ~/Desktop/tell-demo.mov
```

Note: voice-talk and the iPhone USB bridge (`tools/ios/bridge.py`) both default to port 8765. Do not run the iPhone bridge during the demo.

## People and room checks (by hand)

- [ ] **Sanath confirms consent on the day** for his cloned voice in voice-talk. If not, select **demo-say** and use the ALT lines.
- [ ] **Calls on Other Devices** works on the venue Wi-Fi: iPhone > Settings > Phone > Calls on Other Devices > this Mac allowed; Mac > FaceTime > Settings > Calls from iPhone on. Sanath calls Aarav's iPhone once at 10:50. The Mac shows the banner, Answer, terminal A prints `call detected` and `=== LISTENING`, hang up, terminal A goes back to `not listening`. Venue networks sometimes block device-to-device traffic. If the banner never shows, use plan B in `FALLBACKS.md` step 4.
- [ ] **Screen & System Audio Recording** permission is on for the terminal app that runs the listeners (System Settings > Privacy & Security). A denied tap delivers silence, not an error.
- [ ] Sound output is **MacBook Pro Speakers** or the room PA, AirPods are disconnected, and the volume is about 75. `afplay /System/Library/Sounds/Glass.aiff` is audible at the back of the room.
- [ ] Mac notifications are silenced (Focus: Do Not Disturb), apart from the call banner. Check that Do Not Disturb still lets the Continuity call through. If it does not, turn it off.
- [ ] Chrome: the Tell tab is dark, zoomed, scrolled to the top and shows **Waiting for a call**. The voice-talk tab is set up as in `DEMO-SCRIPT.md` (voice, Demo mode, Escalating scam test, auto-advance off, typing input, Pre-record on). The bookmarks bar is hidden.
- [ ] Terminals B and C have their commands typed in and not run.
- [ ] Aarav's and Sanath's phones are charged and their ringers are on, except that Aarav's iPhone stays silent (the Mac rings). Laptop charger is plugged in.
- [ ] Clicker works. A timer is visible to Aarav (a phone stopwatch on the lectern).
- [ ] Do not click **Speak verdict** (Gradium cloud TTS) or **Start listening now** (30 s laptop mic) on the page.
