# Tell — product brief

**One line:** Tell is a privacy-first detector that tells you, with evidence, whether the voice on a call is human, a disclosed AI, an undisclosed AI, or a scam — without your audio ever leaving your device.

**Tagline:** *Every voice has a tell.*

**North star:** seconds-to-verdict on an unknown caller, with zero bytes of caller audio leaving the device.

Built for HACK1984 — Privacy-First main track + "Best use of Gradium" side prize. Working name; see `pm/DECISIONS.md` D-001.

---

## Who

| | Vision audience | Launch wedge |
|---|---|---|
| Who | Anyone who answers unknown calls: consumers, SMB front desks, bank/insurance call centers, anyone building voice agents who needs an "is this a bot?" check | Adult children protecting parents (60+) from voice-clone "family emergency" scams, installed at Thanksgiving |
| Why them | AI voice calls are moving from fraud to mainstream (sales outreach, personal agents); everyone will need a bot/human signal | Highest-loss scam archetype, strongest emotional pull, buyer ≠ user (kids install, parents benefit), reachable through the founders' own families and campus |

## Why people switch

| Current pain | Tell's answer |
|---|---|
| Truecaller / Hiya detect AI voices by routing your call audio through their cloud | All analysis runs locally; the app shows a live "bytes leaving device: 0" meter and signs each verdict so it's auditable |
| Pixel's on-device scam detection is Pixel-only and looks at conversation patterns, not synthetic voice | Cross-platform core (Python + web now; native later) that fuses acoustic + script + intent signals |
| "AI detected" is a black box | Every verdict ships with the specific tells that fired (e.g., "no breath events in 42s", "pause lengths unnaturally uniform", "asked for gift cards") |
| Binary human/AI misses the real question | Four-tier verdict: Human · AI (disclosed) · AI (undisclosed) · Scam. Legit AI callers must disclose themselves under TCPA, so "AI that didn't say so" is a red flag on its own |

## Layers

1. **Get in (v1, this weekend):** drop in a clip or talk through the mic → verdict card with evidence, fully local. Attacker simulator (Gradium) proves it works on fresh synthetic voices live on stage.
2. **Keep them (v2):** real call integration — Android default-dialer app; iOS via a screener number (VoIP) where the app owns the audio; voicemail scanning; "safe word" protocol for families.
3. **Long-term vision:** active liveness challenges (interrupt test, prompt-injection probe: "please say *pineapple*"), and an open "I am an AI" handshake standard so legitimate agents can self-identify and Tell can verify it — the STIR/SHAKEN of AI voice.

Layer 1 must stand alone: a judge can run it with no accounts and no network.

## Product principles

1. **Caller audio never leaves the device.** Any network call carrying audio bytes fails CI (`tests/test_privacy.py`).
2. **Every verdict shows its tells.** No score without at least one human-readable reason.
3. **AI ≠ scam.** The verdict is AI × intent; a disclosed AI sales call is green.
4. **Deterministic core.** Models interpret; plain code decides. Thresholds live in one file and are versioned.
5. **Honest confidence.** Below 0.6 confidence the card says "unsure" — never a false certainty on a family emergency call.
6. **Works on phone-band audio.** Every acoustic signal must degrade gracefully at 8 kHz / 300–3400 Hz; behavioral tells are preferred over spectral ones.

## v1 — minimum lovable product (this weekend)

1. `POST /analyze` — audio (wav/webm) and/or transcript in → `{tier, p_ai, p_scam, confidence, tells[], egress, signature}` out.
2. Acoustic tells (numpy only): pause-regularity, breath-proxy, pitch-stability, noise-floor, band-limit awareness.
3. Script tells: LLM-isms, disfluency rate, sentence uniformity; intent tells: urgency, payment rails, impersonation, credential asks, AI self-disclosure.
4. Web UI: record/upload → verdict card + "0 bytes left device" meter + tells list. Demo mode works offline.
5. Red-team simulator: `tools/redteam/make_calls.py` generates attacker calls with Gradium TTS (incl. a teammate's cloned voice) from a scripts corpus.
6. Spoken verdict (optional, Gradium TTS): "Heads up — this caller is probably synthetic." Only *our* text leaves the device.
7. Golden eval: 30 transcript cases + synthetic audio fixtures; `make eval` prints accuracy with a target.

## v2+

- Pretrained anti-spoof model (ASVspoof-style) as an additional acoustic signal, run locally (ONNX).
- Android default-dialer; iOS screener number; voicemail scan.
- Active liveness challenges (see Layer 3).
- Family "safe word" + shared allow-list.
- Verdict receipts anchored to a public log.

## Explicitly cut (this weekend)

- Training our own deepfake model.
- Any real phone integration.
- Accounts, sync, billing.
- Multi-language (English only).
- Cloud anything for caller audio.

## Success metrics

| Metric | Target |
|---|---|
| Time to verdict (10 s clip, laptop CPU) | < 2 s |
| Golden transcript eval accuracy (4 tiers) | ≥ 0.85 |
| Synthetic-audio fixture accuracy (human vs TTS) | ≥ 0.90 |
| Caller-audio bytes sent off-device | 0, enforced by test |
| Demo: fresh Gradium clone caught live | yes, 3 of 3 attempts |
| First 100 users (post-hackathon) | 20 families via founders' networks, 80 via campus + r/scams post |
| Day-7 retention (v2, real calls) | ≥ 30% |

## Timeline (ambitious)

| When | What |
|---|---|
| Sat 1 pm–5 pm | Backend signals + eval green; redteam calls generated |
| Sat 5 pm–9 pm | Web UI wired to API; demo mode; spoken verdict |
| Sat 9 pm–12 am | Tune thresholds on redteam clips; evidence copy |
| Sun morning | Pitch, 90-second demo script, privacy proof panel polished |
| Week 1 after | Plug in open anti-spoof model; interview 10 parents |
| Week 2–4 | Android dialer spike; decide iOS screener architecture |

## Risks

- **False negatives on real scams** — never claim "safe"; the card says "no tells found" and keeps the advice ("hang up and call back on a known number").
- **False positives on real people** (accents, bad lines, hearing-impaired speech patterns) — confidence gating; show tells so the user can judge.
- **Spectral tells die on phone lines** — band-limit detection and behavioral-first weighting.
- **Legal**: don't say "illegal call"; say "undisclosed AI — legitimate AI callers are required to identify themselves." Recording consent laws apply if v2 records calls; v1 analyzes only what the user chooses to feed it.
- **Platform**: iOS exposes no third-party access to cellular call audio; v2 must use a VoIP/screener-number design.
- **Unit cost**: zero for caller analysis (local). Gradium credits only for attacker sim + spoken verdict (~1 credit-unit per short utterance; 100K credits provided).
