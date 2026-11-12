"""FastAPI app: static page, voice manager API, and the /ws conversation socket.

WebSocket contract (client -> server, JSON unless noted):
  {type:"start", voice, source, target, backend?, disclosure:true, disclosure_ack:false, save_audio:false}
     mode:"translate" (default, the original behaviour) or mode:"converse" with
     {lang, translate_to?, persona?} (source/target are then ignored)
  {type:"say", text}             converse: one complete user turn (typed). Cancels a turn still in flight.
  {type:"interrupt"}             converse: barge-in (same as stop)
  {type:"escalate"}              attacker demo: go to the next stage (the presenter's control)
     converse start may carry demo, demo_auto, prerecord, save_call (attacker demo; see voice_talk/demo.py)
  {type:"text", text}            feed typed text (chunked on sentence/clause ends)
  {type:"flush"}                 force out the pending text (pause / speak-as-I-type)
  {type:"mic_start", mode:"ptt"|"open"}, <binary: 16 kHz mono int16 LE>, {type:"mic_end"}
  {type:"stop"}                  cancel all queued and running speech
server -> client:
  {type:"state", state:"loading|ready|speaking"}, {type:"started"}, {type:"source"|"translation"|"disclosure", seq, text}
  {type:"audio", seq, sample_rate, samples, format:"pcm_s16le", disclosure}  then <binary PCM frame>
  {type:"chunk_done", seq, metrics:{translate_ms, synth_ms, audio_s, rtf, first_audio_ms}}
  converse: {type:"user", turn, text, stt_ms}, {type:"bot_delta", turn, text}, {type:"bot_done", turn},
            {type:"interrupted", turn, reason}, {type:"turn", turn, stt_ms, llm_first_token_ms, tts_first_audio_ms,
            synth_ms, audio_s, rtf}
  demo:     {type:"stage", stage, of, name, reason, label, test_attacker, final, pending}, {type:"saved", path}
            ({type:"started"} carries demo + test_attacker + label; the "turn" event adds stage, source, cache_hits)
  {type:"stopped"}, {type:"error", code, message, seq?}
"""
from __future__ import annotations

import asyncio
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from . import __version__
from .languages import LANGUAGES
from .llms import discover, list_models
from .demo import ATTACKER_LABEL, list_demo
from .converse import ConverseConfig, ConverseSession
from .personas import DEFAULT as DEFAULT_PERSONA, PersonaError, list_personas
from .pipeline import DisclosureError, Session, SessionConfig
from .translate import BACKENDS, RemoteEndpointError
from .voices import MAX_SEC, ConsentError, VoiceError, VoiceStore

STATIC = Path(__file__).resolve().parent.parent / "static"
QA_DIR = Path(__file__).resolve().parent.parent / "qa_out"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}


@dataclass
class Deps:
    voices: VoiceStore
    synth: object
    stt: object | None
    translator_factory: Callable[[str], object]
    outputs_dir: Path
    loader: Callable[[], None] | None = None  # loads the TTS model (called in a thread)
    tts_name: str = ""
    default_backend: str = "ollama"  # what the page preselects (run.py: --backend / VT_BACKEND)
    llm_model: str | None = None  # model name shown for the default backend (VT_LLM_MODEL)
    chat_factory: Callable[[str], object] | None = None  # backend -> ChatLLM (converse mode)
    llm_lister: Callable | None = None  # (base_url) -> model ids; tests inject a fake (default: llms.list_models)
    qa_dir: Path | None = None  # where 'Save this test call' writes (default: <repo>/qa_out)
    demo_dir: Path | None = None  # attacker-demo personas (default: voice_talk/personas/demo)


def _local_origin(origin: str | None) -> bool:
    if not origin:
        return True  # non-browser clients
    return urlparse(origin).hostname in {"127.0.0.1", "localhost", "::1"}


