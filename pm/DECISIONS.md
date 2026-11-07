# DECISIONS

## D-001 · 2026-11-07 · Working name "Tell"
**Decision:** Repo and product are called Tell (as in a poker tell). Unverified for trademark/domain/handles; alternates offered in the kickoff message.
**Why:** Short, sayable, literally the thing the product finds. Easy to rename later (grep `Tell`).

## D-002 · 2026-11-07 · Platform for the hackathon: web app on a laptop
**Decision:** v1 is a local FastAPI + single HTML page. No phone integration this weekend.
**Why:** iOS exposes no third-party access to cellular call audio; Android default-dialer is too heavy for <24 h; the judging criteria are provable privacy and a convincing demo, both achievable on a laptop.

## D-003 · 2026-11-07 · Passive detector first; active screener is v2
**Decision:** Ship passive tells (acoustic + script + intent). Liveness challenges (interrupt test, prompt-injection probe) go on NEXT.
**Why:** Team choice with <24 h left. The passive stack is demoable tonight; the active probe is the differentiator to pitch as "what's next".

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
