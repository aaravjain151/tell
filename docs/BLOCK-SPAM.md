# Block and spam (local only)

A personal block list for the caller-ID side of Tell. The list is the user's own, stored encrypted on the device, and never leaves it.

## What it is, and how it differs from crowd-sourced caller ID

Apps like Hiya or Truecaller identify unknown numbers because millions of users upload their contacts and call logs to a shared reputation database. Tell deliberately has none of that: no crowd upload, no cloud reputation lookup, no number sent anywhere (D-004, D-009).

Consequences, stated plainly:

- It blocks numbers the user already decided to block (typed in, or marked after a call). It does not know that a never-seen number is a spam caller. There is no "Suspected spam" label for unknown numbers.
- What Tell adds that a crowd database cannot: it listens to what the caller says and sounds like (on-device verdict: human, AI, scam), and a one-tap "block this number" follows from that verdict. The decision stays local.
- A repeat block of the same number only raises a local `reports` counter. Nobody else sees it.

## Data and privacy

| Item | Where | Notes |
|---|---|---|
| Block list | `<data dir>/blocklist.enc` | one AES-256-GCM document, written atomically, mode 0600; key in the OS keychain only (same key and helpers as `secure_store.py`; no file fallback) |
| Feedback | `<data dir>/feedback.enc` | label, per-label counters, optional integer tick, timestamp truncated to the hour. No call id, number, transcript or audio |

- Numbers are never logged (logs carry counts and exception class names only), never in `/health`, egress reports, verdicts or signatures, and never in an error message (the API answers with fixed strings and does not echo input).
- If the keychain is unavailable the routes answer `503 secure storage unavailable`; there is no plaintext fallback. A file that cannot be decrypted is never overwritten.
- `POST /panic` wipes both files together with the live sessions. This deletes the user's block list; export it first if you want a copy (`GET /blocklist/export?format=csv`). The keychain key is left alone.
- Loopback client, allowed Host and Origin only, like every other route. Bodies over 8 KiB get 413, writes are rate limited (60/min, 300/min in total, then 429), at most 5000 entries, label 64 and reason 200 characters, control characters stripped.

## API (contract used by the web page and apps)

```
GET    /blocklist                      -> {items:[{id,number,label,reason,added_at,reports}]}   newest first
POST   /blocklist {number,label?,reason?} -> item        same normalised number again: reports += 1, no duplicate
DELETE /blocklist/{id}                 -> {ok:true}      404 if unknown
POST   /blocklist/check {number}       -> {blocked:bool,item?}
GET    /blocklist/export?format=calldirectory|csv
POST   /feedback {call_id?,label:'scam'|'not_scam'|'ai'|'human',tick?} -> {ok:true}
```

`format=calldirectory` returns text/plain: one integer per line (the E.164 number without the plus), de-duplicated and ascending, which is the order `CXCallDirectoryExtensionContext.addBlockingEntry` requires. `format=csv` has a header row and neutralises spreadsheet formulas in label/reason.

Python API for the learning code: `feedback.recent(n)` (newest first, `[]` when storage is unavailable) and `feedback.counters()`.

### Number normalisation (`blocklist.normalise`)

No network, no library (`phonenumbers` is not used even if installed, so results are identical on every machine). Result is E.164 or `None`; it never raises. Input must be a string of at most 32 characters made of digits, space, `. - ( ) /` and an optional leading `+`.

- `+` or `00` prefix: explicit country code, 7 to 15 digits, first digit not 0.
- Otherwise national format, using `DOUBLESPEAK_DEFAULT_REGION` (default `US`): US/CA 10 digits or 1 plus 10 (area code and exchange start 2 to 9); GB `0` plus 10 digits; IN 10 digits starting 6 to 9 (optional leading 0); AU `0` plus 9 digits.

It cannot: check that a number exists or is dialable, handle short codes (911, SMS codes), extensions, vanity letters (`1-800-FLOWERS`), or national-format numbers from any other region. Those get `422 number not recognised` and the user must type the `+country` form.

## iOS: Call Directory extension

The iOS app (PR for `feat/block-spam-ios`) adds a Call Directory extension (`CXCallDirectoryProvider`) that adds the list as blocking entries, and a "Blocked numbers" section in the app to add and remove numbers.

What a Call Directory extension can do: block incoming calls and SMS/FaceTime audio from specific numbers, silently (the caller gets a busy or voicemail path), and label numbers. The list is held by iOS itself, so blocking works with the app closed and the Mac off.

What it cannot do:

- It cannot see an incoming number at call time or decide per call; iOS loads the whole list in advance. It never runs during a call.
- No wildcard or prefix rules, no "block unknown callers" (use Settings > Phone > Silence Unknown Callers for that).
- Entries must be added in ascending order, and the app must call `reloadExtension` after every change; the user must enable it once in Settings > Phone > Call Blocking & Identification.
- Large lists are slow to reload. The extension has a small memory budget.
- Sharing the list: the app and the extension must share it. Tried on the owner's free Personal Team: an App Group entitlement is rejected at signing (profile mismatch). Keychain Sharing signs, so the default build mirrors only the sorted numbers into a shared keychain item that the extension reads; the App Group path is kept for a paid team. Built and unit-tested, but not run on a real phone. Details in `docs/ios/IOS.md` (iOS PR).

## Android plan

`apps/android/native/scaffold/callscreening/` holds a `CallScreeningService` that silences or rejects incoming calls whose number is in a local file, plus the manifest snippet and the role request. It is a scaffold: not wired into the Gradle build, not built, not installed.

Plan:
1. The app downloads `GET /blocklist/export?format=calldirectory` over the existing loopback tunnel (`adb reverse`) and writes `blocklist_numbers.txt` into its private files dir, adding the `+`.
2. The user grants the call-screening role once (`RoleManager.ROLE_CALL_SCREENING`, Android 10+).
3. `onScreenCall` checks the number against the file. Default is silence plus keep in the call log; flip `REJECT` to reject outright.
4. Limits: hidden numbers have no handle and are never blocked; Android requires the role to be held by exactly one screening app (it replaces another caller-ID app); the file is plain text in app-private storage (not the keychain-backed encrypted store), so Keystore-backed encryption of that file is the next step before shipping.

## Mac

The Mac route cannot know the caller's number. With Continuity the number is shown only in the FaceTime or notification UI and is not exposed to the audio tap. So the Mac UI can offer only "block a number I type" and "block the last call", and the latter only works if the user has typed or pasted the number for that call. Nothing here reads the Mac's call log.

## Not verified

Only the backend is covered by automated tests. Call Directory enablement on a real iPhone, App Group behaviour with a free Personal Team on the owner's device, and the Android scaffold (never compiled) are unverified.
