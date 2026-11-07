## What and why
<!-- One or two sentences. Link the issue: "Closes #NN". -->

## Checklist
- [ ] `make test` green locally (CI runs `make test` + `make eval`)
- [ ] `make eval` green; if `thresholds.py` changed: `THRESHOLDS_VERSION` bumped and before/after numbers below
- [ ] One specific lesson added to the relevant `skills.md` (format `YYYY-MM-DD · domain · lesson`), or "none" with a reason
- [ ] New env vars listed in `.env.example`; new deps added to `requirements*.txt` **and** `make lock` re-run

## Privacy impact
- [ ] No new network path on the analysis side (`tests/test_privacy.py` still passes, nothing new in its allowlist)
- [ ] Caller audio and transcripts are not written to disk, logged, or sent anywhere new
- [ ] If this touches `privacy.py`, `localhost.py`, `limits.py` or `tests/test_privacy.py`: a decision is logged in `pm/DECISIONS.md` and a second person reviews (CODEOWNERS)

<!-- Describe anything that leaves the device or the process, or write "none". -->

## How I tested
