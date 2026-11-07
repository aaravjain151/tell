# ROADMAP

Issues: [Demo: Sunday 11:00](https://github.com/aaravjain151/doublespeak/milestone/1) · [Post-hackathon](https://github.com/aaravjain151/doublespeak/milestone/2). Research behind it: `pm/FINDINGS-call-connection.md` (search depth was thin; unverified items are marked in each issue).

## Demo slice (Sunday 11:00), in order
| # | Issue | Owner | Est h |
|---|---|---|---|
| 1 | #22 Merge train (#19 and #18 already merged; #20 then #21 remain) | Aarav | 3 |
| 2 | #25 Pellav2 voter rebased on merged #19 | Sanath | 3 |
| 3 | #29 Dataset: humans, all engines, Opus 8 kHz | Sanath | 6 |
| 4 | #23 Hands-on: Continuity relay into BlackHole | Samarth + Aarav | 3 |
| 5 | #24 Hands-on: voters on relayed/speakerphone audio | Sanath | 4 |
| 6 | #30 Real-data eval and threshold re-tune | Aarav | 5 |
| 7 | #33 Consent copy and counsel questions | Samarth | 3 |
| 8 | #34 Net-monitor proof row, Wi-Fi-off flow | Samarth (Cursor) | 4 |
| 9 | #32 Pitch positioning and claims | Aarav | 3 |
| 10 | #31 Demo script, fallback, Wi-Fi-off rehearsal | Aarav | 6 |

**Cut line:** items 1-10 are the demo. Above the line only if time remains, and only after decision #35 item 5: #26 streaming backend (14 h), #27 stabiliser (8 h, blocked on a human decision), #28 live UI (10 h). If these are cut, the demo is clip analysis plus file replay, which the fallback ladder in #31 already covers. #35 (decisions, 2 h) should be done first.

## Post-hackathon phases
1. **Harden and ship basics:** #37 CI, CODEOWNERS, lockfile, one-command setup; #41 strict loopback hosts; #36 secure history toggle; #43 windowed scoring and latency budget.
2. **Real Mac product:** #38 Swift Core Audio process-tap helper streaming to the loopback WebSocket.
3. **Other sources:** #39 Raspberry Pi Bluetooth HFP box (only passive route to both sides on iPhone, untested); #40 Android companion in speaker mode.
4. **Beyond:** #42 diarisation and trusted-contact alerts (needs counsel first); partnerships with OEMs or carriers.

## Decisions a human must make (tracked in #35)
1. May the stabiliser change the displayed tier? (blocks #27)
2. Demo capture path: BlackHole in the browser first, or wait for the Swift helper? (blocks #28, #38)
3. Is "analysed in RAM, never stored" acceptable per jurisdiction, and do we demo only with consenting callers? (blocks #33, #31)
4. May companions (Android, Pi) connect over USB only, or also LAN? Design default is loopback/USB only. (blocks #39, #40)
5. Is live streaming in the demo or cut? (sets priority of #26-#28)

## Top risks
- **Relay capture may not work** (#23 untested); mitigation: speakerphone + mic and file replay.
- **Anti-spoof voters unmeasured on phone-band audio** (#24); two easy clips are not evidence. No accuracy claim until #30.
- **Dataset not ready** (needs people and Gradium credits); thresholds stay as-is if so.
- **Merge-train conflicts** (#20 currently conflicts; #18 and #19 already merged) eat time before anything else can start.
- **Model downloads and first-load time on demo Macs** (~1.2 GB anti-spoof model); pre-warm with Wi-Fi off in #31.
- **Legal exposure in all-party-consent states is unanswered** (#33); demo only on consenting callers, avoid unmeasured claims.
- **Competition:** Google Scam Detection already does free on-device scam detection; our claim rests on the four-way taxonomy, evidence and auditable locality.
