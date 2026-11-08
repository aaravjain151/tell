# Run of show — Sunday 11:00 (5:00)

Live demo on the Mac. One speaker. One operator. One teammate offstage with a phone. The page the room sees is `http://127.0.0.1:5173`. The engine stays on this laptop.

Leave Wi-Fi on so Calls on Other Devices can ring the Mac. The detector is the loopback engine (`make demo` forces offline models). Do not click **Speak verdict**. Do not click **Start listening now** (that records the laptop mic for 30 seconds; the call path is the terminal listener).

## Pre-flight — done by 10:50

Run from the repo root. Tick each line out loud.

- [ ] **Engine ready.** `make demo` is already running. The terminal printed `Tell demo · UI http://localhost:5173 · API http://localhost:8000/health`. In a second terminal:

  ```bash
  curl -s http://127.0.0.1:8000/health | python3 -c "import json,sys; h=json.load(sys.stdin); e=h['egress']; n=h['os_network']; print(h.get('ok'), h.get('offline_models'), e.get('caller_audio_bytes_sent'), e.get('bytes_sent_external'), n.get('os_check'), n.get('os_outbound_count'))"
  ```

  Read `True True 0 0 ok 0` (`ok`, offline models, caller-audio bytes sent, external bytes sent, OS check, OS outbound count).

- [ ] **Pellav2 on.**

  ```bash
  curl -s http://127.0.0.1:8000/ready | python3 -c "import json,sys; p=json.load(sys.stdin)['components']['pellav2']; print(p['status'], p['detail'])"
  ```

  Status must be `ready`. If it prints `cached but not loaded yet`, play one short clip through the listener (command in the staged-bot step), then run the curl again before the room fills. If it prints `off` or `not cached`, stop. Pellav2 is not on. Do not go on stage on the behavioural tells alone without saying so.

- [ ] **Volume up. No AirPods.** Menu bar sound output is **MacBook Speakers**. Volume near three-quarters. Disconnect AirPods. Bluetooth audio devices are off. Play a one-second check: `afplay /System/Library/Sounds/Glass.aiff` and hear it from the laptop, not from a headset.

- [ ] **Permissions.** System Settings → Privacy & Security → Screen & System Audio Recording. The terminal app that will run the listener is enabled. If you had to toggle it, quit that terminal and open it again. Binary exists:

  ```bash
  test -x tools/macos/tap_audio/.build/release/tap_audio && echo tap_ok
  ```

  If that prints nothing: `cd tools/macos/tap_audio && swift build -c release`, then return to the repo root.

- [ ] **Page open.** Chrome at `http://127.0.0.1:5173`. Headline is **Waiting for a call**. Top chip reads **On this machine · 0 B out**. Click the theme control until the page is dark. Hide the bookmarks bar. Zoom until the headline fills the projector. Scroll is at the top.

- [ ] **Listener running.**

  ```bash
  python3 tools/macos/listen.py --watch --i-understand
  ```

  You see `watching for a call (apps: FaceTime, Phone, callservicesd, avconferenced, zoom.us, WhatsApp, Microsoft Teams); not listening yet` and then `not listening (waiting for a call app)`. You do **not** see `SAVING AUDIO TO DISK`.

- [ ] **Phone path.** Same Apple Account. iPhone: Settings → Phone → Calls on Other Devices → this Mac allowed. Mac: FaceTime → Settings → Calls from iPhone on. At 10:50 the teammate calls once. The Mac banner appears. Click **Answer**. Terminal prints `call detected` and `=== LISTENING`. The page leaves **Waiting for a call**. Hang up. Terminal returns to `not listening (waiting for a call app)`. Page is back at the top for 11:00.

- [ ] **Staged clip on disk.** `ls data/calls/qwen3tts/casual_clone.wav data/calls/qwen3tts/scam_bank_otp.wav` prints both paths. A TextEdit window is parked off the projector, 80 pt, reading:

  ```text
  TEST ATTACKER
  Fictional scenario
  Disclosed Qwen voice
  recorded demo
  ```

## 11:00:00–11:00:20 — Open on the empty page

**Do.** Projector shows **Waiting for a call**. No clicks.

**Say.** "You answer a call. You cannot tell if the voice is a person or an AI. You cannot tell if it is a scam. Tell listens on this Mac and gives you those as two separate answers, with the evidence in plain words. It does not speak to the caller."

**Fallback.** Page says **Not connected to the Tell engine**: operator Ctrl-C `make demo`, start it again, refresh the browser. Speaker repeats the two sentences. Do not describe a verdict you cannot see.

## 11:00:20–11:02:10 — Live call (teammate, real voice)

**Do.** Nod. Teammate calls the iPhone. On the Mac, click **Answer** on the call banner. Leave the call up. When the 2×2 appears, point at the filled cell, then at one line under **Why we think so**. Do not scroll yet.

**See.** Terminal: `call detected`, then `=== LISTENING (tap) | analysed in memory on this machine, nothing recorded or sent`. Page: listening bar with a timer. A new card about every 3 seconds. Grid labels: rows **Human voice** / **AI voice**, columns **Not scam** / **Scam**. The line under the grid is one sentence. A change of answer shows **Changed to …** with a time.

