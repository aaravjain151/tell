# Q&A prep: the hardest questions

Answer in two or three sentences, then stop. If you don't know, say "we haven't measured that" and offer what you did measure. Never use a percentage, "safe", "legal", "only", "first", "better than", "detects all" or "100% private". When you give a count that was tuned on the same clips, say "in-sample" before the number. The owner of each answer is shown in brackets; anyone can answer if that person is mid-sentence elsewhere. Hidden backup slides in the deck: **Why us**, **Who pays**, **Threat model**, **Later: deepfake calls at work**, **Illustration of the live card**.

## Privacy track

**Q1. What exactly leaves the device? [Aarav]**
On the laptop route, no caller audio: it goes from the call app to the engine over loopback (127.0.0.1), is analysed in RAM and dropped. Three modules, no more, may open a socket, the one that can carry audio refuses any host that is not loopback, and a test scans the analysis code for network imports. On the phone route the audio does leave the phone: it goes over the USB cable to your own computer, never Wi-Fi or a server, so we say "your own devices", not "never leaves the phone" (decision D-012).

**Q2. The 0 on screen: is that a measurement? Why trust it? [Aarav]**
The caller-audio 0 is not a measurement; it is an invariant: the code blocks caller audio from leaving, so it is zero by design. The independent check is the operating system's own count of the engine's network connections: the engine asks the OS (psutil) for non-loopback connections of its own process and children, polled every 50 ms during each analysis; the `/health` figure in terminal C is a snapshot at that moment. Its limits: it can miss a connection shorter than 50 ms or unconnected UDP, and it does not cover Ollama, which is a separate local process; run `lsof -i` or Little Snitch yourself during a call to check both.

**Q3. Do you record calls? Is listening to a call even allowed? [Aarav]**
No audio or transcript is written to disk; history is off by default and, when on, keeps time, verdict and reasons, encrypted (AES-256-GCM, key in the OS keychain). In the US, federal law allows a party to the call to consent (one-party consent, 18 U.S.C. 2511(2)(d)); some states require all parties' consent, and there our position is that we record nothing and no third party receives the content, but courts differ on whether live analysis counts as interception, so the app tells users to inform the other person where their law requires it. In the EU, personal use falls under GDPR's household exemption; a business using Tell would be a controller with full duties. This is not legal advice; we haven't had a lawyer review it.

**Q4. Isn't a phone app that listens to calls a privacy risk in itself? [Aarav]**
That is why it is built the way it is: no accounts, no cloud, no analytics or third-party SDKs, loopback-only URLs (a test checks that), and it never speaks to the caller. What it hears differs by route: on the Mac, only the caller's side; on Android speaker mode, everything the phone's microphone hears, including you and the room. The Mac app has no option to hide its icon while it is listening.

**Q5. Can another app on the same computer read the engine's verdicts? [Aarav]**
Not from another machine: the engine listens on loopback, never on the network. A process on the same computer can call it today; the fix, a per-install token required on every data route so a process without it gets 401, is in progress and not merged yet [owner: put the PR number here once it is open, and if it merges before 11:00 say instead: "every data route now requires a per-install token; a process without it gets 401"]. Until then the demo Mac runs nothing untrusted.

**Q6. Whose consent covers the voices you trained and tested on? [Sanath, then Aarav]**
Sanath's own recordings and clones are his, with his consent. The twelve phone memos came from about four of Aarav's friends with consent relayed by Aarav, not signed per speaker; we are collecting per-speaker consent now, and until it is in, every claim about those 12 memos is labelled as relayed consent. The public voices are LibriSpeech (CC BY 4.0). The memos stay on our own machine and are not in the repo.

## Technical

**Q7. How do you detect a cloned voice? [Samarth]**
Several local voters: Pellav2, an open deepfake detector built on a large speech model, scores 4-second windows; a second open anti-spoof model and simple acoustic measures add evidence. Fixed weights, not a learned model, combine them, so the same audio always gives the same answer and every answer lists its reasons. Separately, Whisper and a small local language model read the words for scam patterns (payment, codes, urgency, impersonation, secrecy).

**Q8. How accurate is it? [Aarav]**
We won't give one number, because any single figure on sets this small would mislead. In-sample, with weights we tuned on these same clips, 13 of our 28 AI clips crossed the line on clean audio (the shipping pipeline shows 14, because one more clip reads an "I'm an AI" script and the disclosure rule counts it). Held out, with the Qwen engine left out of tuning, the voice check caught 1 of 10 Qwen clones. Humans: 0 of 12 phone memos crossed the AI line, and 1 of 10 of Sanath's clips was flagged, the one reading the "I'm an AI" script (`pm/AUDITS.md`).

**Q9. Why should we trust 0 of 12 human memos? [Aarav]**
You shouldn't lean on it much. They are voice memos in quiet rooms, not phone calls, from about four people (the speaker count is our estimate from voice embeddings), and 0 of 12 still has a 95% upper bound of 26%. And there is a misfire we found ourselves: on a very lossy simulated channel (6 kbps Opus with burst loss), Pellav2 called 7 of the 12 synthetic and the fused score came within 0.04 of the line; we are investigating before we touch any threshold.

**Q10. In demo 1, was the "AI voice" the detector or the disclosure? [Aarav]**
Read the reason line under the voice row; we say it out loud on stage. The test bot says it is automated by default, and when a caller discloses, the scorer puts the AI score at the threshold (tier "AI, said so"): that is the disclosure rule, not the voice check. If the reason names the disclosure, the voice check didn't decide it; the words are what turned it red.

