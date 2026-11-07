# Connecting Doublespeak to real calls: findings so far (2026-11-07, pre-demo)

Status: researchers for Apple/Mac and Android are done; telephony/HFP, legal/consent and the connector architecture designer are still running. The streaming designer is done. Search depth was thin (6-15 searches, mostly snippets): every "high confidence" below is from an Apple/Android primary doc; everything else needs a hands-on test.

## Constraints (cannot be broken)
- Passive only (D-003): never speaks to the caller. Caller audio never leaves the device; loopback to local engines only (D-004, D-009). Honest about what it can and cannot hear.
- Demo: Sunday 11 AM, Macs + iPhones. Product after.

## What we learned
### iPhone
- No third-party access to cellular call audio. CallKit = call events only. iOS 26 call screening is system-only. VoIP apps only get their own calls. (medium-high)
- BUT iPhone calls can be relayed to a Mac (Settings > Phone > Calls on Other Devices; same Apple Account, Wi-Fi, Bluetooth). The caller then plays through the Mac. So the Mac can hear the caller. (relay: high; capture of relayed audio: untested)
### Mac capture options (all caller-side only, which is what we want)
1. BlackHole 2ch + a Multi-Output Device (speakers + BlackHole); the app reads "BlackHole" as an input device. Lowest risk tonight. Needs a driver install; volume keys disabled on Multi-Output. Works in a browser (getUserMedia deviceId) or Python (sounddevice/ffmpeg avfoundation). Works for any app that plays to the default output: Phone/FaceTime, WhatsApp, Zoom, Meet.
2. Core Audio process tap (macOS 14.4+, Swift): per-app capture, one audio-capture permission prompt, no driver. Best product path; poorly documented; copy the open-source AudioCap sample.
3. ScreenCaptureKit audio: fallback; needs Screen Recording permission; Sequoia re-prompts monthly.
4. Browser getDisplayMedia: tab audio reliably; system audio only on recent Chrome (reported 141+, one source): fragile.
5. Speakerphone + Mac mic: zero setup, degraded (room noise, double acoustic path hurts the anti-spoof model). Fallback.
- Do NOT use Apple's call recording: it announces itself to both parties (breaks passive).
- Mac as a Bluetooth headset for the iPhone: reported not viable (low confidence). Telephony researcher is checking HFP properly.
### Android
- No legitimate third-party API for call audio: VOICE_CALL/DOWNLINK need CAPTURE_AUDIO_OUTPUT (system only). Accessibility workaround is banned by Play for call recording and Android 17 tightens it. Default dialer/InCallService gives no PCM. CallScreeningService gives metadata before answer (number, verification), not audio.
- Demo path: speakerphone + mic in a foreground service (sideloaded APK) streaming to the laptop over USB reverse tunnel or LAN, or just the laptop mic. Be honest in the UI ("speaker mode").
- Real product on Android needs an OEM/carrier partnership; Pixel Scam Detection and Samsung call screening are OS-internal, which validates the on-device idea and is the competition.
### Streaming (design done)
- Ring buffer 30 s, 3 s hop, voters on the last 10 s every 2nd tick, incremental STT with a revisable tail, LLM only on enough new text. Budget 2 s per 3 s hop; shed LLM, then neural, then lengthen the hop; never shed STT/regex.
- A stabiliser wraps scorer output (scorer.py untouched): warm-up 8 s/20 words, escalate in 2 ticks, de-escalate in 5 ticks + 20 s dwell, sticky evidence, red only with corroboration (two intent families incl. payment/credential, or p_scam >= 0.8), latch until dismissed, AI-undisclosed is amber at most. WebSocket /stream contract designed. MVP slice ~19 h of human work; targets: 0 red false alarms in 60 min of human speech, median time-to-detect < 20 s.
- NEEDS A HUMAN DECISION: the stabiliser changes what tier is *displayed* (it does not edit scorer.py). Rules say any tier-logic change needs sign-off.

## Draft architecture (to be confirmed by the connector designer)
Engine (existing FastAPI) + pluggable AudioSources feeding `WS /stream`:
- Phase 0 (tonight): browser source picker (input device incl. BlackHole, optional tab audio) -> PCM over WebSocket -> stream engine -> live UI. iPhone via Continuity on the Mac. Speakerphone/mic fallback.
- Phase 1: native macOS menubar helper (Core Audio process tap) -> loopback WebSocket with a token handshake.
- Phase 2: Android companion (speaker mode, honest label), CallScreening metadata.
- Phase 3: partnerships (OEM/carrier), HFP gadget if the telephony research supports it.

## Hands-on tests nobody can answer from the desk (do these first)
1. Does a Continuity-relayed iPhone call play through the Mac's default output (so BlackHole hears it)? What sample rate / quality?
2. Does the anti-spoof model still work on telephone-band relayed audio?
3. End-to-end latency BlackHole -> browser -> /stream -> verdict.
4. Android demo phone: does a foreground-service mic get real audio or silence during a speaker call?

---
## Added after the remaining reports landed

