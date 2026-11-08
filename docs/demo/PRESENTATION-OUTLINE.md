# Presentation outline — Sunday 11:00

> **Superseded for Sunday by `DEMO-SCRIPT.md`** (4 minutes, phones-first positioning, the voice-talk TEST ATTACKER, owner-by-owner how-it-works). This Mac-first deck draft stays for detail. Do not use its "Mac: live" / "Mac today" framing or the "9 of about 10 clips" line (no source in the repo); `DEMO-SCRIPT.md` segment 7 uses the audited counts.

Twelve slides. One line on the slide. The speaker notes are the words. Dark theme. The live demo slide is a cut to the Mac, run from `docs/demo/RUN-OF-SHOW.md`.

## Slide 1 — Tell

**Message:** A caller ID that listens to the call, on your own device.

**Visual:** Wordmark on the dark page, the real browser at `http://127.0.0.1:5173` showing **Waiting for a call**. No mock UI.

**Say:** "Tell listens while the call is happening and answers on this machine. It does not speak to the caller."

## Slide 2 — You cannot tell by ear

**Message:** A voice can be a person or an AI, and the call can be a scam or not. Those are different questions.

**Visual:** Two blank questions on screen: "Person or AI?" and "Scam or not?" Nothing ticked.

**Say:** "When you pick up, you do not get either answer. A cloned voice can sound like someone you know. A human can read a scam script. Hearing the call is not the same as knowing which is which."

## Slide 3 — Listen live, on the device you already have

**Message:** A smarter caller ID: it hears the live call and judges it on your own device.

**Visual:** Photo of the Mac with the real page beside an iPhone. Arrow from the iPhone call banner to the Mac, labelled "Calls on Other Devices".

**Say:** "You answer the iPhone call on the Mac. Tell hears that audio here. The models run on this laptop. Google Scam Detection on-device, Hiya AI Phone, and Truecaller also do real-time or on-device scam detection. What we show is this card: two answers, the evidence, and a counter you can read."

## Slide 4 — What happens on a call

**Message:** The listener starts by itself, then the verdict updates about every 3 seconds and can change mid-call.

**Visual:** Three stills from a real screen recording, each marked `recorded demo`: **Waiting for a call**, the listening bar, a verdict card. Terminal crop that shows `=== LISTENING`, not a drawing of one.

**Say:** "A listener on the Mac watches for a call app. When the call plays, it starts by itself. About every 3 seconds the card updates. If the call turns from ordinary talk into a request for a code, the card is allowed to change before you hang up. Plain evidence sits under the answer. Tell never speaks to the caller."

## Slide 5 — Human or AI, and scam or not

**Message:** The 2×2 is two answers, not one blended score.

**Visual:** The real grid from the page. Rows: **Human voice**, **AI voice**. Columns: **Not scam**, **Scam**. One cell filled. The sentence under the grid is readable. Corner label `recorded demo` if the still is from a staged clip.

**Say:** "Human voice with no scam pattern. Human voice with a scam pattern. AI voice with no scam pattern. AI voice with a scam pattern. A disclosed AI caller and a scam script are not the same cell. We read the sentence under the grid, and one line from **Why we think so**."

## Slide 6 — The counter you can look at

**Message:** Caller audio is analysed on this machine, and the counters we show read 0.

**Visual:** The real proof block: the big **0** and the caption **bytes of caller audio sent off this device**. Beside it, a terminal crop of the health check: `caller_audio_bytes_sent 0`, `bytes_sent_external 0`, `os_check ok`, `os_outbound_count 0`.

**Say:** "The page counts caller-audio bytes sent off this device. The health check adds external bytes sent, and an operating-system check of outbound connections from the engine. On this demo those read 0, 0, and 0. If a counter shows something else, read the number on screen and move on."

## Slide 7 — Live, on this Mac

**Message:** The next three minutes are the live product, not a slide.

**Visual:** Cut to the projector on Chrome. No slide content except a held title if the cut is late: "Live on this Mac."

**Say:** Hand to the operator and follow `docs/demo/RUN-OF-SHOW.md` from the open through the counter. Name the staged clip out loud as TEST ATTACKER, fictional scenario, disclosed Qwen voice, recorded demo.

## Slide 8 — What we measured

**Message:** In a small informal test, the team judged 9 of about 10 clips correct. That is not a rate.

**Visual:** One line of type: "In a small informal test of about 10 audio clips, the team judged 9 correct." No percent sign. No chart that implies a benchmark.

**Say:** "In a small informal test of about 10 audio clips, 9 were judged correct by the team. Do not turn that into a percentage. We also evaluated and fine-tuned an open-source detector head on many speakers. It helps on speaker-replay audio. It is not in the shipped detector yet. The card you just saw is the detector we are running today."

## Slide 9 — Where it runs

**Message:** Mac is the live path. Android is early access. The iPhone is covered through the Mac.

**Visual:** Three rows, short labels, no store badges.

- Mac: live. iPhone calls answered on the Mac through Calls on Other Devices are heard here.
- Android early access (speaker mode). Real-call behaviour is not verified yet.
- iPhone app: it exists and is coming. iOS gives apps no call audio.

**Say:** "Today the live demo is the Mac. Answer the iPhone on the Mac and the listener can hear the caller. Android early access is speaker mode: the app listens through the phone microphone while the call is on speaker. We have not verified that on a real call. An iPhone app exists and is coming. iOS does not give apps call audio, so that app is not how we hear an iPhone call today."

## Slide 10 — What is already in the world

**Message:** Real-time and on-device scam detection already exist. Our demo is the two-answer card on this Mac.

**Visual:** Three names in equal type: Google Scam Detection on-device, Hiya AI Phone, Truecaller. Under them, four short lines: two answers (human or AI, and scam or not), plain evidence, live on your own Mac, counter at 0.

**Say:** "Those products do real-time or on-device scam detection. Leave them unranked. Say the differences the room can see: human or AI and scam or not as two answers, the evidence line, the call heard on your own Mac, a verdict about every 3 seconds that can change mid-call, and the counters at 0. Tell does not speak to the caller."

## Slide 11 — What is next

**Message:** The fine-tuned head stays out of today's detector until we are ready to show it. The iPhone app and a verified Android call are still ahead.

**Visual:** A short list. "In today's demo" versus "Not in today's demo". The second column holds the fine-tuned head, a verified Android call, and iPhone call audio inside an app.

**Say:** "Show the fine-tuned head when it is in the build. Verify Android on a real call. Keep the iPhone path honest about what iOS allows. Until then, the demo is the Mac."

## Slide 12 — It can be wrong

**Message:** Tell can be wrong.

**Visual:** That sentence, large, in the same type as the product caveat. Under it: "If a call asks for money or a code, hang up and call back on a number you already have."

**Say:** "If the card and your doubt disagree, hang up and call back on a number you already have. That advice does not depend on which cell was filled."
