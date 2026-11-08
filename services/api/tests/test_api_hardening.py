"""API hardening: CORS/Host/Origin guards, upload and duration limits, one-at-a-time analysis, timeout, safe errors.
No network and no models: pipeline.analyze is monkeypatched."""
import asyncio
import threading

import httpx
import pytest
from fastapi.testclient import TestClient
from tests.conftest import AUTH

from tell import limits, pipeline
from tell.main import app
from tests.synth import make_call, to_wav_bytes

client = TestClient(app, headers=AUTH)


class _V:
    def to_dict(self):
        return {"tier": "unsure"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("TELL_CORS_ORIGINS", "TELL_ALLOWED_HOSTS", "TELL_MAX_UPLOAD_MB",
              "TELL_MAX_AUDIO_S", "TELL_ANALYZE_TIMEOUT_S"):
        monkeypatch.delenv(k, raising=False)


def fake_ok(monkeypatch):
    monkeypatch.setattr(pipeline, "analyze", lambda a, t: _V())


def test_cors_preflight_allowed_and_denied():
    ok = client.options("/analyze", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-credentials" not in ok.headers
    bad = client.options("/analyze", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert bad.status_code == 403 and "access-control-allow-origin" not in bad.headers


def test_evil_origin_is_rejected_and_never_runs(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "analyze", lambda a, t: calls.append(1))
    r = client.post("/analyze", data={"transcript": "hi"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and "access-control-allow-origin" not in r.headers and not calls
    assert client.get("/health", headers={"Origin": "null"}).status_code == 403


def test_null_origin_only_if_listed(monkeypatch):
    # CORSMiddleware is built at import with the env of that moment; the guard reads env per request.
    monkeypatch.setenv("TELL_CORS_ORIGINS", "http://localhost:5173,null")
    assert client.get("/health", headers={"Origin": "null"}).status_code == 200


def test_bad_host_rejected_good_hosts_ok(monkeypatch):
    assert client.get("/health", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/health", headers={"Host": "rebind.evil.example:8000"}).status_code == 400
    for h in ("localhost:8000", "127.0.0.1", "[::1]:8000"):
        assert client.get("/health", headers={"Host": h}).status_code == 200
    monkeypatch.setenv("TELL_ALLOWED_HOSTS", "mybox.local")
    assert client.get("/health", headers={"Host": "mybox.local:8000"}).status_code == 200


def _run_asgi(path, chunk):
    """Drive the app directly with an endless body; return (status, chunks_consumed)."""
    state = {"n": 0, "status": None}

    async def receive():
        state["n"] += 1
        head = b'--b\r\nContent-Disposition: form-data; name="audio"; filename="a.wav"\r\n\r\n' if state["n"] == 1 else b""
        return {"type": "http.request", "body": head + b"x" * chunk, "more_body": True}

    async def send(m):
        if m["type"] == "http.response.start":
            state["status"] = m["status"]

    scope = {"type": "http", "method": "POST", "path": path, "raw_path": path.encode(), "query_string": b"",
             "headers": [(b"host", b"localhost"), (b"content-type", b"multipart/form-data; boundary=b"),
                         (b"x-tell-token", AUTH["X-Tell-Token"].encode())],
             "scheme": "http", "server": ("localhost", 8000), "client": ("127.0.0.1", 1), "http_version": "1.1"}
    asyncio.run(app(scope, receive, send))
    return state["status"], state["n"]


def test_oversize_audio_413_before_full_read(monkeypatch):
    monkeypatch.setenv("TELL_MAX_UPLOAD_MB", "1")
    status, n = _run_asgi("/analyze", 256 * 1024)   # endless 256 KiB chunks, no Content-Length
    assert status == 413
    assert n <= 12   # limit is 1 MiB + 1 MiB slack = 8 chunks; it stopped instead of reading forever


def test_oversize_content_length_413_immediately(monkeypatch):
    monkeypatch.setenv("TELL_MAX_UPLOAD_MB", "1")
    r = client.post("/analyze", content=b"", headers={"Content-Length": str(50 * 1024 * 1024),
                                                      "Content-Type": "multipart/form-data; boundary=b"})
    assert r.status_code == 413 and "limit is 1 MB" in r.json()["detail"]


def test_long_transcript_rejected(monkeypatch):
    fake_ok(monkeypatch)
    r = client.post("/analyze", data={"transcript": "a" * 20_001})
    assert r.status_code == 413 and "20000" in r.json()["detail"]
    assert client.post("/analyze", data={"transcript": "a" * 20_000}).status_code == 200


def test_empty_input_still_400():
    assert client.post("/analyze").status_code == 400


def test_duration_cap(monkeypatch):
    fake_ok(monkeypatch)
    monkeypatch.setenv("TELL_MAX_AUDIO_S", "2")
    wav = to_wav_bytes(make_call("tts", seed=3))
    r = client.post("/analyze", files={"audio": ("c.wav", wav, "audio/wav")})
    assert r.status_code == 413 and "2 s" in r.json()["detail"]


def test_corrupt_wav_is_415_not_500(monkeypatch):
    fake_ok(monkeypatch)
    r = client.post("/analyze", files={"audio": ("c.wav", b"RIFF" + b"\x00" * 20, "audio/wav")})
    assert r.status_code == 415


def _aclient():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost", headers=AUTH)


def _slow(started, release):
    def slow(a, t):
        started.set()
        release.wait(10)
        return _V()
    return slow


def test_concurrency_503_with_retry_after(monkeypatch):
    release, started = threading.Event(), threading.Event()
    monkeypatch.setattr(pipeline, "analyze", _slow(started, release))
    monkeypatch.setattr(limits, "QUEUE_WAIT_S", 0.3)

    async def go():
        async with _aclient() as c:
            first = asyncio.create_task(c.post("/analyze", data={"transcript": "one"}))
            while not started.is_set():
                await asyncio.sleep(0.01)
            second = await c.post("/analyze", data={"transcript": "two"})
            release.set()
            return second, await first

    second, first = asyncio.run(go())
    assert second.status_code == 503 and second.headers["retry-after"] and "another analysis" in second.json()["detail"]
    assert first.status_code == 200


def test_sequential_requests_not_throttled(monkeypatch):
    fake_ok(monkeypatch)
    assert all(client.post("/analyze", data={"transcript": "hi"}).status_code == 200 for _ in range(4))


def test_health_responsive_during_slow_analysis(monkeypatch):
    release, started = threading.Event(), threading.Event()
    monkeypatch.setattr(pipeline, "analyze", _slow(started, release))

    async def go():
        async with _aclient() as c:
            job = asyncio.create_task(c.post("/analyze", data={"transcript": "x"}))
            while not started.is_set():
                await asyncio.sleep(0.01)
            h = await asyncio.wait_for(c.get("/health"), 2)
            release.set()
            return h, await job

    h, job = asyncio.run(go())
    assert h.status_code == 200 and job.status_code == 200


def test_timeout_504_and_gate_held_until_thread_ends(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(pipeline, "analyze", lambda a, t: release.wait(10))
    monkeypatch.setenv("TELL_ANALYZE_TIMEOUT_S", "0.3")
    monkeypatch.setattr(limits, "QUEUE_WAIT_S", 0.2)

    async def go():
        async with _aclient() as c:
            r = await c.post("/analyze", data={"transcript": "x"})
            r2 = await c.post("/analyze", data={"transcript": "y"})   # thread still busy
            release.set()
            await asyncio.sleep(0.2)
            return r, r2

    r, r2 = asyncio.run(go())
    assert r.status_code == 504 and "timed out" in r.json()["detail"]
    assert r2.status_code == 503


def test_unexpected_error_is_generic_500(monkeypatch, caplog):
    def boom(a, t):
        raise RuntimeError(t + " /Users/me/file.py")
    monkeypatch.setattr(pipeline, "analyze", boom)
    r = client.post("/analyze", data={"transcript": "secret transcript words"})
    assert r.status_code == 500 and r.json() == {"detail": "analysis failed"}
    assert "Traceback" not in r.text and "/Users" not in r.text
    assert "secret transcript words" not in caplog.text and "RuntimeError" in caplog.text
