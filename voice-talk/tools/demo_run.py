"""Headless run of an attacker-demo persona against a scripted 'presenter', with the real local stack (Ollama + Qwen3-TTS).

    python tools/demo_run.py --voice demo-say --ack-test-only                     # the escalating scam test
    python tools/demo_run.py --voice demo-say --ack-test-only --score http://127.0.0.1:8000

Runs the same ConverseSession the page uses (staging, allowed-line guard, cached lines), waits for each line to finish
"playing" before the presenter answers (so the timeline is a real-time call), saves qa_out/demo_<persona>_<time>/call.wav +
label.json (with per-stage spans and per-turn first-audio latency) and, with --score, POSTs the audio of each stage (alone,
and cumulative as the call escalates) to the Doublespeak API on loopback. Local files only; nothing is played or routed.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

PRESENTER = ["Oh hi, yes, it's a good time.", "I'm doing well, thanks. Just a quiet day.", "Okay, sure, that's fine.",
             "Sure, go ahead.", "Wait, what kind of problem?", "Hmm, I did not notice anything. What do I need to do?",
             "A code? Okay, I think I got a text.", "I'm not sure about this...", "Okay, what should I do?",
             "Why can't I tell anyone?", "Okay, I'm listening."]


async def run(a, chat=None, synth=None, voices=None) -> Path | None:
    from voice_talk.config import Config
    from voice_talk.converse import ConverseConfig, ConverseSession
    from voice_talk.voices import VoiceStore

    cfg = Config()
    voices = voices or VoiceStore(cfg.voices_dir)
    if chat is None:
        from voice_talk.chat import make_chat
        chat = make_chat(a.backend, model=a.llm_model)
    if synth is None:
        from voice_talk.tts import Qwen3Synth
        cfg.tts_model = a.tts
        synth = Qwen3Synth(cfg.tts_path)
        synth.load()
    events: list[dict] = []

    async def emit(msg, binary=None):
        events.append(msg)
        if msg["type"] in ("stage", "turn", "error"):
            print("  ", json.dumps({k: v for k, v in msg.items() if k != "label"}))

    c = ConverseSession(ConverseConfig(voice=a.voice, demo=a.persona, demo_auto=not a.manual, prerecord=not a.no_prerecord,
                                       save_call=True, disclosure=False, disclosure_ack=a.ack_test_only),
                        chat, None, synth, voices, emit, qa_dir=Path(a.out))
    c.models["tts"] = f"Qwen3-TTS-12Hz-{a.tts}-Base"
    t_start = time.monotonic()
    await c.start()

    async def settle():
        for _ in range(6000):
            t = c._turn
            if t and (t.reported or t.cancelled) and c.session.inflight == 0 and not c._bg:
                break
            await asyncio.sleep(0.02)
        rec = c.recorder  # wait for the (simulated) playback to finish before the presenter answers
        await asyncio.sleep(max(0.0, rec.cursor - rec.now()) + 0.8)

    await settle()
    last = len(c.demo.persona.stages)
    extra = 0
    for i in range(a.max_turns):
        if c.demo.stage.n == last:
            extra += 1
            if extra > a.final_turns:
                break
        if a.manual and i in (a.escalate_every * k for k in range(1, last)):
            print("  [Escalate pressed]")
            await c.escalate()
            await settle()
        line = PRESENTER[i % len(PRESENTER)]
        print(f"  presenter> {line}")
        await c.say(line)
        await settle()
    await c.close()
    print(f"call took {time.monotonic() - t_start:.0f}s wall; saved {c.saved_path}")
    return c.saved_path


def score(api: str, d: Path) -> int:
    import numpy as np
    import soundfile as sf
    import qa_score

    lab = json.loads((d / "label.json").read_text())
    wav, sr = sf.read(d / "call.wav", dtype="float32")

    def post(x):
        buf = io.BytesIO()
        sf.write(buf, x, sr, format="WAV", subtype="PCM_16")
        return qa_score.post_audio(api, buf.getvalue())

    print(f"\nexpected tier for the whole call: {lab['expected_tier']}")
    print("stage | span (s)      | alone: tier (p_scam p_ai) | cumulative up to end of stage: tier (p_scam p_ai)")
    for s in lab["stages"]:
        i0, i1 = int(s["start_s"] * sr), int(s["end_s"] * sr)
        out = []
        for seg in (wav[i0:i1], wav[:i1]):
            try:
                v = post(seg)
                out.append(f"{v.get('tier')} ({v.get('p_scam', float('nan')):.2f} {v.get('p_ai', float('nan')):.2f})")
            except Exception as e:  # report honestly
                out.append(f"error: {e}")
        print(f"  {s['stage']}   | {s['start_s']:6.1f}-{s['end_s']:6.1f} | {out[0]:26} | {out[1]}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voice", default="demo-say")
    ap.add_argument("--persona", default="escalating_scam_test")
    ap.add_argument("--out", default=str(ROOT / "qa_out"))
    ap.add_argument("--backend", default="ollama", choices=["ollama", "lmstudio"])
    ap.add_argument("--llm-model", default=None)
    ap.add_argument("--tts", default="0.6B", choices=["0.6B", "1.7B"])
    ap.add_argument("--manual", action="store_true", help="no auto-advance: press Escalate every --escalate-every presenter lines")
    ap.add_argument("--escalate-every", type=int, default=3)
    ap.add_argument("--no-prerecord", action="store_true", help="do not synthesize each next stage's opening line ahead of time")
    ap.add_argument("--max-turns", type=int, default=16)
    ap.add_argument("--final-turns", type=int, default=2, help="presenter lines to keep going once the last stage is reached")
    ap.add_argument("--score", metavar="API", help="score each stage with the Doublespeak API (loopback only)")
    ap.add_argument("--ack-test-only", action="store_true",
                    help="confirm this audio is labelled detector test data (the spoken AI-voice disclosure is omitted)")
    a = ap.parse_args(argv)
    if not a.ack_test_only:
        print("refused: pass --ack-test-only (the saved call omits the spoken AI-voice disclosure).", file=sys.stderr)
        return 2
    from voice_talk.voices import ConsentError, VoiceError
    try:
        d = asyncio.run(run(a))
    except (ConsentError, VoiceError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    if d and a.score:
        return score(a.score, d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
