# voice-talk

A local conversational voice bot. **Converse mode (default):** you speak or type, a local chat LLM (Ollama
`qwen2.5:3b` by default, or LM Studio) answers, and the answer is spoken sentence by sentence in a cloned reference
voice (Qwen3-TTS Base). **Translate mode** is the original behaviour (text/mic -> translate -> speak), and replies in
converse mode can optionally be translated too. Everything runs on loopback (127.0.0.1) on your machine.

## Responsible use (read this)

Voice cloning can be abused. **Do not use this to imitate a person to someone who does not know it is
synthetic, to deceive anyone, or to commit fraud.** Only clone your own voice or a voice whose owner
gave you permission. There is deliberately no feature that routes audio into a phone call, a virtual
microphone, a conferencing app or any telephony path, and none will be added.

Safeguards built in:
- **Consent gate.** A voice is stored with `voices/<name>/consent.json` (attestation text, speaker name, UTC
  timestamp). Without a valid record the server refuses to synthesize (`consent_required`).
- **Disclosure on by default.** Each session opens with a short spoken line in the target language
  ("This voice is AI-generated."), and the page always shows an **AI voice** badge. It can only be turned off by ticking
  "Everyone who will hear this knows it is an AI-translated voice" (the server enforces the tick).
- **Local only.** No telemetry. Network use: loopback to Ollama/LM Studio, and `setup_models.py` (one-time Hugging
  Face download). The app runs with `HF_HUB_OFFLINE=1`, binds 127.0.0.1, rejects non-loopback Host/Origin headers, and
  refuses non-loopback LLM URLs.
