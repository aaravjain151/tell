"""Tell API — runs on localhost only. Caller audio is analyzed in memory and never stored or forwarded."""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from . import api_token, blocklist, env as _env, feedback, limits, net_monitor, offline_guard, pipeline, privacy, readiness, secure_store, speak, thresholds, uploads
from .audio import AudioDecodeError
from .redteam import router as redteam_router
from .live import router as live_router
from .personal import router as personal_router
from .stream import router as stream_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
api_token.install_log_filter()     # second line of defence: no ?token= value in uvicorn's access log (see api_token.py)
uploads.keep_uploads_in_memory()   # caller audio never touches disk, even for large uploads
app = FastAPI(title="Tell", version="0.1.0")
limits.install(app)  # CORS allow-list, Host/Origin guard, body limit (see limits.py)
app.include_router(redteam_router)
app.include_router(stream_router)
app.include_router(live_router)
app.include_router(personal_router)
app.include_router(blocklist.router)
app.include_router(feedback.router)


@app.on_event("startup")
def security_start() -> None:
    """Create (or reuse) the per-install API token and start the engine-lifetime OS network watcher.
    Logs the token's PATH, never its value."""
    lg = logging.getLogger("tell.main")
    try:
        api_token.ensure()
        lg.info("API token: %s (0600). Pair the web page with: make pair-url",
                "from TELL_API_TOKEN" if _env.get("TELL_API_TOKEN") else api_token.token_path())
    except api_token.TokenError as e:
        lg.error("API token unavailable, every protected route will answer 401: %s", e)
    if limits.companion_allow():
        lg.warning("TELL_COMPANION_ALLOW=1: requests with an allowed Origin skip the API token. Turn it off after use.")
    net_monitor.CUMULATIVE.start()


@app.on_event("startup")
def warm_up() -> None:
    """Load whisper, the anti-spoof model and the Ollama model once, so the first real call isn't 8 s. TELL_WARMUP=0 disables."""
    if _env.get("TELL_WARMUP", "1") == "0":
        return
    import time

    import numpy as np

    from . import llm
    from .signals import neural
    t0 = time.time()
    try:
        x = (np.random.default_rng(0).standard_normal(16_000 * 4) * 0.01).astype(np.float32)
        from . import stt
        stt.transcribe(x)
        neural.analyze(x, 4.0)
        llm.interpret("hello, this is a warm up")
        logging.getLogger("tell.main").info("warm-up done in %.1fs", time.time() - t0)
    except Exception as e:  # noqa: BLE001 — never block startup
        logging.getLogger("tell.main").warning("warm-up skipped: %s", e)


@app.get("/health")
def health() -> dict:
    """Public (no API token): counters and switches only, never call content, numbers or remote addresses.
    `egress.caller_audio_bytes_sent` is 0 by construction (privacy.record_egress refuses audio); `os_network` is the
    OS's own count of engine connections to non-loopback addresses SINCE ENGINE START (net_monitor.Cumulative)."""
    return {"ok": True, "thresholds_version": thresholds.THRESHOLDS_VERSION, "egress": privacy.report(),
            "os_network": net_monitor.cumulative_report(), "offline_models": offline_guard.is_enforced(),
            "llm_provider": os.environ.get("LLM_PROVIDER", "stub")}


@app.get("/ready")
def ready() -> dict:
    return readiness.report()


@app.get("/thresholds")
def get_thresholds() -> dict:
    return {k: v for k, v in vars(thresholds).items() if k.isupper()}


@app.post("/analyze")
async def analyze(audio: UploadFile | None = File(default=None), transcript: str | None = Form(default=None)) -> dict:
    data = await audio.read() if audio is not None else None
    if not data and not (transcript and transcript.strip()):
        raise HTTPException(400, "send audio and/or transcript")
    try:
        v = await limits.run_analysis(pipeline.analyze, data, transcript)
    except AudioDecodeError as e:
        raise HTTPException(415, str(e)) from e
    return v.to_dict()


@app.post("/speak")
async def speak_verdict(headline: str = Form(...), evidence: str = Form(default="")) -> Response:
    """Spoken verdict via Gradium TTS. Only the verdict *text* leaves the device, never audio."""
    try:
        wav = speak.verdict_wav(headline, evidence)
    except speak.SpeakUnavailable as e:
        raise HTTPException(503, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return Response(content=wav, media_type="audio/wav")


@app.get("/history/status")
def history_status() -> dict:
    return secure_store.status()


@app.get("/history")
def history_get() -> dict:
    """Decrypted opt-in alert history, newest first (cap 200). No audio, transcript or evidence is ever stored."""
    if not secure_store.enabled():
        return {"records": [], "skipped": 0, "status": "disabled"}
    try:
        records, skipped = secure_store.read_all()
    except secure_store.HistoryUnavailable as e:
        return {"records": [], "skipped": 0, "status": f"unavailable: {e}"}
    return {"records": records, "skipped": skipped, "status": "ok"}


@app.delete("/history")
def history_wipe() -> dict:
    return {"deleted": secure_store.wipe()}
