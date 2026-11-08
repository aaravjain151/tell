# Doublespeak from the user's chair

Written from the user's side, not the engineer's. Status 2026-11-07. Claims here follow `pm/FINDINGS-call-connection.md` and `docs/DETECTION-LAYERS.md`; nothing below is a measured accuracy.

Truecaller's site could not be fetched from the build environment (the fetch tool was refused), so the structure borrowed for the app and site is generic to the category: a home that shows protection status, a block list, a history, a settings page, a plain how-it-works, a platform table and an FAQ. No wording, imagery or layout from any competitor is used.

## Who uses it

| Person | The call they dread | What they need from us |
|---|---|---|
| An older parent | "Your grandson is in jail, send gift cards." | One calm sentence on screen, a big "Call someone you trust" button, no jargon, no settings to find. |
| A busy professional | A "bank fraud department" call during a meeting. | It must start by itself; a glance tells them voice (human or AI) and wording (scam or not) separately. No extra taps. |
| A small-business owner | Fake invoice and supplier-change calls to the front desk. | A block and spam list the whole team can add to, a call history they can look back at, a short plain line on what to say. |

## The moments

1. Before the call. Doublespeak is armed and says so on Home. They should never think about it. They check once: what stays on the device?
2. The call rings. Nothing happens. No popup, no sound. Unknown numbers are the only thing a block list can act on (the Mac route does not see the number today).
3. I pick up. Listening starts by itself, caller side only. A thin bar says Listening. This is the best feature and the one thing we protect.
4. During. One verdict card that changes in place and can change its mind. Two separate answers: human or AI, scam or not, each with the evidence. A red banner only for a corroborated scam pattern, with a Dismiss.
5. After. "Nothing was heard" if the call never played through the Mac. Otherwise: block this caller (they type the number), report as spam (stays local), call a trusted person, mark "not a scam" to teach the page.
6. A week later. History (opt-in, encrypted, on the device) shows which calls were flagged and why. Nothing else is kept.

## Why they would use it

- It works without being asked. Everything else on this list is secondary.
- It tells them why in words they would say out loud ("They asked you to pay with gift cards").
- It does not record, upload or talk to the caller. They can see the bytes-out number.
- It is honest about doubt: "Not sure yet" is a real answer.

## What they will want next (ranked)

1. Auto-listen on pickup, everywhere they take calls.
2. Trusted-contact alert (today: one tap to call a person; later: tell them).
3. Block and spam list, with local reporting.
4. Call history with verdicts, on device and opt-in.
5. Quiet versus sensitive mode.
6. Plain advice on what to say or do next.
7. Weekly summary, local ("3 calls flagged, 0 sent anywhere").

## What they will NOT want

- Alert fatigue and false alarms: one red banner per scam pattern, latched, dismissible; amber is a single quiet line.
- Nagging: no "rate us", no upsell on the live screen, no sound by default.
- Jargon: no "p_ai", "spoof", "tells" on the main view. Scores sit behind the word "How serious".
- Fear: no skulls, no countdowns, no "you are being scammed" as a fact. We say "possible scam pattern".
- The cloud: no accounts, no upload, no analytics.
- Anything that records: no audio saved, no transcript in history.

## Ship for the Sunday demo, ranked

Ship now (exists or is a day of work in the page):
1. Auto-listen on pickup with the listening bar, the changing verdict card, 2x2, scores, timeline, transcript, red banner and Dismiss. (exists)
2. Home with armed status and the privacy proof row (OS-measured bytes out). (this PR)
3. Trusted people. (exists, moved to its own page)
4. Block this caller and Report as spam after a call, degrading to this browser when the engine has no block list. (this PR, depends on the engine's `/blocklist`)
5. History page over the existing opt-in encrypted `/history`. (this PR)
6. Settings: plain explanation of auto-listen, quiet versus sensitive display, what is stored, Delete everything. (this PR)

Later:
7. Block-list lookup during a call (needs the number: iPhone app or Android dialer role).
8. Trusted-contact alert that actually notifies someone (needs a send path that is not the cloud).
9. Weekly summary.
10. Android real-call verification; the iPhone app (iOS gives apps no call audio, so iPhone calls are covered through the Mac).
