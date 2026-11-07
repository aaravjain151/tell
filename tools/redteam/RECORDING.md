# Recording the AI vs human set (T-012)

Same words, two voices: an engine clone of teammate X (`make redteam`) and teammate X reading the
identical scripts (`make record`), then opus-8k copies and a speaker→mic replay. Script tells cancel,
so the wild eval measures whether Doublespeak separates the *voice*.

~30 min per speaker. Credits: 6 clips per engine per voice.

## 0. Once
```bash
brew install ffmpeg uv
make setup
cp .env.example .env                        # GRADIUM_API_KEY, ELEVENLABS_API_KEY, *_VOICE_ID
python3 tools/redteam/capture.py devices    # mic index, e.g. [1] MacBook Pro Microphone → --device ":1"
```
Consent: only teammates who agreed, only their own voice. Clips stay in `data/calls/` (gitignored).

## 1. AI side
Clone teammate X in Gradium Studio / ElevenLabs, put the voice ids in `.env`, then:
```bash
make redteam ARGS="--engine all"            # ai__<engine>__<script>.wav + .txt
```

## 2. Human side (same teammate X)
```bash
make record ARGS="--speaker sanath"         # human__sanath__<script>.wav + .txt, plus 3 free_* takes
```
Each script shows on screen → Enter starts, Enter stops → `p` play back, `r` redo.
- Read like a phone call: normal pace and volume. Don't act out the scam.
- Keep stumbles and "um"s; real people sound like that.
- Mic ~30 cm, quiet room, same setup every take. Each take ≥ 6 s (tool warns).
- The `free_*` prompts are unscripted on purpose: read speech is more regular than conversation.

Recorded on a phone? `python3 tools/redteam/capture.py import memo.m4a --script scam_irs --speaker sanath`

## 3. Replay (what the live demo actually hears)
```bash
python3 tools/redteam/capture.py replay     # every clean clip → <stem>.replayed.wav via speakers + mic
```
Speaker ~60% volume, nobody talks while it runs.

## 4. Measure
```bash
make wild                                    # degrade.sh (opus-8k) + run_eval.py --wild: FPR@90%TPR per condition
make wild ARGS=--verbose
```
Conditions: `clean`, `opus-8k`, `replayed`. Judge generalisation on Gradium/VoiceStudio, not ElevenLabs
(in-domain for the anti-spoof model). Paste the table into the T-012 commit; threshold changes bump
`THRESHOLDS_VERSION` with before/after (services/api/skills.md).

Minimum for T-012: 2 speakers × 6 scripts, plus the matching AI clips, clean + opus-8k.
