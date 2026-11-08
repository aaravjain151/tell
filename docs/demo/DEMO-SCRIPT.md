# Demo script: 4 minutes, Sunday 11:00

This is the script for the stage. It builds on `RUN-OF-SHOW.md` (Cursor's draft, PR #85) and replaces its Mac-first framing with the owner's positioning (phones first, the brain on your own devices). Preflight: `PREFLIGHT.md`. If a step fails: `FALLBACKS.md`. Judge questions: `QA-PREP.md`. Practice: `REHEARSAL.md`.

## Who is where

| Person | Role on stage | Says |
|---|---|---|
| **Aarav** (AARAV) | Presenter, front centre, holds the clicker. His iPhone is on the table, signed in to the same Apple Account as the Mac. | Hook, both demo narrations, privacy proof, the live system, measured, roadmap, close |
| **Samarth** (SAMARTH) | Operator at the Mac, which drives the projector. | The model (how it works) |
| **Sanath** (SANATH) | Stands at the side with his own phone. He is the voice the attacker cloned and the real caller in demo 2. | The problem, the real call, the voices and data (how it works) |

Projector layout (set in preflight): Chrome at `http://127.0.0.1:5173` on the right two-thirds, dark theme, zoomed so the headline is readable from the back. On the left third, the voice-talk tab at `http://127.0.0.1:8765`, which shows its red **TEST ATTACKER - fictional scenario** bar. Terminals sit on the laptop screen but off the projector, except terminal C, which is shown during the privacy proof.

Terminals (all from the repo root, prepared in preflight):

- **A**: `.venv/bin/python tools/macos/listen.py --watch --i-understand`. It runs the whole time. It arms by itself when a call app plays audio and ignores the browser, so it stays idle during demo 1.
- **B**: `.venv/bin/python tools/macos/listen.py --now --i-understand`, typed in but **not started** (Samarth presses Enter on cue).
- **C**: the health one-liner, typed in but not started:
  `curl -s http://127.0.0.1:8000/health | python3 -c "import json,sys; h=json.load(sys.stdin); e=h['egress']; n=h['os_network']; print('caller audio bytes sent:', e['caller_audio_bytes_sent'], '| external bytes:', e['bytes_sent_external'], '| OS outbound connections:', n['os_outbound_count'], '| os_check:', n['os_check'])"`

voice-talk setup (in preflight): voice **sanath** (if Sanath confirms on the day that he still agrees; otherwise **demo-say** and use the alternate lines marked ALT). **Demo mode** on, set **Escalating scam test**. Untick **Advance the stage by turn count**, so the operator drives each stage with **Escalate**. Input set to **typing**, with the mic off (room echo can cut the bot off, see `REHEARSAL.md`). Leave the spoken disclosure on unless the round 1 rehearsal decided otherwise; if it is off, the acknowledgement tick must be set. **Pre-record the next line** on.

Pace: about 150 words per minute. Word counts are shown so each segment can be checked against the clock.

## Timing table

| # | Clock | Length | Segment | Speaker(s) | Words spoken |
|---|---|---|---|---|---|
| 1 | 0:00–0:20 | 20 s | Hook | Aarav | 48 |
| 2 | 0:20–0:38 | 18 s | The problem | Sanath | 45 |
| 3 | 0:38–1:48 | 70 s | Live demo 1: TEST ATTACKER | Aarav (bot talks most of it) | about 85 |
| 4 | 1:48–2:30 | 42 s | Live demo 2: real human call | Aarav, Sanath | about 95 |
| 5 | 2:30–2:48 | 18 s | Privacy proof | Aarav | 45 |
| 6 | 2:48–3:24 | 36 s | How it works | Samarth, Sanath, Aarav | 36 + 37 + 28 |
| 7 | 3:24–3:42 | 18 s | What we measured | Aarav | 46 |
| 8 | 3:42–3:55 | 13 s | Phones-first roadmap | Aarav | 33 |
| 9 | 3:55–4:00 | 5 s | Close | Aarav | 8 |
| | | **240 s** | | | |

## 1. Hook (0:00–0:20)

**Screen.** Tell page on **Waiting for a call**. Top chip: **On this machine · 0 B out**.

**AARAV:** "Pick up a call. Is that voice a person or an AI? Is it your bank, or a scam? You can't tell by ear, and neither can your parents. Tell answers both questions, live, while the call is still going. The audio stays on your own devices."

## 2. The problem (0:20–0:38)

**SANATH:** "The attacker you're about to hear is me. Well, a copy of me. We recorded a short sample of my voice, and an open-source model on this laptop now says whatever it's told. I agreed to that for this demo. A scammer won't ask."

ALT (demo-say voice): "The attacker you're about to hear is a cloned voice, made from a short sample by an open-source model on this laptop. Ours is labelled and fictional. A real scammer's isn't, and some scammers are real people reading a script."

## 3. Live demo 1: the TEST ATTACKER (0:38–1:48)

| Clock | Operator (Samarth) does | Room sees or hears | Aarav says |
|---|---|---|---|
| 0:38 | Menu bar > Wi-Fi > **off** (only if the round 2 gate passed, see the note below). | The Wi-Fi icon goes empty. | "Wi-Fi off. On the left is a test bot we built, labelled TEST ATTACKER. It's fictional. On the right is Tell." (25 words) |
| 0:45 | Terminal B: Enter. Wait for `=== LISTENING`. Then click **Start session** in voice-talk. | The page shows the listening bar and timer. The bot opens: "Hi, good morning! This is Alex from Example Services..." | (silent) |
| 0:52 | Type `Yes, go ahead.` and press Enter. After the next reply, type `Fine, thanks.` and press Enter. | Friendly small talk, about 15 s of bot speech. The card leaves warming up. | In a gap: "Small talk. Tell is calm: no scam pattern." (8 words) |
| 1:08 | Click **Escalate** (stage 2). | "...I'm actually with the Example Bank Fraud Desk... case number 000-TEST." Amber can appear here. | In a gap, if amber shows: "Now it claims to be the bank. Amber." If not: "Now it claims to be the bank." |
| 1:22 | Click **Escalate** (stage 3). | "...please read me the six digit code we just texted to you." | (silent; let the room hear the ask) |
| 1:30 | When red shows: Menu bar > Wi-Fi > **on** (gate). If red has not shown by 1:36, click **Escalate** (stage 4, secrecy). | The red banner, and the 2×2 moves to the Scam column. A line under **Why we think so** names the code request. | "There. Red, mid-call: it asked for a code. Two answers: the voice, and the scam. And the evidence, in plain words." (22 words) Then ONE of the branch lines below. |
| 1:44 | Click **Stop** in voice-talk. Ctrl-C terminal B. Click **Dismiss** on the red banner. | The page returns to waiting. | (bridge) "Now a real person." |

**Branch line, read only what is on screen:**

- Voice row shows **AI voice**: "And it flags the voice as AI." (7 words)
- Voice row shows human or **not sure**: "The voice check isn't sure about this clone, and it says so. The wording caught it. That's why there are two answers." (22 words)
- The voice row reads AI only because the bot said it was automated (the disclosure is on): "It said it was automated, so the voice answer is AI because it said so." (15 words)
- No red by 1:44: "It hasn't gone red. It needs two scam signs that agree before it alerts. We don't override it." Then go on.

**Wi-Fi note.** Turning Wi-Fi off for demo 1 makes the proof stronger: the attacker and the detector both ran with no network. Wi-Fi then has to come back in time for the iPhone call to reach the Mac. Use it only if the round 2 rehearsal measured the Answer banner reliably appearing within 20 s of Wi-Fi coming back on. Otherwise leave Wi-Fi on here and switch it off in segment 5.

## 4. Live demo 2: a real human (1:48–2:30)

| Clock | Operator does | Room sees or hears | Spoken |
|---|---|---|---|
| 1:48 | (nothing) | Sanath raises his phone and dials Aarav's iPhone. | **AARAV:** "Sanath, call me." (3 words) |
| 1:52 | When the Mac banner appears, click **Answer**. | Terminal A: `call detected`, `=== LISTENING`. The page shows the listening bar. Sanath's voice comes out of the Mac speakers. | **AARAV:** "I didn't press anything in Tell. It started listening when I picked up." (13 words) |
| 1:56 | (nothing) | Sanath talks for about 25 s, steadily, with no pauses. | **SANATH** (into his phone): "Hey, it's Sanath. I'm standing right over there. Just calling to say the demo's going okay so far. Are we still getting food after this? I was thinking the noodle place on the corner. Okay, I'll stop talking now so you can see what it says." (49 words) |
| 2:20 | Point the cursor at the filled cell. | 2×2 cell and its sentence. | **AARAV** (read the screen): "Sounds human. No scam pattern. Same voice the attacker copied, two different answers." (13 words) If it shows **not sure**: "On a phone line the voice check is less sure, and it tells you that instead of guessing." (18 words) |
| 2:27 | (nothing) | Sanath hangs up. Terminal A: `call ended: stopping`. | |

If the iPhone call does not reach the Mac within 15 s, use `FALLBACKS.md` step 4 and do not wait longer.

## 5. Privacy proof (2:30–2:48)

**Operator.** Scroll the page to the big **0** (**bytes of caller audio sent off this device**). Bring terminal C onto the projector and press Enter. If Wi-Fi was not switched off in demo 1, switch it off now while Aarav talks.

**AARAV:** "Here's the proof. Bytes of caller audio sent off this laptop: zero. And that isn't just our own counter: the operating system reports zero outbound connections from the engine. The attacker call ran with Wi-Fi off. And Tell never speaks to the caller." (45 words)

If Wi-Fi stayed on during demo 1, say instead of the fourth sentence: "Wi-Fi is off now, and it's still running." If any number in terminal C is not 0, or os_check is not ok: "That number is not zero. We won't talk past it." Point at it and move on.

## 6. How it works (2:48–3:24): each owner says their piece

**SAMARTH (14 s):** "I worked on the model. Pellav2, an open deepfake detector, scores the voice in short windows. Whisper and a small local language model read the words. I built our pipeline to fine-tune Pellav2 on new fakes." (36 words)

**SANATH (15 s):** "I made the voices. I recorded myself reading real call scripts, then cloned my own voice with Qwen3-TTS and Gradium, script for script, so every fake has a real twin. That's our test set, and the attacker you heard." (37 words)

**AARAV (11 s):** "I built the live system: the engine on your own computer, listening on pickup, a verdict every three seconds that can change mid-call, and the apps." (28 words)

## 7. What we measured (3:24–3:42)

**AARAV:** "What we measured, honestly, on small sets: on clean audio the voice check caught 14 of 28 AI clips we made, but only 2 of 10 Qwen clones. That's our weak spot. Twelve real people recorded on phones: none flagged as AI. Tell can be wrong." (46 words)

Source: `pm/AUDITS.md` (fusion re-weight, thresholds 2026-11-07.2; phone-memo humans, 2026-11-07.3). Say counts, never a percentage. If asked, the human set is mostly one speaker plus 12 voice memos (see `QA-PREP.md` Q6).

## 8. Phones-first roadmap (3:42–3:55)

**AARAV:** "Phones first. Android is in early access: the phone is the ears, your own laptop is the brain, connected by a USB cable. Starting automatically on pickup is being built for Android right now. iPhone is coming soon." (38 words; trim "connected" and "right" if behind)

## 9. Close (3:55–4:00)

**AARAV:** "Every voice has a tell. We're Tell. Thank you." (9 words)

**Screen.** The page, with the line **Tell can be wrong.** visible.

## Cut list (in this order if running long)

Check the clock at three points: the end of demo 1 should be about **1:48**, the end of demo 2 about **2:30**, and the end of how it works about **3:24**. If a checkpoint is more than 10 s late, cut from the top of this list until you are back on time.

1. Segment 7: say only "Small test sets. Qwen clones are our weak spot. Tell can be wrong." (saves 10 s)
2. Demo 1: skip the second typed reply (`Fine, thanks.`) and escalate at 1:02 (saves 6 s).
3. Segment 6: Aarav's piece becomes "I built the live system and the apps." (saves 7 s)
4. Segment 8: "Android early access now, iPhone coming soon." (saves 8 s)
5. Segment 2: Sanath says only the first two sentences (saves 8 s).
6. Demo 2: if the call is not on the Mac by 2:05, drop demo 2 entirely, say "The live call didn't connect; here is what a real human looks like," and play the 10 s human replay from `FALLBACKS.md` step 4c, or skip straight to segment 5.
7. Never cut: the TEST ATTACKER label, the privacy numbers, "Tell can be wrong."

## Say this, never this

| Say | Never say |
|---|---|
| "on your own devices", "on this laptop", "the audio goes from the phone only to your own computer, over the cable" | "never leaves the phone", "100% private", "fully on-device" (for a phone) |
| "Android early access", "iPhone coming soon" | "works on every phone", "fully shipped", "Mac today" |
| "two answers: human or AI, scam or not, with the evidence" | "detects every deepfake", "fraud confirmed" |
| "small test sets", exact counts ("2 of 10") | any percentage, "accuracy", "better than Truecaller/Hiya/Google", "only", "first" |
| "possible scam pattern", "Tell can be wrong" | "safe", "legal", "illegal", "verified human" |
| "TEST ATTACKER, fictional, a cloned voice we made with consent" | an unlabelled AI voice, a real brand, a real victim |
| "the fine-tuned model helps on replayed audio in our tests; it is not in today's detector" | "the fine-tune is in the build" |

## Appendix: ownership and evidence

Credit as the git history shows it (`git log origin/main`, PRs on `aaravjain151/doublespeak`). Commit counts on origin/main over the last 3 days: Aarav 222 (166 as "Aarav Jain" plus 56 as "aaravjain151"), Sanath 11, Samarth 7.

| Person | What they present | Evidence |
|---|---|---|
| **Samarth** (`samarth` / `samarthsrinivas`) | The model: the first working detector prototype (Pellav2 on rolling windows, then faster-whisper, then the Ollama scam score, fused; Streamlit UI; encrypted alert store; network monitor). The Pellav2 fine-tuning pipeline (`finetune/`: dataset, features, head training, first Qwen head). The training pipeline (`training/pellav2-finetune`: make fakes, pull real audio, run training; `training/scam-text`: pull text data, mine keywords, train the text model), plus `DATA_SOURCES.md` and the scam scripts. Also the interface mockup and the in-app sample-clip player. | PR #67 `sam_dev1` (merged), commits `3dde4c0` (detector prototype, 23 files, +2362), `4774631` (fine-tune pipeline + fake-voice fix, 14 files, +814), `881e12a` (training/ voice + scam-text, 15 files, +1292), `8a3d16f` (runtime fixes, sample-clip player), `3239127` (`design/interface.html`), `85007f0` (merge), `3118a20` (README sample clips). Follow-up hardening by Aarav: #68 (`torch.load weights_only`). Note: the larger 80-speaker head study (`docs/HEAD-FINETUNE.md`, #76, #83) came after his run and was done on Aarav's branches. It extends his pipeline and is credited to the team. It is not in today's detector. |
| **Sanath** (`sanathNU`) | The voices and data: his own consented recordings (20 clean scripts under `human/sanath`), paired Qwen3-TTS clones, and Gradium clones regenerated with his v4 voice at 48 kHz. These are the clips behind every audit row and the attacker voice. Also the T-012 human recorder and speaker-to-mic replay tool, CI and dev ergonomics (`make setup/lock/models/demo`, CODEOWNERS, PR template, pinned lockfiles, fresh-clone fixes, torch floor for CVE-2025-32434), and the Pellav2 MPS-default and load-time PR. | Data branch `data/sanath-voice-clips`: `7ab59fe` (human clips + qwen3tts and gradium clones), `f33fdcb` (gradium regenerated with Sanath v4 voice), `4ecb91b` (+7 recordings and paired clones), `789d14c` (+3 more). PR #2 (merged; `2768cef` human recorder + replay, `bdda80f` brand rename). PR #50 for issue #37 (merged; `4ff6dca`, `87523f2`, `2e3b494`, `3d93276`, `3eca7bf`, `2590092`, `6cc1bf2`). **PR #49** (closes #25) is **open, not merged**: MPS by default and load-time logging. The Pellav2 voter itself landed in #48 (Aarav), so do not say "Sanath landed Pellav2"; say "Sanath's PR makes it use the Mac's GPU by default". |
| **Aarav** (`Aarav Jain` / `aaravjain151`) | Product, architecture, the engine (`services/api/tell`: signals, scorer, privacy meter and OS outbound check, Pellav2/HF/Whisper/Ollama voters, stabiliser, live stream), the live listener and audio tap, the apps (web page and site, Mac menu bar, Android, iPhone, block list), the evaluations (fusion re-weight, shadow layers, Qwen cue study, head fine-tune studies), integration and this demo. He also owns the voice-talk attacker app (separate repo, all 14 commits). | PRs #1, #3–#21, #44–#48, #51, #54–#66, #68–#86 (author `aaravjain151`), e.g. #48 Pellav2 voter, #60 streaming backend, #65 live detection, #59 macOS tap, #69 Android, #73 iPhone, #79 menu bar, #72/#75/#76/#83 evaluations, #84 rename to Tell. voice-talk `attacker-demo` branch (`3954af3`, `04059c5`, `907d80b`, `58c78ca`). Much of this was built with AI coding agents under his direction; say "we built" for the system and "I" only for the parts above. |

The earlier draft line "in a small informal test of about 10 clips the team judged 9 correct" (RUN-OF-SHOW, PRESENTATION-OUTLINE) has no source in the repo, so this script does not use it. Segment 7 uses the audited counts instead.
