# Q&A prep: the 15 hardest questions

Answer in two or three sentences, then stop. If you don't know, say "we haven't measured that" and offer what you did measure. Never use a percentage, "safe", "legal", "only", "first" or "better than". The owner of each answer is shown in brackets; anyone can answer if that person is mid-sentence elsewhere.

## Privacy track

**Q1. What exactly leaves the device? [Aarav]**
On the laptop route, nothing: caller audio goes from the call app to the engine over loopback (127.0.0.1), is analysed in RAM, and is dropped. Only three modules may open a socket, the one that can carry audio refuses any host that is not loopback, and a test scans the analysis code for network imports, and the page shows caller-audio bytes sent, external bytes and the operating system's own count of outbound connections from the engine, all 0 in the demo. On the phone route, the audio does leave the phone: it goes over the USB cable to your own computer, never Wi-Fi or a server. We say "your own devices", not "never leaves the phone" (decision D-012).

**Q2. Your "0 bytes" is your own code counting. Why trust it? [Aarav]**
Two of the numbers are our counters, and the third is not: `os_outbound_count` comes from the operating system's list of the engine process's connections, so it does not depend on our code being honest. You also saw it run with Wi-Fi off. Better still, run `lsof -i` or Little Snitch yourself during a call; the code is open for that.

**Q3. Do you record calls? What about two-party consent laws? [Aarav]**
No audio or transcript is written to disk. It is analysed in memory and wiped when the call ends. History is off by default; when you turn it on it is encrypted and keeps only time, verdict and reasons. Rules on listening to calls differ by place: in the US some states require everyone's consent. Whether real-time analysis without recording counts as interception varies, and we are not lawyers. So the app tells users to inform the other person where their law requires it. The opt-in labelled-capture tool for building test data needs four explicit flags, including a consent note, and prints a "SAVING AUDIO TO DISK" banner.

**Q4. Isn't a phone app that listens to calls a privacy risk in itself? [Aarav]**
That is why it is built the way it is: no accounts, no cloud, no analytics or third-party SDKs, loopback-only URLs (a test checks that), caller side only on the Mac, and it never speaks to the caller. The Mac app has no option to hide its icon while it is listening, so you can always see when it is on.

## Technical

**Q5. How do you detect a cloned voice? [Samarth]**
Several local voters: Pellav2, an open deepfake detector built on a large speech model, scores 4-second windows. A second open anti-spoof model and simple acoustic measures (pauses, breath, pitch movement) add evidence. Fixed rules, not a model, combine them, so the same audio always gives the same answer and every answer lists its reasons. Separately, Whisper and a small local language model read the words for scam patterns (payment, codes, urgency, impersonation, secrecy).

**Q6. How accurate is it? [Samarth]**
On small sets, counts only. On clean audio the voice check caught 14 of 28 AI clips we generated, with 1 of 10 human clips flagged, and that one human was reading a script that says "I'm an AI". Qwen clones were caught 2 of 10, which is our weak spot. Twelve people recorded on phones: none flagged as AI. Most human audio is one speaker (Sanath), so any separation may partly be his microphone. All of this is in `pm/AUDITS.md`. We do not publish an accuracy figure.

**Q7. What about false alarms? Grandma gets a red banner on her real grandson. [Aarav]**
Red needs corroboration: two kinds of scam wording, one of them a payment or code request, plus agreeing scam ticks. A single tick never alerts, and it does not flap: it escalates in two ticks and calms down only after five. In our phone-memo test no human crossed the voice threshold. We did find a real weakness: on very low-bitrate audio with packet loss, Pellav2 calls many real people synthetic, and we are investigating it before we touch any threshold. Every alert can be dismissed. An optional, on-device setting learns how sensitive you want alerts, and it can never quiet a corroborated red.