**Say.** "This is a teammate who agreed to be called. The iPhone rang, and we answered on the Mac through Calls on Other Devices. The listener started by itself when the call played. One answer is the voice: human or AI. The other answer is the wording: scam pattern or not. This line is the evidence. It refreshes about every 3 seconds, and it can change before we hang up. Tell can be wrong."

**Fallback.**

- No Mac banner: on the iPhone, confirm Calls on Other Devices, call again. If the second try fails, skip to the staged bot and say: "The live phone route did not come up. The next sound is a recorded demo, labelled TEST ATTACKER. It is a fictional call."
- Terminal says `hearing SILENCE`: confirm MacBook Speakers, volume up, AirPods disconnected. Hang up and call again. If it stays silent, use the staged-bot fallback below.
- `=== LISTENING` but the page stays on **Waiting for a call**: refresh `http://127.0.0.1:5173`. Chip must say **On this machine**.
- Card stays on warming well after the caller has been talking: keep the call up and say "It waits until it has enough speech, then it answers." Do not click **Start listening now**.

## 11:02:10–11:03:40 — Staged bot through the speakers

**Do.** Teammate hangs up. Wait until the terminal says `call ended: stopping` and `not listening (waiting for a call app)`. Operator Ctrl-C that watcher, then:

```bash
python3 tools/macos/listen.py --now --i-understand
```

When the terminal shows `=== LISTENING`, drag the TextEdit label **TEST ATTACKER** onto the projector beside the page, and play:

```bash
afplay data/calls/qwen3tts/casual_clone.wav && afplay data/calls/qwen3tts/scam_bank_otp.wav
```

Point at the grid when the sentence changes. Hang nothing up; this audio is the laptop speakers, not a phone call.

**Say.** "Label on screen: TEST ATTACKER. Fictional scenario. Disclosed Qwen voice. This is a recorded demo, not a person and not a real scam. It starts as ordinary talk and moves into a request for a verification code. Watch the two answers. They are allowed to change mid-call."

**Fallback.**

- Either wav is missing: Ctrl-C `--now`. Restart `python3 tools/macos/listen.py --watch --i-understand` so the page is idle. Click **More**, then **Grandparent scam**. Say: "Stored sample. Not a live call." The provenance line must say it is a stored sample. Do not call it live.
- `afplay` is silent: output device and volume again. If the room still cannot hear it, leave the page up and say the verdict from the screen: "You cannot hear the speakers. The card is still the engine on this machine."
- Grid does not move to a scam cell: read whatever sentence is on screen. Say "That is the answer it gave. We do not override it." Do not refresh to hunt a red cell.

## 11:03:40–11:04:30 — Counter

**Do.** Scroll to **bytes of caller audio sent off this device**. Leave the big **0** in frame. Operator runs the health curl from pre-flight again and leaves the six numbers visible in a corner terminal.

**Say.** "Caller audio bytes sent off this device: 0. External bytes sent: 0. The operating system reports 0 outbound connections from the engine (`os_check` ok, `os_outbound_count` 0). The audio was analysed in memory on this Mac. Tell does not speak to the caller."

**Fallback.** If any of those three numbers is not 0, or `os_check` is not `ok`: "That counter is not at 0. We will not talk past it." Point at the number that is there. Move to the close.

## 11:04:30–11:05:00 — Close

**Do.** Ctrl-C the listener if it is still in `--now`. Projector back on the page, including the line **Tell can be wrong.**

**Say.** "In a small informal test of about 10 audio clips, the team judged 9 correct. That is a small informal test, not a rate. If a call asks for money or a code, hang up and call back on a number you already have."

**Fallback.** Clock is over: stop after "Tell can be wrong." The measurement sentence can move to questions.

## Say this / Do not say this

| Say this | Do not say this |
|---|---|
| On this Mac. On your own device. | "Fully shipped." "Works on all devices." "100% private." |
| Two answers: human or AI, and scam pattern or not, plus the evidence line on screen. | "Detects all." "Fraud confirmed." "Provably" anything. |
| The listener starts by itself when a call plays. The card updates about every 3 seconds and can change mid-call. | "It catches the scam immediately." |
| Caller-audio bytes sent: 0. External bytes: 0. OS outbound count: 0. It does not speak to the caller. | "Safe." "Legal." "Illegal." |
| iPhone calls are covered when you answer them on the Mac. An iPhone app exists and is coming. iOS gives apps no call audio. | "The iPhone app hears the call." |
| Android early access (speaker mode). Real-call behaviour is not verified yet. | "Android works on a normal call." |
| Google Scam Detection on-device, Hiya AI Phone, and Truecaller also do real-time or on-device scam detection. | "Only." "First." "Better than Truecaller, Hiya, or Google." |
| In a small informal test of about 10 clips, the team judged 9 correct. | Any accuracy percentage. |
| We evaluated and fine-tuned an open-source detector head on many speakers. It helps on speaker-replay audio. It is not in the shipped detector yet. | "The fine-tune is in today's build." |
| TEST ATTACKER. Fictional scenario. Disclosed Qwen voice. Recorded demo. | A real victim, a real scammer, or unlabelled AI audio. |
| Tell can be wrong. Hang up and call back on a number you already have. | "You are fine to keep talking." |
