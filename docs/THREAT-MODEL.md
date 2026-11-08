# Tell threat model

Scope: the engine (`services/api/tell`, FastAPI on 127.0.0.1:8000), its clients (web page `apps/web/index.html`,
`tools/macos/listen.py`, `tools/ios/bridge.py`, the macOS menu-bar app, the Android app) and the files they keep.
Status words: **mitigated** (a control exists and is tested), **partial** (a control exists with a known gap),
**not mitigated** (we say so). Written 2026-11-08 with the per-install API token (PR fix/local-api-token).

## Assets

| Asset | Where it lives | At rest |
|---|---|---|
| Caller audio | RAM only: upload buffer (`uploads.py` keeps it in memory), 30 s ring per live session (`ring.py`, `session.py`) | never written, except the explicit opt-ins `TELL_DEBUG_SAVE=1` and `listen.py --save-labeled` |
| Transcript of the window | RAM; returned by `/analyze` and in every `/live/events` verdict event (`live.py`) | never written |
| Verdicts (tier, scores, tells, reasons) | RAM; `/live/events`, WS `/ws/stream` | only the opt-in history below |
| History of flagged calls | `secure_store.py`, opt-in `TELL_HISTORY=1` | AES-256-GCM, key in the OS keychain; time, tier, scores, top tell names only |
| Block list | `blocklist.py` | AES-256-GCM file, keychain key; phone numbers never logged |
| Feedback and personal-alert weights | `feedback.py`, `personal.py` | AES-256-GCM, keychain key; labels and small numbers only |
| API token | `~/Library/Application Support/Tell/api_token` (`api_token.py`) | 0600 file in a 0700 directory |

## Adversaries

### 1. Network or cloud observer (anyone off this machine) — mitigated, with a measured gap
* The engine binds 127.0.0.1 (`Makefile` `demo`), refuses non-loopback Host headers (DNS rebinding) and foreign Origins
  (`limits.GuardMiddleware`, `tests/test_api_hardening.py`).
* Caller audio cannot be sent by our code: `privacy.record_egress` raises `AudioEgressError` for any audio-like egress
  (`tests/test_privacy.py`). The "0 B" on screen is therefore **0 by design**, not a measurement; the page now says
  "Caller audio blocked from leaving by code (0 by design)".
* The only socket opener for local engines is `localhost.py` (loopback-only, no proxy, no redirects);
  `tests/test_import_scan.py` fails if another engine file imports a network module; `tests/test_network_guard.py`
  runs the whole pipeline with non-loopback sockets patched to raise.
* Independent check by the OS: `net_monitor.Cumulative` polls the engine process tree every 250 ms from engine start and
  counts every non-loopback connection it sees; `/health` and `/ready` report the count, first-seen time and number of
  distinct remote addresses (never the addresses). Shown as "Engine network connections seen by the OS since start: N".
* Gaps (partial): polling can miss a connection shorter than 250 ms; unconnected UDP (a DNS lookup) has no remote end to
  see; Ollama and VoiceStudio are separate processes and are not counted. Opt-in switches can send content out and are
  listed in `/ready` `privacy_posture`: `LLM_PROVIDER=anthropic` (transcript, dev only) and `GRADIUM_API_KEY` (`/speak`
  sends our fixed verdict text). `TELL_OFFLINE=1` (`offline_guard.py`) stops model libraries from downloading.

### 2. Another local process or user account on the Mac — mitigated (this PR), with limits
Before: any process could read `GET /live/events` (live transcript), `GET /history` and `/blocklist` (decrypted), wipe
everything with `POST /panic`, open sessions, and hold all 4 SSE slots, because a request without an Origin header
passed the guard.
* Now every route except `/health`, `/ready`, `/thresholds` needs the per-install token (`api_token.py`,
  `limits.GuardMiddleware`, deny by default: new routes are protected automatically; `tests/test_api_token.py`
  enumerates the app's route table and expects 401 on each without the token, with a forged Origin, and with a wrong
  token). Constant-time comparison (`hmac.compare_digest`, tested).
