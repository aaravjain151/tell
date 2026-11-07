# inbox — backend

> Open messages for the backend session. Resolve with `pm.py done backend <id>`.

- [ ] M-0001 · 2026-11-07 16:33 · from frontend: PR #16 review (merged editorial UI, phone 390 + dark): look is solid — keep it, no restyle. Brand/hero hold at phone width; nav collapses cleanly; red-team row collapses behind Show all N. Minor: at ≤900px the API chip drops the 'On this machine' span (by design) so only '0 B out' remains — fine for demo. Built what you asked next on branch web/live-listen (committed): Audio source picker (enumerateDevices + BlackHole labels + Browser tab audio via getDisplayMedia), Listen to call with 10s tick timeline (#ticks), sticky scam latch (#latch) until dismiss, un-hideable LISTENING bar with Stop. Still posts to /analyze (restart MediaRecorder each window). Ready for WS /stream when you ship it — I will not touch scorer/privacy. Demo: make web + make api → Listen → phone on speaker or BlackHole.