**Q11. Why can't you catch Qwen clones? [Samarth]**
Pellav2 is close to blind on Qwen3-TTS in our tests: held out, 1 of 10 caught. We measured what a listener hears, on 8 paired scripts from one speaker: the voice is too clean (cepstral peak prominence about 2.9 dB higher), sentence-end pauses are about half as long (324 vs 649 ms), and pitch moves less and more slowly. Those cues run in shadow mode, logged but not scored, because one speaker and one engine cannot support them yet. We also trained a small head on frozen Pellav2 layers; it is not shipped because on held-out Qwen it didn't keep false alarms as low as today's detector.

**Q12. Why hand-tuned fusion weights instead of a learned fuser? [Aarav]**
Our human audio is mostly one speaker on one microphone, so a learned fuser would mostly learn that microphone. Fixed weights are few, readable and auditable, and they give the same answer for the same audio. We concede they were chosen on these same clips, which is why we say "in-sample" and report the held-out Qwen count next to it.

**Q13. What was Pellav2 trained on? [Samarth]**
The model card doesn't document its training data, so we can't tell you. LibriSpeech, which our head study uses for real voices, comes from LibriVox, so there may be overlap with whatever Pellav2 saw; treat our real-voice numbers on LibriSpeech with that in mind. We pinned the exact weights by revision and SHA-256.

**Q14. Phone audio is 8 kHz and compressed. Does any of this work on a real call? [Aarav]**
Phone-band and replayed audio is the hardest case for voice checks. That is why the voice answer can say "not sure" instead of "human", and why the scam-wording answer is separate. On the Mac route the iPhone call audio is tapped digitally from the call app; on Android it is speakerphone audio from the phone's mic. We tested codecs with simulated channels; a real call on Android is not verified yet.

**Q15. Why does the demo use a Mac? [Aarav]**
The models (a 600M-parameter voice model, Whisper and a 3B language model) don't run well on a phone yet, so the brain runs on a computer you own and the phone is the ears. Android: working prototype, speaker mode, real call not verified yet. iPhone: iOS gives apps no call audio, so iPhone calls work today through the owner's own Mac, and the iPhone app is in progress.

**Q16. Can an attacker beat it? [Samarth]**
Yes. A human scammer has a human voice, which is why the wording check exists, and a voice engine the detector never saw can score as human: Qwen3-TTS is our blind spot today. Red needs two kinds of scam wording, one of them a payment or code request, plus agreeing ticks, so a single phrase never alerts.

**Q17. False alarms: grandma gets a red banner on her real grandson? [Aarav]**
Red needs corroboration: two kinds of scam wording, one of them a payment or code request, plus agreeing scam ticks. It escalates in two ticks and calms down after five, every alert can be dismissed, and an optional on-device setting tunes how sensitive alerts are, but can never quiet a corroborated red. The weakness we know about is the lossy-channel misfire in Q9.

## Gradium

**Q18. How did you use Gradium? [Sanath]**
Gradium was our sparring partner. I cloned my own voice in Gradium (with my consent) for our test scripts, so each fake has a real twin. That is how we found that on Gradium audio replayed through a simulated room and phone codec, the open detector scores below a coin flip (AUC 0.42), and our trained head lifted it to 0.82 with Gradium held out of training (`docs/HEAD-FINETUNE.md`; a second fold seed gave 0.72; 440 real and 72 fake windows; the head is not shipped). Gradium received text we wrote and nothing else, never a caller's audio or words; the optional spoken verdict, off in the demo, would send our fixed verdict sentence. The live attacker uses Qwen3-TTS because it runs offline on the laptop.

## Business

**Q19. Who pays? [Aarav]** (backup slide: Who pays)
Our hypothesis: adult children paying to protect a parent, as a family plan, at around US$5 a month. It is a hypothesis, not validated: tonight we asked people and [N of M people said yes tonight]. Next step is pricing interviews with families.

**Q20. Why not just use Google, Truecaller or Hiya? [Aarav]** (backup slide: Why us)
If your phone has a scam feature, use it; they can sit side by side, and we don't rank ourselves against them. Caller ID checks the number; we check the conversation. Tell also covers calls on your computer, reaches iPhone users through their Mac, and its privacy is something you can audit: open code, a counter and the OS's own connection count.

**Q21. Is there a business product? [Aarav]** (backup slide: Later: deepfake calls at work)
Later, maybe. At work this means listening to colleagues and customers, so all-party consent, employee-monitoring rules and a DPIA come first; not designed yet.

## Ethics

**Q22. You built a voice-cloning scam bot. Isn't that dangerous? [Sanath, then Aarav]**
Sanath: "It's my voice, cloned with my consent, and I'm standing here." Aarav: it is a test tool that plays through the laptop speakers and nowhere else, with no route into phone calls, virtual mics or conferencing. A consent record is required for every voice, a red TEST ATTACKER bar stays on screen, a spoken AI disclosure is on by default, and the script is fixed and fictional ("Example Bank", case 000-TEST), with a guard that replaces anything off script.

## If asked something not on this list

- "Have you tested it on real scam calls?" No real scam recordings were used: consented voices and scripted scenarios, nothing else.
- "Does it work in other languages?" Not tested. Whisper is multilingual, but the scam-wording rules are English.
- "What's the latency?" In a replay, 0.3 to 1.0 s per tick after each 3 s of audio. Red needs two agreeing ticks, about 6 s after the evidence arrives.
- "Can I try it?" Yes, at our table after the session.