def create_app(deps: Deps) -> FastAPI:
    app = FastAPI(title="voice-talk", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.deps = deps
    app.state.model_state = "ready" if deps.loader is None else "loading"
    app.state.model_error = None

    @app.middleware("http")
    async def host_guard(request: Request, call_next):  # block DNS-rebinding style access
        host = (request.headers.get("host") or "").rsplit(":", 1)[0]
        if host not in LOCAL_HOSTS:
            return JSONResponse({"detail": "loopback only"}, status_code=403)
        if request.method != "GET" and not _local_origin(request.headers.get("origin")):
            return JSONResponse({"detail": "cross-origin request refused"}, status_code=403)
        return await call_next(request)

    @app.on_event("startup")
    async def _load():
        if deps.loader is None:
            return

        async def go():
            try:
                await asyncio.to_thread(deps.loader)
                app.state.model_state = "ready"
            except Exception as e:  # missing model files etc.
                app.state.model_state, app.state.model_error = "error", str(e)
        app.state.load_task = asyncio.create_task(go())

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/config")
    async def config():
        return {"version": __version__, "languages": {k: v["name"] for k, v in LANGUAGES.items()},
                "backends": list(BACKENDS), "tts_model": deps.tts_name,
                "default_backend": deps.default_backend, "llm_model": deps.llm_model,
                "model_state": app.state.model_state, "model_error": app.state.model_error,
                "consent_text": __import__("voice_talk.voices", fromlist=["x"]).ATTESTATION}

    @app.get("/api/llm")
    async def llm_servers():
        """Local OpenAI-compatible servers (LM Studio, Ollama, ...) with reachability and the models each offers."""
        servers = await asyncio.to_thread(discover, None, deps.llm_lister or list_models)
        return {"default_backend": deps.default_backend, "default_model": deps.llm_model, "servers": servers}

    @app.get("/api/personas")
    async def personas():
        return {"default": DEFAULT_PERSONA, "personas": list_personas()}

    @app.get("/api/demo")
    async def demo_personas():
        return {"attacker_label": ATTACKER_LABEL, "personas": list_demo(deps.demo_dir)}

    @app.get("/api/voices")
    async def list_voices():
        return deps.voices.list()

    @app.post("/api/voices")
    async def create_voice(name: str = Form(...), ref_text: str = Form(...), speaker_name: str = Form(""),
                           consent: bool = Form(False), audio: UploadFile = File(...)):
        try:
            data = await audio.read()
            if len(data) > 20 * 1024 * 1024:
                raise VoiceError("file too large")
            return deps.voices.create(name, data, ref_text, speaker_name, consent)
        except ConsentError as e:
            raise HTTPException(403, str(e))
        except VoiceError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/voices/transcribe")
    async def transcribe_clip(lang: str = Form("en"), audio: UploadFile = File(...)):
        """Draft transcript for a clip recorded in the page (local faster-whisper). Writes nothing and grants nothing:
        the user edits the text, then enrols the voice through POST /api/voices, which still enforces consent."""
        if deps.stt is None:
            raise HTTPException(503, "speech input is not available on this server")
        data = await audio.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "file too large")
        try:
            x, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
        except Exception:
            raise HTTPException(400, "could not read the audio; send a .wav recording")
        x = x.mean(axis=1)
        dur = len(x) / sr
        if dur > MAX_SEC:
            raise HTTPException(400, f"clip is {dur:.1f}s; it must be at most {MAX_SEC:.0f}s")
        if sr != 16000:  # linear resample is plenty for speech recognition
            x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * 16000 / sr)), np.arange(len(x)), x)
        try:
            text = await asyncio.to_thread(deps.stt.transcribe, x.astype(np.float32), lang)
        except Exception as e:
            raise HTTPException(500, f"transcription failed: {e}")
        return {"text": text.strip(), "duration_s": round(dur, 1)}

    @app.post("/api/voices/{name}/consent")
    async def add_consent(name: str, speaker_name: str = Form(""), consent: bool = Form(False)):
        try:
            deps.voices.attach_consent(name, speaker_name, consent)
        except ConsentError as e:
            raise HTTPException(403, str(e))
        except VoiceError as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.get("/api/voices/{name}/audio")
    async def voice_audio(name: str):
        try:
            p = deps.voices.root / VoiceStore(deps.voices.root)._dir(name).name / "ref.wav"
        except VoiceError:
            raise HTTPException(400, "bad name")
        if not p.exists():
            raise HTTPException(404)
        return FileResponse(p, media_type="audio/wav")

    @app.delete("/api/voices/{name}")
    async def delete_voice(name: str):
        try:
            deps.voices.delete(name)
        except VoiceError as e:
            raise HTTPException(400, str(e))
        if hasattr(deps.synth, "forget_voice"):
            deps.synth.forget_voice(name)
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        if not _local_origin(sock.headers.get("origin")) or (sock.headers.get("host") or "").rsplit(":", 1)[0] not in LOCAL_HOSTS:
            await sock.close(code=1008)
            return
        await sock.accept()
        send_lock = asyncio.Lock()

        async def emit(msg: dict, binary: bytes | None = None):
            async with send_lock:
                await sock.send_text(json.dumps(msg, ensure_ascii=False))
                if binary is not None:
                    await sock.send_bytes(binary)

        async def err(code: str, message: str):
            await emit({"type": "error", "code": code, "message": message})

        session: Session | None = None
        await emit({"type": "state", "state": app.state.model_state})
        try:
            while True:
                m = await sock.receive()
                if m["type"] == "websocket.disconnect":
                    break
                if m.get("bytes") is not None:
                    if session:
                        await session.feed_audio(m["bytes"])
                    continue
                try:
                    msg = json.loads(m.get("text") or "")
                    kind = msg["type"]
                except Exception:
                    await err("bad_message", "expected a JSON object with a 'type'")
                    continue
                if kind == "start":
                    if app.state.model_state != "ready":
                        await err("model_not_ready", app.state.model_error or "the speech model is still loading")
                        continue
                    if session:
                        await session.close()
                        session = None
                    try:
                        if msg.get("mode") == "converse":
                            if deps.chat_factory is None:
                                raise ValueError("conversation mode is not configured on this server")
                            ccfg = ConverseConfig(
                                voice=str(msg.get("voice", "")), lang=msg.get("lang", "en"),
                                translate_to=msg.get("translate_to") or None,
                                persona=msg.get("persona") or DEFAULT_PERSONA,
                                disclosure=bool(msg.get("disclosure", True)),
                                disclosure_ack=bool(msg.get("disclosure_ack", False)),
                                save_audio=bool(msg.get("save_audio", False)),
                                demo=(str(msg["demo"]) if msg.get("demo") else None),
                                demo_auto=bool(msg.get("demo_auto", True)), prerecord=bool(msg.get("prerecord", False)),
                                save_call=bool(msg.get("save_call", False)))
                            backend = msg.get("backend") or "ollama"
                            tr = deps.translator_factory(backend) if ccfg.translate_to else None
                            chat = deps.chat_factory(backend)
                            picked = msg.get("model")
                            if isinstance(picked, str) and picked.strip() and hasattr(chat, "model"):
                                chat.model = picked.strip()[:200]
                            probe = getattr(chat, "check", None)
                            if probe:
                                try:
                                    await asyncio.to_thread(probe)
                                except Exception as e:
                                    await err("llm_unavailable", f"The {backend} model server is not reachable ({e}). "
                                                                 f"Start it, or pick the other server in the dropdown.")
                                    continue
                            if tr is not None and hasattr(tr, "model") and not tr.model:
                                tr.model = getattr(chat, "model", None)  # same server: translate with the chosen model
                            c = ConverseSession(ccfg, chat, tr, deps.synth, deps.voices, emit,
                                                stt=deps.stt, outputs_dir=deps.outputs_dir if ccfg.save_audio else None,
                                                qa_dir=deps.qa_dir or QA_DIR, demo_dir=deps.demo_dir)
                            await c.start()
                            session = c
                            continue
                        cfg = SessionConfig(
                            voice=str(msg.get("voice", "")), source=msg.get("source", "en"), target=msg.get("target", "es"),
                            disclosure=bool(msg.get("disclosure", True)), disclosure_ack=bool(msg.get("disclosure_ack", False)),
                            save_audio=bool(msg.get("save_audio", False)))
                        tr = deps.translator_factory(msg.get("backend") or "ollama")
                        s = Session(cfg, tr, deps.synth, deps.voices, emit, stt=deps.stt,
                                    outputs_dir=deps.outputs_dir if cfg.save_audio else None)
                        await s.start()
                        session = s
                    except ConsentError as e:
                        await err("consent_required", f"Synthesis refused: {e}")
                    except DisclosureError as e:
                        await err("disclosure_required", str(e))
                    except (VoiceError, PersonaError, ValueError, KeyError, RemoteEndpointError) as e:
                        await err("bad_request", str(e))
                    except Exception as e:
                        await err("start_failed", str(e))
                    continue
                if session is None:
                    await err("no_session", "send 'start' first")
                    continue
                converse = isinstance(session, ConverseSession)
                if kind == "say":
                    if not converse:
                        await err("bad_message", "'say' needs a conversation-mode session")
                    else:
                        await session.say(str(msg.get("text", ""))[:2000])
                elif kind == "escalate":
                    if converse:
                        await session.escalate()
                    else:
                        await err("bad_message", "'escalate' needs an attacker-demo session")
                elif kind == "interrupt":
                    await session.stop()
                elif kind == "text" and converse:
                    await session.say(str(msg.get("text", ""))[:2000])
                elif kind == "flush" and converse:
                    pass
                elif kind == "text":
                    session.feed_text(str(msg.get("text", "")))
                elif kind == "flush":
                    session.flush()
                elif kind == "stop":
                    await session.stop()
                elif kind == "mic_start":
                    session.mic_start("ptt" if msg.get("mode") == "ptt" else "open")
                elif kind == "mic_end":
                    await session.mic_end()
                else:
                    await err("bad_message", f"unknown type {kind!r}")
        except WebSocketDisconnect:
            pass
        finally:
            if session:
                await session.close()

    return app
