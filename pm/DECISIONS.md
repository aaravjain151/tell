# DECISIONS

## D-001 · 2026-11-07 · Working name "Tell"
**Decision:** Repo and product are called Tell (as in a poker tell). Unverified for trademark/domain/handles; alternates offered in the kickoff message.
**Why:** Short, sayable, literally the thing the product finds. Easy to rename later (grep `Tell`).

## D-002 · 2026-11-07 · Platform for the hackathon: web app on a laptop
**Decision:** v1 is a local FastAPI + single HTML page. No phone integration this weekend.
**Why:** iOS exposes no third-party access to cellular call audio; Android default-dialer is too heavy for <24 h; the judging criteria are provable privacy and a convincing demo, both achievable on a laptop.

## D-003 · 2026-11-07 · Passive, local listen-and-judge. No talk-back.
**Decision:** Doublespeak listens and judges; it never answers or speaks to the caller. Liveness challenges are out of scope (team decision 14:12).
**Why:** Team wants the product to be invisible to the caller. Differentiation is local + open + ensemble + provable, not an active protocol.

## D-004 · 2026-11-07 · Core architectural rule: models interpret, code decides; caller audio never leaves the device
**Decision:** `scorer.py` is deterministic; the LLM (off by default) only adds Tells. The analysis path has no network imports (enforced by `tests/test_privacy.py`); `privacy.record_egress` rejects audio by construction; every verdict is HMAC-signed and bound to the clip hash.
**Why:** The track is judged on "what leaves the device, who can read it, can you prove it" — so the privacy claim is a test and a meter, not a sentence in a deck.

## D-005 · 2026-11-07 · Four-tier verdict (Human · AI disclosed · AI undisclosed · Scam) + "unsure"
**Decision:** AI ≠ scam. Disclosure short-circuits to `ai_disclosed`; scam intent overrides everything; low confidence shows "unsure" with the same advice.
**Why:** Legit AI callers are required to identify themselves under TCPA, so non-disclosure is itself a meaningful signal; and a false "safe" on a family-emergency call is the worst outcome, so we never say "safe".

## D-006 · 2026-11-07 · Gradium: attacker simulator + spoken verdict only
**Decision:** Gradium TTS generates red-team clips (incl. a cloned teammate) and speaks the verdict. Caller audio never goes to Gradium STT in v1; transcripts are pasted or produced locally.
**Why:** Keeps the privacy guarantee intact while using Gradium meaningfully for the side prize.

## D-007 · 2026-11-07 · Data to collect from day 1 (post-hackathon, opt-in only)
**Decision:** Per verdict: tier, p_ai, p_scam, confidence, which tells fired, clip duration, band-limited flag, user correction (thumbs up/down). Never audio, never transcript, unless the user explicitly donates a clip to the eval set.
**Why:** Enough to tune thresholds and measure false positives on real people without holding anyone's calls.

## D-008 · 2026-11-07 · Neural ensemble on-device
**Decision:** Add local neural voters beside the behavioral tells: an open anti-spoof checkpoint (HF or ONNX), local Whisper (faster-whisper) for the transcript, and a local 3B model via Ollama for scam-talk. All are voters; `scorer.py` still decides.
**Why:** Hardcoded acoustic heuristics are a floor. Neural voters catch vocoder artifacts (incl. live voice conversion) that behavioral tells miss. Caller audio still never leaves the device: Whisper and the anti-spoof model run in-process, Ollama runs on localhost.

## D-009 · 2026-11-07 · Renamed Tell → Doublespeak (brand only, for now)
**Decision:** Product name in UI, API title, docs and marketing is "Doublespeak". The Python package `services/api/tell`, the `TELL_*` env vars and the `Tell` record type stay for now so open teammate branches merge without rename conflicts; package/env rename is one later PR once those land. Tagline "Every voice has a tell." kept: a tell is what Doublespeak finds. Supersedes D-001.
**Why:** Team naming decision (T-001). Orwell's "doublespeak" = language that hides what it is, which is exactly an undisclosed AI caller.