### Telephony / Bluetooth (researcher, thin depth, mostly one 2025 source)
- Bluetooth HFP "Doublespeak box": a Raspberry Pi / Linux box (BlueZ + PipeWire + WirePlumber + oFono) pairs with the phone as a hands-free car-kit and receives BOTH sides of the call, passive, nothing new in the path. Verified by one Mar-2025 write-up (tested on a Samsung; iPhone pairing only per one forum comment). Audio is mono CVSD 8 kHz or mSBC 16 kHz. Use the Pi's onboard Bluetooth (cheap USB dongles break SCO). A Mac cannot present as a headset to an iPhone. This is the only iOS-friendly passive route to both sides of a cellular call. UNTESTED: does the target iPhone pair and route audio; quality loss for the models at 8 kHz.
- Carrier conditional forwarding to a self-hosted SIP DID: NOT passive (our box answers, caller may notice), carrier and SIP provider carry the audio (truthful claim: "we run no cloud service and analysis is local"), iOS 26 MMI codes reportedly flaky. Active "screener" mode, post-hackathon at best.
- Cloud telephony (Twilio/Telnyx/Vonage media streams): rejected, breaks the promise. Wired TRRS/USB tricks: unreliable, skip.
### Legal / consent / market (researcher; not legal advice; many items search-summary only)
- Federal wiretap: one-party consent, the recipient is a party: low risk. All-party states (CA, FL, IL, WA, PA, MD, MA...): nobody answered whether LIVE, LOCAL, NON-RECORDED analysis counts as interception; counsel must say. CA CIPA vendor-as-eavesdropper theory (Ambriz v. Google, 2025) targets vendors that can use the data: a purely local app with no telemetry and no cloud fallback has no vendor to target; ANY cloud ASR/LLM fallback would reintroduce the exposure.
- Biometrics: spoof/real scoring that stores and matches nothing is probably not a "voiceprint", but BIPA is unsettled (Gunderson v. Amazon, 2025): never persist embeddings, never match speakers.
- "AI, undisclosed" binds no duty on the user; it is a factual claim about a caller and can invite defamation/UDAP questions: word it as "no AI disclosure heard". FTC: substantiate every accuracy claim.
- Safeguards: per-session start by the user, RAM only, no logs/transcripts/embeddings/crash dumps, consent copy ("Doublespeak listens to this call on your device only to warn you. Nothing is recorded or sent anywhere. Tell the other person if your state requires it."), demo only on consenting teammates' calls or synthetic/replayed audio.
- Claims we MAY make: runs on the device; nothing sent or stored by default; probabilistic warning; never speaks to the caller. MAY NOT: "legal everywhere", "100% private" while any cloud path exists, "detects all scams/deepfakes", "complies with <statute>", any accuracy figure we have not measured.
- Competitors: Google Scam Detection (Pixel 9/10, Samsung S26; Gemini Nano on-device, free), Apple iOS 26 Call Screening (system-only), Truecaller AI Call Scanner (cloud-ish, tap to scan), Hiya AI Phone ($9.99/mo, live alerts + deepfake), Robokiller (blocklists). Differentiation that is REAL: the four-way human / disclosed AI / undisclosed AI / scam taxonomy with evidence, cross-platform design, auditable local processing (OS-measured 0 bytes). NOT real: "on-device scam detection" (Google does it free) and "voice-clone check" (Hiya, Truecaller).
- Questions for a lawyer: (1) does live local non-recorded analysis need the other party's consent/notice in all-party states; (2) is a spoof/real classifier a voiceprint under BIPA/CUBI/WA/GDPR; (3) wording and duty-of-care for labelling a caller "AI, undisclosed" or "scam" to older users.
### Connector design (system designer)
- Every source emits Frame{seq, t_ms, side in far|near|mix, PCM16 16 kHz mono}. The engine analyses only `far`, or `mix` flagged degraded with confidence capped; the user's own voice never gets a caller verdict.
- One loopback WebSocket `/ws/stream`: 12-byte header + PCM, 20-100 ms frames; token handshake (256-bit per-launch token in a 0600 file, never in a URL), Host and Origin checks, bind 127.0.0.1 only; LAN is NOT acceptable (an Android or Pi companion uses `adb reverse`/USB, or analyses on-device and sends only verdicts: new ADR).
- Server: RAM-only ring buffer per session (30 s, cap 120 s), one in-flight analysis per session, drop-oldest backpressure, wipe on stop/timeout/kill/exit; `POST /panic` wipes everything. Persistent un-hideable LISTENING bar + hard Stop button + hotkey.
- Packaging: Swift menubar app for the real product (TCC permissions attach to the signed bundle; Developer ID needed); hackathon = no signing.
- Human decisions: is "analysed in RAM, never stored" acceptable per jurisdiction; Swift helper or browser-only first; LAN/USB companions allowed?; show a capped verdict in `mix` mode or refuse; file ownership.
### Streaming design (see above) plus: red alert needs corroboration, latches until dismissed; "Not a scam" feedback button (D-007 opt-in); never say "safe", "legal", "illegal", "fraud confirmed"; 0 red false alarms in 60 min of human speech is the target; chime off by default.
### Verified today
- Pellav2 weights are byte-identical to the Hub (SHA-256), load with weights_only=True, and on 2 clips score a real human recording (JFK) 0.001 and macOS TTS 0.999; 1.6 s per 3-window vote on CPU, 0.15 s on Apple MPS (7-11 s load). Two easy clips is NOT evidence of generalisation: it needs the wild eval on Gradium/ElevenLabs/VoiceStudio/Qwen clips and real human phone recordings.
