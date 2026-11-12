"""Start voice-talk on loopback only.   python run.py [--tts 0.6B|1.7B] [--backend ollama|lmstudio] [--port 8765]"""
import argparse
import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # the app never talks to Hugging Face
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


def main() -> None:
    from voice_talk.config import Config, TTS_DIRS

    ap = argparse.ArgumentParser()
    ap.add_argument("--tts", choices=list(TTS_DIRS), default=None)
    ap.add_argument("--backend", default=None, help="lmstudio (default), ollama, llamacpp, vllm, jan, or custom (with --llm-url)")
    ap.add_argument("--llm-url", default=os.environ.get("VT_LLM_URL"), help="any OpenAI-compatible loopback endpoint, e.g. http://127.0.0.1:8080/v1")
    ap.add_argument("--llm-model", default=None, help="model id to use (default: the first chat model the server offers)")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    cfg = Config(port=a.port)
    if a.tts:
        cfg.tts_model = a.tts
    if a.backend:
        cfg.backend = a.backend
    if a.llm_model:
        cfg.llm_model = a.llm_model
    if a.llm_url:
        from voice_talk.llms import register_custom
        register_custom(a.llm_url, cfg.llm_model)
        cfg.backend = a.backend or "custom"
    from voice_talk.translate import BACKENDS
    if cfg.backend not in BACKENDS:
        ap.error(f"unknown backend {cfg.backend!r}; choose from {', '.join(BACKENDS)} (or give --llm-url)")

    import uvicorn
    from voice_talk.server import Deps, create_app
    from voice_talk.stt import FasterWhisperSTT
    from voice_talk.chat import make_chat
    from voice_talk.translate import make_translator
    from voice_talk.tts import Qwen3Synth
    from voice_talk.voices import VoiceStore

    synth = Qwen3Synth(cfg.tts_path)
    deps = Deps(voices=VoiceStore(cfg.voices_dir), synth=synth, stt=FasterWhisperSTT(cfg.models_dir),
                translator_factory=lambda b: make_translator(b or cfg.backend, model=cfg.llm_model if b == cfg.backend else None),
                chat_factory=lambda b: make_chat(b or cfg.backend, model=cfg.llm_model if b == cfg.backend else None),
                outputs_dir=cfg.outputs_dir, loader=synth.load, tts_name=f"Qwen3-TTS {cfg.tts_model}-Base",
                default_backend=cfg.backend, llm_model=cfg.llm_model)
    print(f"voice-talk on http://127.0.0.1:{cfg.port}  (TTS {cfg.tts_model}, chat + translation via {cfg.backend})")
    uvicorn.run(create_app(deps), host="127.0.0.1", port=cfg.port, log_level="warning")


if __name__ == "__main__":
    sys.exit(main())
