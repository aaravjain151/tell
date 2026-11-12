"""QA mode: the bot plays a labelled 'caller' persona against a scripted (or typed) 'recipient'; each full bot-side
conversation is saved as qa_out/<scenario>/call.wav + label.json. Local files only.

    python tools/qa_run.py --voice demo-say --ack-test-only                 # all scenarios, scripted recipient
    python tools/qa_run.py --voice demo-say --scenario scam_pattern --interactive --ack-test-only
    python tools/qa_run.py --list

Needs ollama (or LM Studio) running, and the TTS model from setup_models.py. The output is detector test data: the
spoken AI-voice disclosure is NOT prepended (it would change the label), so --ack-test-only is required, the files
are labelled test_only, and nothing here routes audio anywhere (--play uses the local speakers via afplay, at most).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from voice_talk import qa  # noqa: E402


def main(argv=None, chat=None, synth=None, voices=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voice", default="demo-say")
    ap.add_argument("--scenario", default="all")
    ap.add_argument("--out", default=str(ROOT / "qa_out"))
    ap.add_argument("--backend", default="ollama", choices=["lmstudio", "ollama", "llamacpp", "vllm", "jan"])
    ap.add_argument("--llm-model", default=None)
    ap.add_argument("--tts", default="0.6B", choices=["0.6B", "1.7B"])
    ap.add_argument("--scripted", action="store_true", help="fixed caller lines instead of the LLM (fully deterministic)")
    ap.add_argument("--interactive", action="store_true", help="type the recipient's lines yourself (empty line ends)")
    ap.add_argument("--play", action="store_true", help="also play through the local speakers (afplay)")
    ap.add_argument("--ack-test-only", action="store_true",
                    help="confirm this audio is labelled detector test data and will not be played to anyone as a real call")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    if a.list:
        for s in qa.SCENARIOS.values():
            print(f"{s.name:22} expected={s.expected_tier:15} persona={s.persona}")
        return 0
    if not a.ack_test_only:
        print("refused: pass --ack-test-only (the output omits the spoken AI-voice disclosure because it is labelled "
              "detector test data, not a call).", file=sys.stderr)
        return 2
    names = list(qa.SCENARIOS) if a.scenario == "all" else [a.scenario]
    if any(n not in qa.SCENARIOS for n in names):
        print(f"unknown scenario; choose from {list(qa.SCENARIOS)}", file=sys.stderr)
        return 2

    from voice_talk.config import Config
    from voice_talk.voices import ConsentError, VoiceError, VoiceStore
    cfg = Config()
    voices = voices or VoiceStore(cfg.voices_dir)
    try:
        ref_path, ref_text = voices.require_usable(a.voice)  # the consent gate applies here too
    except (ConsentError, VoiceError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    if chat is None:
        from voice_talk.chat import make_chat
        chat = make_chat(a.backend, model=a.llm_model)
    if synth is None:
        from voice_talk.tts import Qwen3Synth
        cfg.tts_model = a.tts
        synth = Qwen3Synth(cfg.tts_path)
        synth.load()
    synth.prepare_voice(a.voice, ref_path, ref_text)
    models = {"llm": getattr(chat, "model", "?"), "tts": f"Qwen3-TTS-12Hz-{a.tts}-Base", "backend": a.backend}

    for n in names:
        sc = qa.SCENARIOS[n]
        print(f"== {n} (expected {sc.expected_tier})")
        recipient = None
        if a.interactive:
            def recipient(i):  # noqa: F811
                t = input("recipient> ").strip()
                return t or None
        audio, sr, tr = qa.run_scenario(sc, chat, synth, a.voice, recipient=recipient, scripted=a.scripted,
                                        on_line=lambda who, t: print(f"  {who:9} {t}"))
        d = qa.save_run(Path(a.out), sc, audio, sr, tr, a.voice, models, a.scripted)
        print(f"  saved {d / 'call.wav'} ({len(audio) / sr:.1f}s)")
        if a.play:
            subprocess.run(["afplay", str(d / "call.wav")], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
