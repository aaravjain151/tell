# Tell — session handoff (2026-11-08 ~04:00, pre-demo)

Demo: **Sunday 11:00 AM**, HACK1984, 300 Mass Ave. Submit on Devpost by 11:00 (DEMO VIDEO REQUIRED or not judged) → expo demos 12:15–1:30 → top-6 finalists pitch 3min+2 Q&A 1:50–2:20.

## Tracks we target (stack on one project)
- **Privacy-First (MAIN, $5k)** — judged: "what leaves the device, who can read it, can you prove it? would anyone use it?" THIS IS THE ONE.
- **Most Startup-able ($3.5k)** — "who pays, would they pay, why your team?"
- **Best Use of Gradium (side prize, STACKS)** — low-latency voice; we use it for red-team attacker clips (our own cloned voices) + the pre-rendered spoken verdict.
- (Big Brother Award = attendance game, side.)

## State of `main`
Everything core is merged: Tell rename, live stream+stabiliser+listener, two-answer verdicts (human/AI × scam/not), honest "How sure", end-of-call tail scoring, block/spam, personal learning, Mac menubar, Android app + auto-listen, iPhone app+bridge, phones-first site, demo kit, pitch deck.

## OPEN PRs awaiting merge decision (all green unless noted)
- **#96 feat/learned-tells** ← THE BIG ONE. New `learned_tells` voter (logreg on Pellav2 embedding) ON by default, thresholds 2026-11-08.1. Held-out Qwen catch 0.55→0.90 clean, 0 new human false alarms; fixes 3 bugs (Pellav2 every-window, breath_proxy→0, band_limited). Replay chain still 0 (honest). SCORER CHANGE → on merge re-run full suite + golden eval + restart engine + re-verify demo. **Recommended merge.**
- **#94 Gradium spoken verdict** — Tell speaks verdict in Gradium voice, pre-rendered, offline (5 credits used). Best-Use-of-Gradium moment.
- **#95 Android mic-honesty** — honest "phone blocks the mic during calls" message (replaces wrong "USB" error) + JS fix.
- **#97 Android demo mode** — bulletproof stage demo: bundled recorded clip → REAL engine, labeled "RECORDED DEMO". APK at ~/Downloads/Tell-demo.apk (not yet installed on phone).
- **#92 track wording** — Privacy-First+Startup-able+Gradium side prize accurate in README/skills.
- **#93 demo privacy script + 3-min finals cut** (docs/demo/FINALIST-PITCH-3MIN.md).
- **#98 live SSE cap 4→24** (demo robustness).

## Key findings (honest, for the pitch)
- **Android:** confirmed on the owner's Samsung S20 FE — OS SILENCES the mic for apps during a real call, even on speaker (AudioRecord→-1). So real-call capture on the phone is impossible; use the Mac route for live calls. Android works for recorded/other-device audio near the phone (bars move, verified).
- **Mac route (recommended live demo):** answer the iPhone call ON THE MAC (Calls on Other Devices) — no speaker, mic unaffected, auto-starts. WORKS.
- **ML weak spot:** speaker-replay-through-room still uncatchable; biggest data need = Qwen/ElevenLabs clones of ~8-12 MORE consented speakers + real phone-call captures.

## Assets
- Pitch deck (claude.ai Slides artifact): https://claude.ai/artifact/NQq6KXkkC6RHb9MUV4Pnpm
- Launch film v2.1 (28.8s, honest, real human for "sounds human"): /Users/aarav/Downloads/tell_launch_film/out/v2_1/ (16x9/9x16/4x5)
- Consent: 13 signed "Yes I consent" in data/consents/ (gitignored). Covers video; friends' recordings also covered by relayed "we all consent".
- Android demo APK: ~/Downloads/Tell-demo.apk ; auto-listen APK built too.

## Running processes (persist until Mac restart)
- Engine: ONE uvicorn tell.main on :8000 (Pellav2 on MPS, CORS set). `curl localhost:8000/ready`.
- Mac listener: `listen.py --watch` armed. Page: `make web` on :5173.
- Clean (earlier I accidentally stacked 5 engines; killed all, restarted one — don't stack restarts).

## Team ownership (for the pitch + git reality)
- Aarav: product/architecture/live system/all apps/integration (bulk of commits).
- Samarth: original detector prototype + Pellav2 fine-tune pipeline (sam_dev1). Has voice-talk (Qwen attacker) access.
- Sanath: voice dataset (recordings + paired Qwen/Gradium clones), red-team recorder, CI/setup. Backend/infra going forward.

## NEXT STEPS (do these next session)
1. **Merge #96** (re-verify demo after) if owner approves; then #94/#95/#97/#92/#93/#98.
2. Owner to: get the "$5/month?" count for the Most Startup-able slide; place a REAL Mac-route call to rehearse; run 3 demo practice rounds (docs/demo/REHEARSAL.md).
3. Record the required Devpost demo video (launch film v2.1 or a screen-rec of the live Mac demo).
4. Optional: generate Qwen/Gradium clones of the 13 consented speakers → retrain to attack the replay weak spot.
5. CI file still uses DOUBLESPEAK_OFFLINE/WARMUP env names (works via fallback; rename when convenient — needs `gh auth refresh -s workflow`).

## Resume a fresh session
`python3 scripts/pm.py start <domain> --tool claude` prints the briefing. Read skills.md + services/api/skills.md + pm/inbox/<domain>.md + this HANDOFF.md.