**Q8. Phone audio is 8 kHz and compressed. Does any of this work on a real call? [Aarav]**
Phone-band and replayed audio is the hardest case for voice checks: it strips the cues detectors use. That is why the voice answer can say "not sure" instead of "human", and why the scam-wording answer is separate and still works. On the Mac route, the iPhone call audio is tapped digitally from the call app. On Android it is speakerphone audio picked up by the phone's mic. We tested the codecs with simulated channels. Real-call verification on Android is in progress.

**Q9. Why does the demo use a Mac if you say phones first? [Aarav]**
The models (a 600M-parameter voice model, Whisper and a 3B language model) don't run well on a phone yet. So the brain runs on a computer you own, and the phone is the ears. The live demo you saw is that brain. Android is in early access over USB; automatic start on pickup is being built on Android now; iPhone is coming soon. iOS gives apps no call audio, so the iPhone version works differently.

**Q10. Why not just use Google's on-device scam detection? [Aarav]**
If your phone has it, use it. Google, Hiya and Truecaller all do real-time or on-device scam features, and we don't rank ourselves against them. What Tell shows is different: whether the voice sounds human or AI and whether the words match a scam, as two separate answers, each with its evidence. It runs on open models on hardware you own, with a counter you can check.

**Q11. Can an attacker beat it? [Samarth]**
Yes. A human scammer has a human voice, which is why the wording check exists. A new voice engine the detector never saw can score as human: Qwen3-TTS is our current blind spot. We studied what a listener hears in it (the voice is too clean, and pauses at sentence ends are half as long). Those cues are logged in shadow mode, not used, until we have more speakers. A fine-tuned head on 80 speakers helped on replayed audio in our tests but raised false alarms slightly, so it is not in today's detector.

## Gradium

**Q12. How did you use Gradium? [Sanath]**
Three ways. I cloned my own voice with Gradium (with my consent) to build paired red-team clips: same script, real versus clone. Those clips are part of every evaluation row, and the voice check catches them more often than the Qwen clones. Our red-team tool generates new attacker calls with the Gradium CLI. Gradium TTS can also speak the verdict to the user; only our fixed verdict text is sent, never the caller's words, and it is off in the demo. The live attacker uses Qwen3-TTS instead because it runs offline on the laptop, so the demo works with Wi-Fi off.

## Business

**Q13. Who pays? [Aarav]**
Our hypothesis, not yet validated: adult children paying for a parent's protection (a family plan), and small businesses whose front desk gets fake-invoice and "bank" calls. A credit union or carrier could distribute it. We have not run pricing interviews yet; that is the next step.

**Q14. Truecaller and Hiya have millions of users. Why would anyone switch? [Aarav]**
They mostly identify callers by number reputation, built from a shared database that users contribute to. Tell has no shared database and uploads nothing: it judges what is said and how it sounds, on your own devices, even when the number is new or spoofed. The two approaches can sit side by side; our block list is local-only.

## Ethics

**Q15. You built a voice-cloning scam bot. Isn't that dangerous? [Sanath, then Aarav]**
Sanath: "It's my voice, cloned with my consent, and I'm standing here." Aarav: It is a test tool that plays only through the laptop speakers. It has no route into phone calls, virtual mics or conferencing. A consent record is required for every voice, a red TEST ATTACKER bar stays on screen, and a spoken AI disclosure is on by default. The script is fixed and fictional ("Example Bank", case 000-TEST), with a guard that replaces anything off script. You can't build a detector without realistic attacks, and the open models it uses are already public.

## If asked something not on this list

- "Have you tested it on real scam calls?" No real scam recordings were used: only consented voices and scripted scenarios.
- "Does it work in other languages?" Not tested. Whisper is multilingual, but the scam-wording rules are English.
- "What's the latency?" In a replay, 0.3 to 1.0 s per tick after each 3 s of audio. Red needs two agreeing ticks, about 6 s after the evidence arrives.
- "Can I try it?" Yes, at our table after the session. Android early access by email from the site.
