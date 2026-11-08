# Finalist pitch: 3 minutes, Sunday 1:50–2:20 PM

**This is the finals cut** (top 6, 3 min + 2 min Q&A). The full expo/table version is `DEMO-SCRIPT.md`; it wins on any disagreement about wording and honest-claims rules. This cut keeps **one** live demo beat — the scam call flips red mid-call — then the privacy proof, then who-pays, then the tagline. Everything else (how-it-works detail, what-we-measured, roadmap, team roll call) moves to Q&A. Judge questions: `QA-PREP.md`. If the demo fails: the 30-second fallback at the bottom.

Pace ~150 words per minute. Planned length **2:45**, hard cap **3:00** — the 15 s buffer absorbs a slow escalation.

## What it has to land (both judging lines, fast)

- **Privacy-First (primary).** What leaves the device: no caller audio, blocked by code. Who can read it: loopback-only, per-install token on every route (PR #90). Can you prove it: OS outbound count is zero and a judge can block all outbound / `lsof` and the verdict still comes. Would anyone use it: the live flip-to-red plus who-pays.
- **Most Startup-able (nod).** Who'd pay: adult children, family plan, ~US$5/month.
- **Best Use of Gradium (side prize, stacks):** one honest line — the attacker voice is a teammate's own voice, cloned in Gradium with consent, attacking our own detector; only our script text is sent, never a caller.

## Slides for the finals cut (see deck "Slide order" note)

Cover → Problem → LIVE → Privacy you can check → Who pays (normally a backup slide, promoted into this cut) → Close. Skip How it works, What we measured, Team, Roadmap as full slides; they stay as backups for Q&A.

## Timing table

| # | Clock | Length | Segment | Speaker(s) | Words |
|---|---|---|---|---|---|
| 1 | 0:00–0:18 | 18 s | Hook | Aarav | 44 |
| 2 | 0:18–0:30 | 12 s | The attacker (cloned voice) | Sanath | 28 |
| 3 | 0:30–1:30 | 60 s | Live beat: scam call flips red | Aarav (bot talks most) | ~45 + one voice-row line |
| 4 | 1:30–2:00 | 30 s | Privacy proof + invite the judge | Aarav | 58 |
| 5 | 2:00–2:14 | 14 s | How it works (one line) | Samarth | 34 |
| 6 | 2:14–2:34 | 20 s | Who pays | Aarav | 48 |
| 7 | 2:34–2:45 | 11 s | Close + tagline | Aarav | 27 |
| | | **2:45** | | | |

**Checkpoint:** be on the privacy proof by **1:30**. If the red flip has not happened by 1:24, click Escalate to the secrecy stage and let it fire; do not wait past 1:30.

## 1. Hook (0:00–0:18)

**Screen.** Cover, then Problem slide on the opening word.

**AARAV:** "Last year Americans reported losing three and a half billion dollars to people pretending to be someone they trust. The call sounds like your bank. Sometimes it sounds like your son. Caller ID checks the number. Tell checks the conversation, live, on your own devices. Watch." (44 words)

On "Watch." click to the LIVE slide; operator cuts the projector to Chrome.

Source (slide footer): US FTC, Consumer Sentinel, press release 15 June 2026: US$3.5 billion reported lost to impostor scams in 2025. Phone is one contact method among several; never say all of it was phone.

## 2. The attacker (0:18–0:30)

**SANATH:** "The attacker you're about to hear is a copy of my voice, made by an open-source model on this laptop. I agreed to it. A scammer won't ask." (28 words)

ALT (demo-say voice): "The attacker you're about to hear is a cloned voice, made by an open-source model on this laptop. Ours is labelled and fictional. A real scammer's isn't." (27 words)

## 3. Live beat: the scam call flips red (0:30–1:30)

Wi-Fi stays on. One escalation path only — small talk, then straight to the code ask.

| Clock | Operator (Samarth) does | Room sees or hears | Aarav says |
|---|---|---|---|
| 0:30 | Terminal B: Enter. Wait for `=== LISTENING`. Then click **Start session**. | Listening bar; the bot opens: "Hi, good morning! This is Alex from Example Services..." | "On the left, a test bot we built, labelled TEST ATTACKER. It's fictional. On the right, Tell, listening." (18 words) |
| 0:42 | Type `Yes, go ahead.` Enter. | ~10 s of friendly small talk. | In a gap: "Small talk. Tell is calm: no scam pattern." (8 words) |
| 0:56 | Click **Escalate** (bank), then at 1:08 **Escalate** (code ask). | "...I'm with the Example Bank Fraud Desk... please read me the six digit code we just texted you." | (silent; let the room hear the ask) |
| 1:16 | If red has not shown by 1:22, click **Escalate** (secrecy). | Red banner; the 2×2 moves to the Scam column; under **Why we think so** the code request is named. | **Two seconds of silence on red.** Then: "The words gave it away: it asked for a code." (10 words) Then the ONE voice-row line below. |
| 1:28 | Click **Stop**; **Dismiss** the banner. | Page returns to waiting. | (bridge) "That flipped live, mid-call." (4 words) |

**Voice-row line (read only the one on screen; full set in `DEMO-SCRIPT.md` §3).**

- Voice row **AI voice**, reason is the voice check: "And the voice check says AI too." (7 words)
- Voice row **AI voice** only because the bot disclosed: "The voice says AI because the bot told us it's automated — the disclosure, not the voice check." (17 words)
- Voice row **not sure**: "The voice check isn't sure about this clone, and it says so. The words caught it." (16 words)
- No red by 1:28: "It needs two scam signs that agree before it alerts. We don't override it." (14 words) Then go on.

## 4. Privacy proof (1:30–2:00)

**Operator.** Menu bar > Wi-Fi > **off**. Scroll to the big **0** (**bytes of caller audio sent off this device**). Bring terminal C onto the projector and press Enter. On "come check it yourself", cut back to the **Privacy you can check** slide.

**AARAV:** "Wi-Fi is off, and Tell is still running. Caller audio is blocked from leaving by code: zero by design. The independent check is the operating system's own count of the engine's network connections during the call: zero. Don't take our word for it — block all outbound for Tell, or run `lsof`, and the verdict still comes. Come check it yourself." (58 words)

Never present the 0 as a measurement of audio: the audio 0 is a design invariant, the OS count is the measured check. If any terminal-C number is not 0, or os_check is not ok: "That number is not zero. We won't talk past it." Point and move on.

**Token / 401 line — conditional.** Add "and curl the live feed without the per-install token, you get 401" ONLY if PR #90 is on the demo build by showtime; it is open and not merged as of this writing (`QA-PREP.md` Q5). Do not invite a check that would fail.

## 5. How it works (2:00–2:14): one line

**SAMARTH:** "Your own computer is the brain: Whisper writes down the words, a small local language model checks them for scam patterns, and an open deepfake detector scores the voice. Two separate answers, every answer lists its reasons." (34 words)

## 6. Who pays (2:14–2:34)

**Screen.** Who pays slide.

**AARAV:** "Who pays? The adult child who worries about a parent getting the family-emergency call. The child buys, the parent benefits, so we sell a family plan, around five dollars a month. It's a hypothesis, not validated: tonight we asked and [N of M said yes]. Next is pricing interviews with families." (48 words; keep the [N of M] honest — say the real number or cut the sentence.)

## 7. Close (2:34–2:45)

**AARAV:** "Caller ID tells you who's calling. Tell tells you what they want. And you can check every word of it. Every voice has a tell." (27 words)

**Screen.** Close slide with the small line: "Tell can be wrong. If a call asks for money or a code, hang up and call back on a number you already have." Leave it up for Q&A.

## 30-second ultra-fallback (demo failed)

Use if the bot, the page or the call does not come up by the 0:42 cue. Switch the projector to the **Illustration of the live card** backup slide and play the pre-recorded clip (`FALLBACKS.md` step 4c).

**AARAV:** "Our live bot isn't cooperating, so here's a recording of the same thing. A cloned voice — a teammate's, with consent — works up to asking for a six-digit code, and Tell flips to a scam pattern on the words, live, with the reason shown. The important part you can still check right now: Wi-Fi is off, caller audio is blocked from leaving by code, and the operating system counts zero outbound connections. Block all outbound yourself and the verdict still comes. Caller ID checks the number; Tell checks the conversation. Every voice has a tell." (~95 words, ~38 s — if over, drop the two sentences after "reason shown".)

Honest-claims rules apply to the fallback too: "possible scam pattern" / "Tell can be wrong", no percentages, no "safe"/"legal"/"only"(as a superiority claim)/"first", the TEST ATTACKER voice is labelled and consented.
