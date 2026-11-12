"""Measure first-audio latency and real-time factor of the Qwen3-TTS Base models on this machine.
    python bench.py [--tts 0.6B 1.7B] [--voice demo-say] [--lang es]
Writes bench_results.json (gitignored). Local files only."""
import argparse
import json
import os
import statistics
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

from voice_talk.config import Config, TTS_DIRS  # noqa: E402
from voice_talk.languages import lang_name  # noqa: E402
from voice_talk.tts import Qwen3Synth  # noqa: E402
from voice_talk.voices import VoiceStore  # noqa: E402

SENT = {
    "es": ["Hola, ¿cómo estás hoy?", "Ayer fuimos al mercado y compramos pan fresco y manzanas.",
           "Me gustaría reservar una mesa para cuatro personas esta noche, por favor."],
    "fr": ["Bonjour, comment allez-vous aujourd'hui ?", "Hier, nous sommes allés au marché acheter du pain frais."],
    "de": ["Guten Tag, wie geht es Ihnen heute?", "Gestern sind wir auf den Markt gegangen und haben frisches Brot gekauft."],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tts", nargs="+", default=["0.6B", "1.7B"], choices=list(TTS_DIRS))
    ap.add_argument("--voice", default="demo-say")
    ap.add_argument("--lang", default="es", choices=list(SENT))
    a = ap.parse_args()
    cfg = Config()
    ref, ref_text = VoiceStore(cfg.voices_dir).require_usable(a.voice)  # consent gate applies here too
    results = {}
    for size in a.tts:
        path = cfg.models_dir / TTS_DIRS[size]
        if not path.exists():
            print(f"[bench] skip {size}: {path} missing (python setup_models.py --tts {size})")
            continue
        s = Qwen3Synth(path)
        t = time.perf_counter(); s.load(); load_s = time.perf_counter() - t
        t = time.perf_counter(); s.prepare_voice(a.voice, ref, ref_text); prompt_s = time.perf_counter() - t
        s.synthesize("Warm up.", lang_name(a.lang), a.voice)
        rows = []
        for text in SENT[a.lang] * 2:
            t = time.perf_counter()
            audio, sr = s.synthesize(text, lang_name(a.lang), a.voice)
            el = time.perf_counter() - t
            dur = len(audio) / sr
            rows.append({"text": text, "latency_s": round(el, 2), "audio_s": round(dur, 2), "rtf": round(el / dur, 2)})
            print(f"[bench] {size} {el:5.2f}s for {dur:5.2f}s audio  rtf={el/dur:.2f}  {text[:40]}")
        short = [r for r in rows if len(r["text"]) < 45]
        results[size] = {"device": s.device, "load_s": round(load_s, 1), "clone_prompt_s": round(prompt_s, 2),
                         "first_chunk_latency_s_median": round(statistics.median(r["latency_s"] for r in short), 2),
                         "rtf_median": round(statistics.median(r["rtf"] for r in rows), 2), "rows": rows}
        del s
    Path("bench_results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps({k: {x: y for x, y in v.items() if x != "rows"} for k, v in results.items()}, indent=2))


if __name__ == "__main__":
    main()