* The token is 32 random bytes in a 0600 file in a 0700 directory; a loosened mode is tightened on read (tested).
  Another **user account** cannot read it. `/health` and `/ready` hold counts and switches only (tested: no addresses,
  no transcript, no numbers).
* The SSE `?token=` (browsers cannot set EventSource headers) is accepted on `/live/events` only and removed from the
  request in place before uvicorn writes its access log; a log filter is a second layer (real-uvicorn test).
* The web page gets the token from `make pair-url`'s `#token=` fragment (never sent to any server), keeps it in that
  tab's `sessionStorage`, and removes it from the address bar and history.
* Not mitigated: **malware running as the same user** can read the token file, the browser profile, or attach to the
  processes; file permissions do not separate code running under one account. The token stops other accounts, sandboxed
  apps without home access, drive-by scripts that only know the port, and stray tools; it is not a defence against a
  compromised user account. `make demo`/`make pair-url` print the link to the terminal (scrollback). Escape hatch
  `TELL_COMPANION_ALLOW=1` (OFF by default, logged at start) lets requests with an allowed Origin through without the
  token, which any local process can forge.
* The 4 SSE slots can still be held by a client that has the token (by design; `live.MAX_SUBSCRIBERS`).

### 3. A malicious web page in the user's browser — mitigated
Foreign Origins get 403 before any route runs (`limits.py`), `null` is refused unless listed, CORS never allows
credentials, and the token is required in addition. A page cannot read the token (it lives in our origin's
sessionStorage).

### 4. Phone thief / someone with the unlocked device — partial
* Mac: nothing about calls is stored by default. If history, block list or feedback are on, they are encrypted with a
  keychain key, but an unlocked, logged-in Mac decrypts them for whoever sits at it (the engine serves them to anyone
  holding the token, and the token file is readable by that user). Not mitigated beyond the OS login.
* Android: the app stores the engine key in its own storage (`apps/android/app.js`, `localStorage` of the app). A thief
  with the unlocked phone AND the USB cable to the owner's running Mac could use it; without the Mac it is useless.
  Clear app data or restart the engine with a new token file to revoke.
* iPhone: the phone never holds the engine token; it pairs only with the bridge (`tools/ios/bridge.py`).

### 5. The scammer, evading detection — partial (a detection limit, not a privacy one)
A caller can use a better voice clone, avoid the scripted phrases, or speak over a bad line. Mitigations: several
independent voters, content (intent) signals that do not depend on the voice, a stabiliser that latches red
(`stabiliser.py`), red-team generation (`tools/redteam`). Tell can be wrong and says so in the UI.

### 6. The user as a covert surveillant (recording someone without consent) — partial
Tell is passive and keeps no audio or transcript by default; the listener prints a consent line and requires
`--i-understand` or an interactive yes (`listen.py`, `bridge.py`). Labelled capture (`--save-labeled`) needs four
explicit flags, a consent note and shows a SAVING AUDIO banner. We cannot stop a user from running it on a call without
telling the other side; local law may require consent, which the consent line says.

### 7. Speakerphone bystanders — partial
Android and iPhone companions listen through the microphone in speaker mode, so people in the room are heard too.
Audio is analysed in RAM and dropped; the window transcript reaches the local page only. The engine caps displayed
confidence for `side: mix`. Bystanders get no notice from Tell itself.

### 8. Supply chain — partial
Dependencies are pinned in `services/api/requirements.lock` (versions, not hashes); CI runs the test suite and the
golden eval on each PR (`.github/workflows/ci.yml`); `tests/test_import_scan.py` blocks new network or process use in the
engine package; `TELL_OFFLINE=1` keeps model libraries offline at run time. Not mitigated: a compromised pinned package
runs with the engine's rights and could read RAM or the token; there are no hash pins or signature checks yet.

## Residual risks to know before a demo
* The pairing link sits in the terminal's scrollback; close the terminal tab or run `clear` if the screen is shared.
* `TELL_COMPANION_ALLOW=1` must stay off unless a companion cannot be paired.
* The OS counter is cumulative since the engine started; restarting the engine resets it.
