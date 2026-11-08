# Demo script: 4 minutes, Sunday 11:00

**This file is the one plan.** The deck (claude.ai Slides artifact "Tell: pitch deck") carries exactly the slides this script uses, in this order, and its speaker notes repeat these lines word for word. If the deck and this file ever disagree, this file wins. Preflight: `PREFLIGHT.md`. If a step fails: `FALLBACKS.md`. Judge questions: `QA-PREP.md`. Practice: `REHEARSAL.md`. `RUN-OF-SHOW.md` and `PRESENTATION-OUTLINE.md` are older drafts kept for detail; do not present from them.

## Tracks we are entering, and how the pitch answers the judging

- **Privacy-First (primary target).** Judged on "what leaves the device, who can read it, can you prove it, then would anyone use it." Our answers, in order: caller audio is blocked from leaving by code — zero by design (segment 5, `tests/test_privacy.py`); who can read it — the engine binds to loopback only, so no other machine reaches it, and a per-install token on every data route (401 without it) adds same-machine isolation (PR #90, open — see Q5); can you prove it — the OS's own count of the engine's outbound connections since start reads zero, and a judge can block Tell's outbound (Little Snitch / `lsof`) and the verdict still comes; would anyone use it — the live demo plus the who-pays answer (segment 4, Q19).
- **Most Startup-able (secondary target).** Judged on "how fundable, who is it for, would they pay, why this team." First customer: adult children buying a family plan for a parent (60+). Price hypothesis: ~US$5/month ([N of M said yes tonight]). Why this team: we already shipped the live system, the model pipeline and the voices/data (segment 7, Q19–Q21, team slide).
- **Best Use of Gradium (side prize, stacks with Privacy-First).** We cloned our own teammates' voices in Gradium to manufacture the red-team attacker calls that attack our own detector, and Gradium speaks Tell's verdict — only our own script text is ever sent to Gradium, never a caller (segment 7, Q18). The privacy-correctness of that use is itself the story.

## Who is where

| Person | Role on stage | Says |
|---|---|---|
| **Aarav** (AARAV) | Presenter, front centre, holds the clicker. His iPhone is on the table, signed in to the same Apple Account as the Mac. | Hook, both demo narrations, privacy proof, what we measured, team, roadmap, close |
| **Samarth** (SAMARTH) | Operator at the Mac, which drives the projector. | How it works |
| **Sanath** (SANATH) | Stands at the side with his own phone. He is the voice the attacker cloned and the real caller in demo 2. | The attacker, the demo 2 call and its tag line, Gradium |

Projector layout (set in preflight): the deck full screen until the LIVE slide. Then Chrome at `http://127.0.0.1:5173` on the right two-thirds, dark theme, zoomed so the headline is readable from the back. On the left third, the voice-talk tab at `http://127.0.0.1:8765`, which shows its red **TEST ATTACKER - fictional scenario** bar. Terminals sit on the laptop screen but off the projector, except terminal C, which is shown during the privacy proof. After the privacy proof the operator cuts back to the deck on the **Privacy you can check** slide.

Terminals (all from the repo root, prepared in preflight):

- **A**: `.venv/bin/python tools/macos/listen.py --watch --i-understand`. It runs the whole time. It arms by itself when a call app plays audio and ignores the browser, so it stays idle during demo 1.
- **B**: `.venv/bin/python tools/macos/listen.py --now --i-understand`, typed in but **not started** (Samarth presses Enter on cue).
- **C**: the health one-liner, typed in but not started:
  `curl -s http://127.0.0.1:8000/health | python3 -c "import json,sys; h=json.load(sys.stdin); e=h['egress']; n=h['os_network']; print('caller audio bytes sent:', e['caller_audio_bytes_sent'], '| external bytes:', e['bytes_sent_external'], '| OS outbound connections:', n['os_outbound_count'], '| os_check:', n['os_check'])"`

voice-talk setup (in preflight): voice **sanath** (if Sanath confirms on the day that he still agrees; otherwise **demo-say** and use the lines marked ALT). **Demo mode** on, set **Escalating scam test**. Untick **Advance the stage by turn count**, so the operator drives each stage with **Escalate**. Input set to **typing**, with the mic off (room echo can cut the bot off, see `REHEARSAL.md`). Leave the spoken disclosure on unless the round 1 rehearsal decided otherwise; if it is off, the acknowledgement tick must be set. **Pre-record the next line** on.

**Wi-Fi stays ON for both demos.** It goes off only in the privacy proof (segment 5), after the iPhone call is over.

Pace: about 150 words per minute. Word counts are shown so each segment can be checked against the clock.

## Slides used (deck order)

| # | Slide | Shown during |
|---|---|---|
| 1 | Cover: **Tell.** | Walk-on; Aarav clicks on his opening word |
| 2 | Problem: **The scam call doesn't sound like a scam.** | Hook |
| 3 | **LIVE** cue | The attacker; operator cuts to Chrome during it |
| 4 | **Privacy you can check** | End of the privacy proof (operator cuts back to the deck) |
| 5 | **How it works** (one diagram) | How it works |
| 6 | **What we measured** | Gradium, then what we measured |
| 7 | **Team** | Team |
| 8 | **Roadmap** | Roadmap |
| 9 | **Close** | Close, then Q&A |
| hidden | BACKUP: Why us · Who pays · Threat model · Later: deepfake calls at work · Illustration of the live card | Q&A only (jump to them from the slide grid) |

## Timing table

| # | Clock | Length | Segment | Speaker(s) | Words spoken |
|---|---|---|---|---|---|
| 1 | 0:00–0:20 | 20 s | Hook | Aarav | 46 |
| 2 | 0:20–0:32 | 12 s | The attacker | Sanath | 28 |
| 3 | 0:32–1:34 | 62 s | Live demo 1: TEST ATTACKER | Aarav (bot talks most of it) | about 60 + one branch line |
| 4 | 1:34–2:12 | 38 s | Live demo 2: real human call | Aarav, Sanath | about 75 |
| 5 | 2:12–2:30 | 18 s | Privacy proof | Aarav | 45 |
| 6 | 2:30–2:46 | 16 s | How it works | Samarth | 41 |
| 7 | 2:46–3:06 | 20 s | Gradium | Sanath | 56 |
| 8 | 3:06–3:40 | 34 s | What we measured | Aarav | 83 |
| 9 | 3:40–3:45 | 5 s | Team | Aarav | 16 |
| 10 | 3:45–3:59 | 14 s | Roadmap | Aarav | 35 |
| 11 | 3:59–4:06 | 7 s | Close | Aarav | 17 |
| | | **246 s** | | | |

Planned length is 4:06. Cut 1 on the cut list brings it to 3:52; use it if the rehearsal clock lands over 4:00.

**Checkpoints:** end of demo 1 at **1:34**, end of demo 2 at **2:12**, end of how it works at **2:46**. More than 10 s late at a checkpoint: cut from the top of the cut list.

## 1. Hook (0:00–0:20)

**Screen.** Cover, then Aarav clicks to the Problem slide on his opening word.

**AARAV:** "Last year Americans reported losing three and a half billion dollars to people pretending to be someone they trust. The call sounds like your bank. Sometimes it sounds like your son. Caller ID checks the number. Tell checks the conversation, live, on your own devices. Watch." (46 words)

On "Watch." click to the LIVE slide.

Source (on the slide footer): US Federal Trade Commission, Consumer Sentinel data, press release of 15 June 2026: US$3.5 billion reported lost to impostor scams in 2025. Phone is one contact method among several; never say all of it was phone calls.

## 2. The attacker (0:20–0:32)

**Screen.** LIVE slide. Samarth cuts the projector to Chrome while Sanath talks.

**SANATH:** "The attacker you're about to hear is a copy of my voice, made by an open-source model on this laptop. I agreed to it. A scammer won't ask." (28 words)

ALT (demo-say voice): "The attacker you're about to hear is a cloned voice, made by an open-source model on this laptop. Ours is labelled and fictional. A real scammer's isn't." (27 words)

## 3. Live demo 1: the TEST ATTACKER (0:32–1:34)

Wi-Fi stays on.

| Clock | Operator (Samarth) does | Room sees or hears | Aarav says |
|---|---|---|---|
| 0:32 | Terminal B: Enter. Wait for `=== LISTENING`. | The page shows the listening bar and timer. | "On the left, a test bot we built, labelled TEST ATTACKER. It's fictional. On the right, Tell." (17 words) |
| 0:38 | Click **Start session** in voice-talk. | The bot opens: "Hi, good morning! This is Alex from Example Services..." | (silent) |
| 0:44 | Type `Yes, go ahead.` and press Enter. After the next reply, type `Fine, thanks.` and press Enter. | Friendly small talk, about 15 s of bot speech. The card leaves warming up. | In a gap: "Small talk. Tell is calm: no scam pattern." (8 words) |
| 0:58 | Click **Escalate** (stage 2). | "...I'm actually with the Example Bank Fraud Desk... case number 000-TEST." Amber can appear here. | In a gap: "Now it claims to be the bank." (7 words; add "Amber." if amber shows) |
| 1:10 | Click **Escalate** (stage 3). | "...please read me the six digit code we just texted to you." | (silent; let the room hear the ask) |
| 1:18 | If red has not shown by 1:24, click **Escalate** (stage 4, secrecy). | The red banner, and the 2×2 moves to the Scam column. A line under **Why we think so** names the code request. | **Two seconds of silence on red.** Then: "The words gave it away: it asked for a code." (10 words) Then the ONE voice-row line that matches the screen, below. |
| 1:30 | Click **Stop** in voice-talk. Ctrl-C terminal B. Click **Dismiss** on the red banner. | The page returns to waiting. | (bridge) "Now a real person." (4 words) |

**Voice-row lines (these are the main lines; rehearse all four, read only the one on screen).** Before choosing, look at the reason under the voice row: if it says the caller said it was automated, the AI answer comes from the disclosure, not from the voice check.

- Voice row shows **AI voice**, and the reason is the voice check: "And the voice check says AI too." (7 words)
- Voice row shows **AI voice** only because the bot said it was automated: "The voice says AI here because the bot told us it's automated. That's the disclosure, not the voice check." (19 words)
- Voice row shows **not sure**: "The voice check isn't sure about this clone, and it says so. The words caught it. That's why there are two answers." (22 words)
- Voice row shows **human**: "The voice check heard this clone as human. That's our blind spot, and why the words are checked separately." (19 words)
- No red by 1:30: "It hasn't gone red. It needs two scam signs that agree before it alerts. We don't override it." (18 words) Then go on.

## 4. Live demo 2: a real human (1:34–2:12)

| Clock | Operator does | Room sees or hears | Spoken |
|---|---|---|---|
| 1:34 | (nothing) | Sanath raises his phone and dials Aarav's iPhone. | **AARAV:** "Sanath, call me." (3 words) |
| 1:38 | When the Mac banner appears, click **Answer**. | Terminal A: `call detected`, `=== LISTENING`. The page shows the listening bar. Sanath's voice comes out of the Mac speakers. | **AARAV:** "I didn't press anything in Tell. It started listening when I picked up." (13 words) |
| 1:42 | (nothing) | Sanath talks for about 20 s, steadily, with no pauses. | **SANATH** (into his phone): "Hey, it's Sanath. I'm standing right over there. Just calling to say the demo's going okay so far. Are we still getting food after this? I was thinking the noodle place on the corner. Okay, I'll stop talking now." (39 words) |
| 2:02 | Point the cursor at the filled cell. | 2×2 cell and its sentence. | **AARAV** (read the screen): "Sounds human. No scam pattern." (5 words) If it shows **not sure**: "On a phone line the voice check is less sure, and it says so instead of guessing." (17 words) |
| 2:06 | (nothing) | Sanath hangs up. Terminal A: `call ended: stopping`. | **SANATH:** "Same voice. One was me. One was a copy asking for your code." (13 words) |

If the iPhone call does not reach the Mac within 15 s, use `FALLBACKS.md` step 4 and do not wait longer.

## 5. Privacy proof (2:12–2:30)

**Operator.** Menu bar > Wi-Fi > **off**. Scroll the page to the big **0** (**bytes of caller audio sent off this device**). Bring terminal C onto the projector and press Enter. When Aarav says "never speaks to the caller", cut back to the deck on the **Privacy you can check** slide.

**AARAV:** "Wi-Fi is off now, and Tell is still running. Caller audio is blocked from leaving by code: zero by design. The independent check is the operating system's own count of the engine's network connections during the call: zero. And Tell never speaks to the caller." (45 words)

Never present the 0 as a measurement of audio: the audio 0 is a design invariant (the code refuses to send it), the OS count is the measured check. If any number in terminal C is not 0, or os_check is not ok: "That number is not zero. We won't talk past it." Point at it and move on.

**Invite the judge to verify it themselves (say this, and mean it).** "Don't take our word for it. During a call, block every outbound connection for Tell in Little Snitch, or run `lsof -i` against the engine process — the verdict keeps coming, because caller analysis needs nothing to leave this device. Come try it at our table." This is provable today on the demo build. The matching claim for the live feed — `curl` it without the per-install token and you get 401 — depends on PR #90, which is open and not merged as of this writing; only add "and curl the live feed without the token, you get 401" if #90 is on the demo build by 11:00 (see Q5). Do not invite a check that would fail.

Scope, for Q&A: the page's OS count is polled every 50 ms during each analysis for the engine process and its children; terminal C's `/health` figure is a snapshot taken at that moment. Neither covers Ollama, which is a separate local process (`QA-PREP.md` Q2).

## 6. How it works (2:30–2:46): one diagram, one speaker

**Screen.** How it works slide.

**SAMARTH:** "The phone or the Mac hears the call; your own computer is the brain. Whisper writes down the words, a small local language model checks them for scam patterns, and Pellav2, an open deepfake detector, scores the voice. Two separate answers." (41 words)

## 7. Gradium (2:46–3:06)

**Screen.** What we measured slide (Gradium row on top).

**SANATH:** "Gradium was our sparring partner. I cloned my voice in it for our test scripts, so each fake has a real twin. Replayed through a simulated room, Gradium audio scored below a coin flip on the open detector: AUC 0.42. Our held-out head, not shipped yet, reached 0.82. Gradium got our script text, never a caller." (56 words)

Source: `docs/HEAD-FINETUNE.md` (hold out Gradium, `chain_replay_call` = simulated speaker re-record then Opus 8 kHz, AUC Pellav2 0.42 vs head 0.82, 440 real / 72 fake windows; a second fold seed gave 0.72 vs 0.42). The head is not wired into the detector (`pm/AUDITS.md`).

## 8. What we measured (3:06–3:40)

**AARAV:** "With weights we tuned on these same clips, 13 of our 28 AI clips crossed the line on clean audio. Holding the Qwen engine out of tuning, the voice check caught 1 of 10 Qwen clones. That's our blind spot, and why the words are checked separately. Twelve voice memos from about four friends, not phone calls: none crossed the AI line, but on a very lossy simulated channel one voice model misfired on 7 of them. Small sets. Tell can be wrong." (83 words)

Sources, all in `pm/AUDITS.md` on origin/main: 13/28 = the raw voice formula after the fusion re-weight, without the disclosure floor (the shipping pipeline reports 14/28 because one more clip reads an "I'm an AI" script); 1/10 = leave-one-engine-out with Qwen3-TTS held out (in-sample it is 2/10); 0/12 and 7/12 = phone-memo humans, thresholds 2026-11-07.3, Pellav2 at `opus_lowbitrate_with_loss`. Say counts, never a percentage.

## 9. Team (3:40–3:45)

**AARAV:** "Samarth built the model pipeline, Sanath the voices and data, and I built the live system." (16 words)

## 10. Roadmap (3:45–3:59)

**AARAV:** "Android: a working prototype in speaker mode; a real call isn't verified yet. iOS gives apps no call audio, so iPhone calls work today through your own Mac, and the iPhone app is in progress." (35 words)

## 11. Close (3:59–4:06)

**AARAV:** "Caller ID tells you who's calling. Tell tells you what they want. Every voice has a tell." (17 words)

**Screen.** Close slide, with the small line: "Tell can be wrong. If a call asks for money or a code, hang up and call back on a number you already have." Leave it up for Q&A.

## Cut list (in this order if running long)

1. Segment 8 becomes: "With weights tuned on these clips, 13 of 28 AI clips crossed the line. With Qwen held out, 1 of 10: our blind spot. Twelve voice memos, none flagged. Small sets. Tell can be wrong." (saves 14 s)
2. Demo 1: skip the second typed reply (`Fine, thanks.`) and escalate at 0:52 (saves 6 s).
3. Segment 7 becomes: "Gradium was our sparring partner: I cloned my voice in it for our test scripts. Replayed through a simulated room, it beat the open detector; our held-out head, not shipped yet, did much better. Gradium only got our script text." (saves 6 s)
4. Segment 9: drop it; the Team slide shows for two seconds while Aarav clicks through (saves 5 s).
5. Segment 2: Sanath says the opening sentence and stops (saves 5 s).
6. Demo 2: if the call is not on the Mac by 1:50, drop demo 2, say "The live call didn't connect; here is a real human, recorded," and play the human replay from `FALLBACKS.md` step 4c, or skip straight to segment 5.
7. Never cut: the TEST ATTACKER label, the two seconds on red, the privacy numbers, Sanath's "Same voice" line, "Tell can be wrong."

## Say this, never this

| Say | Never say |
|---|---|
| "on your own devices", "on this laptop", "the audio goes from the phone to your own computer, over the cable" | "never leaves the phone", "100% private", "fully on-device" (for a phone) |
| "Android: working prototype, speaker mode, real call not verified yet"; "iPhone calls work today through your own Mac; the iPhone app is in progress" | "early access", "coming soon", "works on every phone", "fully shipped", "Mac today" |
| "two answers: human or AI, scam or not, with the evidence" | "detects all deepfakes", "fraud confirmed" |
| "small test sets", exact counts ("1 of 10"), "in-sample" before an in-sample count | any percentage, "accuracy", "better than Truecaller/Hiya/Google", "only", "first", an informal clip count |
| "caller audio is blocked from leaving by code"; "the OS counted zero connections" | "we measured zero bytes of audio" |
| "possible scam pattern", "Tell can be wrong" | "safe", "legal", "illegal", "verified human" |
| "TEST ATTACKER, fictional, a cloned voice we made with consent" | an unlabelled AI voice, a real brand, a real victim |
| "the trained head helps on replayed audio in our tests; it is not in today's detector" | "the fine-tune is in the build" |

## Appendix: ownership and evidence

Credit as the git history shows it (`git log origin/main`, PRs on `aaravjain151/doublespeak`). Commit counts on origin/main over the last 3 days: Aarav 222 (166 as "Aarav Jain" plus 56 as "aaravjain151"), Sanath 11, Samarth 7.

| Person | What they present | Evidence |
|---|---|---|
| **Samarth** (`samarth` / `samarthsrinivas`) | The model: the original working detector prototype (Pellav2 on rolling windows, then faster-whisper, then the Ollama scam score, fused; Streamlit UI; encrypted alert store; network monitor). The Pellav2 fine-tuning pipeline (`finetune/`: dataset, features, head training, an early Qwen head). The training pipeline (`training/pellav2-finetune`: make fakes, pull real audio, run training; `training/scam-text`: pull text data, mine keywords, train the text model), plus `DATA_SOURCES.md` and the scam scripts. Also the interface mockup and the in-app sample-clip player. | PR #67 `sam_dev1` (merged), commits `3dde4c0` (detector prototype, 23 files, +2362), `4774631` (fine-tune pipeline + fake-voice fix, 14 files, +814), `881e12a` (training/ voice + scam-text, 15 files, +1292), `8a3d16f` (runtime fixes, sample-clip player), `3239127` (`design/interface.html`), `85007f0` (merge), `3118a20` (README sample clips). Follow-up hardening by Aarav: #68 (`torch.load weights_only`). Note: the larger 80-speaker head study (`docs/HEAD-FINETUNE.md`, #76, #83) came after his run and was done on Aarav's branches. It extends his pipeline and is credited to the team. It is not in today's detector. |
| **Sanath** (`sanathNU`) | The voices and data: his own consented recordings (20 clean scripts under `human/sanath`), paired Qwen3-TTS clones, and Gradium clones regenerated with his v4 voice at 48 kHz. These are the clips behind every audit row and the attacker voice. Also the T-012 human recorder and speaker-to-mic replay tool, CI and dev ergonomics (`make setup/lock/models/demo`, CODEOWNERS, PR template, pinned lockfiles, fresh-clone fixes, torch floor for CVE-2025-32434), and the Pellav2 MPS-default and load-time PR. | Data branch `data/sanath-voice-clips`: `7ab59fe` (human clips + qwen3tts and gradium clones), `f33fdcb` (gradium regenerated with Sanath v4 voice), `4ecb91b` (+7 recordings and paired clones), `789d14c` (+3 more). PR #2 (merged; `2768cef` human recorder + replay, `bdda80f` brand rename). PR #50 for issue #37 (merged; `4ff6dca`, `87523f2`, `2e3b494`, `3d93276`, `3eca7bf`, `2590092`, `6cc1bf2`). **PR #49** (closes #25) is **open, not merged**: MPS by default and load-time logging. The Pellav2 voter itself landed in #48 (Aarav), so do not say "Sanath landed Pellav2"; say "Sanath's PR makes it use the Mac's GPU by default". |
| **Aarav** (`Aarav Jain` / `aaravjain151`) | Product, architecture, the engine (`services/api/tell`: signals, scorer, privacy meter and OS outbound check, Pellav2/HF/Whisper/Ollama voters, stabiliser, live stream), the live listener and audio tap, the apps (web page and site, Mac menu bar, Android, iPhone, block list), the evaluations (fusion re-weight, shadow layers, Qwen cue study, head fine-tune studies), integration and this demo. He also owns the voice-talk attacker app (separate repo, all 14 commits). | PRs #1, #3–#21, #44–#48, #51, #54–#66, #68–#86 (author `aaravjain151`), e.g. #48 Pellav2 voter, #60 streaming backend, #65 live detection, #59 macOS tap, #69 Android, #73 iPhone, #79 menu bar, #72/#75/#76/#83 evaluations, #84 rename to Tell. voice-talk `attacker-demo` branch (`3954af3`, `04059c5`, `907d80b`, `58c78ca`). Much of this was built with AI coding agents under his direction; say "we built" for the system and "I" only for the parts above. |

An earlier draft quoted an informal clip count that has no source in the repo. It is retired everywhere; segment 8 uses the audited counts in `pm/AUDITS.md` instead.