- **Disk.** Only `voices/` and (opt-in "save audio") `outputs/` are written.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python setup_models.py                 # 0.6B TTS + whisper base.en (one time, uses the network)
.venv/bin/python setup_models.py --tts 1.7B --whisper small   # optional: 1.7B TTS, multilingual speech input
ollama pull qwen2.5:3b                           # chat + translation model (or load a model in LM Studio on :1234)
```
Optional: `brew install sox` silences a harmless qwen-tts warning.

## Run

```bash
.venv/bin/python run.py                 # http://127.0.0.1:8765   (--tts 1.7B, --backend lmstudio, --port N)
.venv/bin/python -m pytest              # tests: no network, no real models
.venv/bin/python bench.py               # first-audio latency and real-time factor per model
.venv/bin/python tools/make_synthetic_voice.py   # demo voice made with macOS `say` (no real person)
```
In the page (Converse is the default tab): pick a voice, a persona and the conversation language, Start session, then
type and press Enter, hold the talk button, tick Hands-free to open the mic automatically, or open the mic. The status shows IDLE / READY / LISTENING / THINKING /
SPEAKING, both sides are transcribed, and each bot turn shows its timings (speech-to-text, LLM first token, first
audio, synthesis, real-time factor). Esc or the big Stop button cancels the reply being generated and everything
queued to be spoken (barge-in); tick "Let me interrupt by speaking" (headphones!) and speaking over the bot does the
same. The last 10 turns are kept in RAM only and wiped when you end the session. Personas are plain files in
`voice_talk/personas/*.md` (first line `# Title`, the rest is the system prompt).

In Translate mode: add a voice (a 3-30 s .wav, the exact words spoken, the speaker's name, consent tick), pick languages,
Start session, then type (speak-as-I-type sends on punctuation or a ~1 s pause), hold the talk button, tick Hands-free to open the mic automatically, or open the mic.
Use headphones with the open mic.

## Reference voices from a recording

```bash
.venv/bin/python tools/import_voice.py --src rec.wav --transcript rec.txt --name NAME \
    --speaker "Full Name" --attest "what the speaker agreed to, in their own words, and when"
```
Picks the cleanest 5-15 s stretch between pauses (RMS/SNR), resamples to 24 kHz, stores it under `voices/NAME/` and writes
`consent.json` (schema 2) **only** from `--speaker`/`--attest`. Both are required and have no default; with either missing
or empty the tool refuses and writes nothing. The source recording is only read. `voices/` is gitignored: never commit
recordings of real people. The words for the chosen stretch are cut from your transcript by proportion of voiced time (there is
no forced aligner); a check against Whisper on two real clips matched, but listen to the Preview and read the printed words.

## QA mode (testing the Doublespeak detector)

```bash
.venv/bin/python tools/qa_run.py --voice demo-say --ack-test-only          # bot plays labelled callers
.venv/bin/python tools/qa_score.py qa_out/ --api http://127.0.0.1:8000     # POSTs each WAV to /analyze
```
Scenarios: `benign_receptionist` (expected `ai_undisclosed`), `disclosed_assistant` (`ai_disclosed`) and `scam_pattern`
(`scam`). Personas are in `voice_talk/personas/qa/`, marked TEST PERSONA, fictional entities and fixed placeholders only
("Example Bank", case `000-TEST`). The bot plays the caller, a scripted (or `--interactive` typed) recipient is silence in
the bot-side recording; `--scripted` uses fixed caller lines instead of the LLM. Each run is saved to
`qa_out/<scenario>/call.wav` + `label.json` (`scenario, expected_tier, persona, voice, models`, transcript). Local files
only (`--play` uses the local speakers at most); nothing is written into the detector repo. Because the label depends on
the AI voice *not* announcing itself, QA output omits the app's spoken disclosure, so `--ack-test-only` is required. The consent
gate still applies. `qa_score.py` refuses any non-loopback `--api`, ignores proxies and does not follow redirects. A
handful of clips from one synthetic voice is a sanity check, not a measurement. There is no `human` scenario: a TTS bot
cannot produce one.

## Attacker demo (live detector demo)

The bot plays a labelled TEST caller in a real-time voice conversation with the presenter (typed or mic), through the Mac's
speakers only, while the Doublespeak detector listens to the system audio and shows its verdict change as the call escalates.
There is no route into phone calls, virtual mics or conferencing; the consent gate, the AI-voice badge and the spoken
disclosure all stay (dropping the spoken disclosure still needs the "everyone who will hear this knows" tick).

Run steps:

```bash
ollama serve &                                   # chat model: ollama pull qwen2.5:3b (once)
.venv/bin/python run.py                          # http://127.0.0.1:8765
```
1. Open the page, pick a voice (the list only shows voices with a consent record; `sanath` and the synthetic `demo-say` work).
2. Tick **Demo mode** (off by default), choose the set: *Escalating scam test*, *Friendly appointment assistant (undisclosed AI)* or
   *Disclosed AI assistant*. While the scam set is selected or running the page shows a persistent red **TEST ATTACKER - fictional
   scenario** bar. For a clean detector clip untick the spoken disclosure and tick the acknowledgement; leave it on to keep it.
3. Optional: **Save this test call** (off by default) writes `qa_out/demo_<persona>_<time>/call.wav` + `label.json`
   (expected tier, per-stage time spans, per-turn first-audio latency, transcript) for Doublespeak's eval. `qa_score.py qa_out/` scores it.
4. Start session. The caller opens by itself (stage 1, friendly small talk and an innocent reason for calling: about 35 s, nothing
   suspicious). Answer by typing or with the mic. The stage shows in the UI (1 of 4) and advances by turn count (stage 1: 4 bot
   turns, stages 2 and 3: 3 each) or whenever you press **Escalate to next stage**; untick "Advance the stage by turn count" for manual
   control only. Stage 2 introduces "Example Bank" and case 000-TEST, stage 3 pressure and a code or gift cards, stage 4 secrecy and
   urgency (fixed fictional wording in `voice_talk/personas/demo/escalating_scam_test.md`; every persona file says it is a test persona).
5. Headless check of the same code: `python tools/demo_run.py --voice demo-say --ack-test-only --score http://127.0.0.1:8000`
   (scripted presenter, real Ollama + Qwen3-TTS, per-stage Doublespeak scores).

How a 3B model is kept on script: the system prompt names the stage and lists its allowed lines; every clause the model produces is
checked (`voice_talk/demo.py`): a stray name, a number not in the allowed lines, or a banned word replaces the rest of the reply with an
allowed line, and a reply lacking the stage's required wording (e.g. "code" or "gift card" in stage 3) gets an allowed line appended.
The first reply of each new stage is the stage's canned lead line (no LLM call). If the LLM fails the call carries on with allowed lines.

Speed: the chat model and TTS are warmed at session start, the opener is synthesized before the call begins, **Pre-record the next line**
(on by default in demo mode) synthesizes the next stage's lead line in the background so Escalate speaks from cache, a long first
sentence is cut at about 52 characters (with a comma) so speech starts early, and every turn reports first-audio latency.

Honest limits: the saved WAV is the bot's side only (the presenter's side is silence), laid out on the clock of the session, so
it matches what the speakers played only approximately after an interrupt. Replies that came from the model are guarded, not guaranteed:
the model can still sound off-script within the allowed words. Stage text, label and audio are fictional placeholders; a few synthetic
clips from one voice are a demo and a sanity check, not a measurement of the detector.

## How it works

`input (text | mic -> faster-whisper) -> [converse: History -> ChatLLM stream] -> Chunker -> [Translator] -> Qwen3-TTS clone -> WebSocket PCM -> WebAudio`

Converse reuses the translate pipeline: the streamed LLM tokens are cleaned (`<think>` and markdown dropped) and fed to the
same chunker, so the first sentence is synthesized while the model is still writing the rest. The chat model is warmed when
a session starts. A new user turn, Esc, or voice over the bot cancels the in-flight generation and the speech queue.

Each stage is a small class with a fake in `tests/`. The qwen-tts 0.1.1 package has no streaming audio output
(its `non_streaming_mode` flag only simulates streaming *text input*), so latency is kept low by chunking at
sentence ends and at clause ends once a clause is about 18 characters, translating chunk n+1 while chunk n is
synthesized, and playing chunks back to back. One clone prompt per voice is cached; a warm-up synthesis runs at
session start. WebSocket contract: see the docstring in `voice_talk/server.py`.

## Measured on this Mac (Apple silicon, MPS, bf16, `bench.py`, Spanish, synthetic `say` voice)

| Model | first chunk (short sentence) | real-time factor | load |
|---|---|---|---|
| Qwen3-TTS 0.6B-Base (default) | about 1.5 s | 0.73 | 4.6 s |
| Qwen3-TTS 1.7B-Base | about 1.5 s | 0.81 | 2.6 s (warm cache) |

Add translation (about 0.2-0.4 s warm with Ollama qwen2.5:3b; the first call after idle can take over 1 s while the model loads).
In converse mode on the same Mac a warm turn measured LLM first token about 20-65 ms, STT about 540 ms (whisper-small,
CPU) and first audio about 2.4-4.7 s, dominated by synthesizing the first sentence (a longer first sentence costs more).
Both are faster than real time, so playback stays ahead of synthesis; 0.6B is the default for the extra headroom.

## Local setup notes (this checkout)

- Env: uv venv at `~/.venvs/voice-talk` (`uv pip install -r requirements.txt scipy`; `scipy` is needed by `tools/import_voice.py`).
- Reference voice `sanath`: imported from `source_clips/sanath/room_booking.wav` (Sanath's own recording, copied from
  tell `data/calls/human/sanath`; whole clip, exact transcript). `source_clips/` and `voices/` are gitignored.
- Start everything (app + LM Studio gemma-4-e4b by default, opens the browser): `./app.sh`. `VT_BACKEND=ollama ./app.sh` uses Ollama. Pick the "RED TEAM (drill)" persona to have the fictional attacker open the call.

## Honest limits

- **No true audio streaming.** qwen-tts 0.1.1 returns a whole clip per call, so audio starts after the first sentence/clause
  has been synthesized, not after the first token. A short first sentence starts sooner.
- **STT is English-only unless the small model is installed.** `setup_models.py` fetches `whisper base.en`; other languages
  need `--whisper small` (multilingual, slower). Chat and TTS support the languages listed in the page.
- A 3B chat model is chatty-but-shallow and can drift from a persona; the QA scam persona in particular is sometimes
  watered down (use `--scripted` for deterministic QA audio).
- The echo handling is simple: the open mic is muted while the bot talks unless you opt in to voice barge-in (use headphones).
- Not verified here: a real microphone in a browser (the mic path was exercised with a recorded clip over the WebSocket).

## Record a voice on the fly

In the page, open **Add a voice**, press **Record**, read the shown sentence aloud (10 to 25 s, auto-stops at 28 s), press **Stop**.
The clip is sent only to this machine (`POST /api/voices/transcribe`, local faster-whisper) and a draft transcript fills the form.
Fix any wrong words (Whisper writes digits like "3.30" where you said "three thirty"; use the spoken words), enter the speaker's
name and tick the consent box: the normal consent-gated enrolment still applies, nothing is stored until you press Add voice.
Then pick the voice and any persona (including "RED TEAM (drill)" or Demo mode) as before.

## Any local model server

The chat (and translation) model is any OpenAI-compatible server on loopback. The page lists the ones it finds
(LM Studio :1234, Ollama :11434, llama.cpp :8080, vLLM :8000, Jan :1337, plus a custom URL) with the models each offers; pick a
server and a model, or leave the model on "auto" for the first chat model. Embedding models are hidden.

- Machine-local defaults go in `.env.local` (gitignored, read by `app.sh`): `VT_BACKEND`, `VT_LLM_MODEL`, `VT_LLM_URL`.
- Any other endpoint: `./app.sh --llm-url http://127.0.0.1:8080/v1 --llm-model my-model` (loopback only; remote URLs are refused).
- A server that is down, or a model it does not have, is reported when you press Start, with the models that are available.
