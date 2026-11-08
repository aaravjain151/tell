# Rehearsal: three rounds before Sunday 11:00

Run all three rounds on the demo Mac, in a room as close to the venue as you can get, with the projector or an external screen. Run `python3 scripts/demo_preflight.py` before each round. Reset between runs with the commands at the end of `FALLBACKS.md`.

## Round 1: technical truth (Saturday night, about 45 min, no clock)

Goal: find out what the screen **actually** shows on the attacker and the human call, and write the branch lines down. Don't polish the words yet.

| Run | What | Record |
|---|---|---|
| 1a | Attacker, voice **sanath**, spoken disclosure **on**, typed replies, Escalate at the script's marks. Tick **Save this test call**. | The cell and tier at each stage, the time from stage 3 start to red, any amber, and whether the voice row ever says AI. The saved `qa_out/demo_*/call.wav` path becomes `$CALL` in `FALLBACKS.md`. |
| 1b | Same with voice **demo-say**. | Same. Pick the stage voice for the story (Sanath, if he agrees), not for the "best" cell. Pick it once and keep it. |
| 1c | Same as 1a with the spoken disclosure **off** (acknowledgement ticked). | Did the voice row change? Decide disclosure on or off, and keep the matching branch line in `DEMO-SCRIPT.md`. |
| 1d | Mic input instead of typing in voice-talk, with the room speakers on. | Does the room echo cut the bot off (barge-in)? If it does even once, stay with typing. |
| 1e | Sanath calls Aarav's iPhone, answered on the Mac (terminal A in `--watch`). He reads his demo 2 lines. | Time from Answer to `=== LISTENING`, time to the first verdict, the cell shown. Do the same once more with the Android phone (plan B), if it is set up. |
| 1f | Every fallback in `FALLBACKS.md` once: `afplay "$CALL"` with terminal B listening, `--file "$CALL"`, the human replay (`long_checkin.wav`), More > Grandparent scam. | Each one works: yes or no. Fix what doesn't. |

Exit criteria: the branch lines in `DEMO-SCRIPT.md` match what you saw, `$CALL` points at a fresh recording, every fallback has worked once, and the stage voice and disclosure setting are decided.

## Round 2: the clock (Sunday 08:30, about 40 min, three timed run-throughs)

Goal: land the 4:00 with the real demos. Full script, every word, stopwatch running.

- **Time:** each segment against the timing table. Write the actual times in the form. Checkpoints: end of demo 1 at **1:48**, end of demo 2 at **2:30**, end of how it works at **3:24**, finish at **4:00**.
- **Wi-Fi gate (run it twice):** turn Wi-Fi off, wait 20 s, turn it on, and have Sanath call at once. Measure from Wi-Fi on to the Mac showing the Answer banner. If both tries are under 20 s, use Wi-Fi off in demo 1. Otherwise leave it on until segment 5.
- **Cut list:** if a run ends past 4:10, apply cuts from the top of the cut list until the next run lands between 3:50 and 4:00.
- **Handovers:** Samarth starts terminal B before Aarav finishes "On the right is Tell". Sanath dials on "Sanath, call me", not before.

## Round 3: dress rehearsal (Sunday 10:00, one run, as if judges were there)

Goal: one clean run with no stops, recorded as the backup video (`FALLBACKS.md` step V). Everyone stands where they will stand. Run the preflight first. Nobody pauses to fix anything. If something fails, use the fallback, the same way you would on stage. Then do 5 minutes of Q&A drill: one person fires 5 random questions from `QA-PREP.md`, and each answer has to finish within 20 s.

## Who watches what

| Person | During the run, watch | Flag afterwards |
|---|---|---|
| Aarav (presenting) | The stopwatch on the lectern, and the card only when it is his turn to read it. | Lines that felt long, and anything on screen he could not read from where he stands. |
| Samarth (operating) | Terminal output (`=== LISTENING`, `hearing SILENCE`, `call detected`), the voice-talk stage counter, the cue marks. | Late cues, typing errors, and any terminal state that was unexpected. |
| Sanath (caller) | The Mac banner after he dials, the page during his own call. | How long it took to connect, and whether his words were picked up (transcript line). |
| Observer (a friend, or whoever is not speaking in that round) | The room view: can you read the card, hear the bot, see the TEST ATTACKER bar? | Every banned word (see below), every claim stronger than the docs, and the moments the room would be lost. |

## Feedback form (copy for each run)

```text
Run: ___  Round: ___  Date/time: ________  Stage voice: sanath / demo-say  Disclosure: on / off  Wi-Fi off in demo 1: yes / no

Segment times (actual)     target   actual
  1 Hook                   0:20     ____
  2 Problem                0:38     ____
  3 Demo 1 end             1:48     ____
  4 Demo 2 end             2:30     ____
  5 Privacy end            2:48     ____
  6 How it works end       3:24     ____
  7 Measured end           3:42     ____
  8 Roadmap end            3:55     ____
  9 Close                  4:00     ____

Demo 1: warming ended at ____  amber at ____ (or none)  red at ____ (or none)
        2x2 cell at red: [AI+scam] [human+scam] [not sure+scam] [other: ____]
        bot latency > 4 s? yes / no   off-script line? yes / no
Demo 2: Answer -> LISTENING ____ s   first verdict ____ s   cell: [human+no scam] [not sure] [other: ____]
Privacy: numbers shown: caller audio ___ external ___ OS outbound ___ os_check ___
Fallbacks used: ______________________

Banned words heard (circle): only  first  safe  legal  fully shipped  better than  percent/accuracy  never leaves the phone  Mac today
Claims stronger than the docs: ______________________
Lines that dragged: ______________________
One change for the next run: ______________________
```

## The "perfect run": acceptance criteria

The run counts as perfect only if all of these are true:

1. Total time is between 3:50 and 4:00, and every checkpoint is within ±5 s.
2. Preflight was green (0 red) within the 15 minutes before the run.
3. Demo 1: the TEST ATTACKER bar was visible the whole time, the card went from warming to a calm state to amber or red while the bot was still talking, and Aarav read the branch line that matched the screen.
4. Demo 2: listening started with no click in Tell (terminal A armed by itself on pickup), and Aarav read the cell that was actually shown.
5. The privacy numbers on screen were caller audio 0, external 0, OS outbound 0, os_check ok, and Aarav said them correctly.
6. Each of the three people said their own "how it works" piece, and nobody claimed someone else's work.
7. There were zero banned words and zero claims beyond `docs/` and `pm/AUDITS.md`.
8. Nobody clicked **Speak verdict** or **Start listening now**, and nobody refreshed to hunt for a red cell.
9. If a fallback was used, it was named out loud ("recorded", "replay", "stored sample") and the run stayed on time.
10. The run was recorded, and the recording was saved as `~/Desktop/tell-demo.mov`.
