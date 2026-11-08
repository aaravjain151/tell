"""Runtime proof of the privacy claim: while the whole pipeline (and the HTTP API) runs, no Python-level
socket operation targets a non-loopback destination. The guard patches connect / connect_ex / sendto /
create_connection / getaddrinfo / gethostbyname so any non-loopback destination is RECORDED and RAISES.

Limits (by design, see services/api/skills.md): native libraries that open their own sockets in C and
subprocess children bypass Python's socket module; those are covered only by the OS-level connection monitor.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import types
import urllib.request

import pytest
from fastapi.testclient import TestClient

from tell import localhost, pipeline, privacy
from tests.synth import make_call, to_wav_bytes

TRANSCRIPT = ("Hello, this is the IRS. You owe back taxes and a warrant will be issued today. "
              "Pay now with gift cards and do not tell anyone, it is urgent.")


class NetworkGuardViolation(OSError):
    pass


def _host_is_loopback(host) -> bool:
    if host is None or host == "":
        return True   # getaddrinfo(None, port) means loopback/wildcard, no remote lookup
    if isinstance(host, bytes):
        host = host.decode(errors="replace")
    h = str(host).split("%")[0].strip("[]").lower()
    if h == "localhost":
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False   # any other hostname would need a DNS lookup: not loopback


class Guard:
    def __init__(self):
        self.attempts: list[tuple[str, object]] = []   # non-loopback, refused
        self.allowed: list[tuple[str, object]] = []    # loopback, passed through

    def check(self, op: str, host, family=None):
        if family == getattr(socket, "AF_UNIX", object()):
            self.allowed.append((op, host))
            return
        if _host_is_loopback(host):
            self.allowed.append((op, host))
            return
        self.attempts.append((op, host))
        raise NetworkGuardViolation(f"non-loopback network attempt blocked: {op} {host!r}")

    def assert_clean(self):
        assert self.attempts == [], f"non-loopback network attempts: {self.attempts}"


def _addr_host(address):
    return address[0] if isinstance(address, (tuple, list)) and address else address


@pytest.fixture
def guard(monkeypatch):
    g = Guard()
    real_getaddrinfo = socket.getaddrinfo
    real_gethostbyname = socket.gethostbyname

    for op in ("connect", "connect_ex"):
        orig = getattr(socket.socket, op)

        def patched(self, address, *a, _op=op, _orig=orig, **k):
            g.check(_op, _addr_host(address), self.family)
            return _orig(self, address, *a, **k)
        monkeypatch.setattr(socket.socket, op, patched)

    orig_sendto = socket.socket.sendto

    def sendto(self, data, *args):
        g.check("sendto", _addr_host(args[-1]), self.family)
        return orig_sendto(self, data, *args)
    monkeypatch.setattr(socket.socket, "sendto", sendto)

    orig_cc = socket.create_connection

    def create_connection(address, *a, **k):
        g.check("create_connection", _addr_host(address))
        return orig_cc(address, *a, **k)
    monkeypatch.setattr(socket, "create_connection", create_connection)

    def getaddrinfo(host, *a, **k):
        g.check("getaddrinfo", host)
        return real_getaddrinfo(host, *a, **k)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    def gethostbyname(host):
        g.check("gethostbyname", host)
        return real_gethostbyname(host)
    monkeypatch.setattr(socket, "gethostbyname", gethostbyname)
    real_ex = socket.gethostbyname_ex

    def gethostbyname_ex(host):
        g.check("gethostbyname_ex", host)
        return real_ex(host)
    monkeypatch.setattr(socket, "gethostbyname_ex", gethostbyname_ex)

    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("TELL_OFFLINE", "1")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("TELL_WARMUP", "0")
    return g


class FakeResp:
    def __init__(self, payload): self._b = json.dumps(payload).encode()
    def read(self): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False


class LocalEngines:
    """Fake VoiceStudio + Ollama: answers by URL, never touches a network."""
    def __init__(self): self.urls = []

    def __call__(self, req, timeout=None):
        self.urls.append(req.full_url)
        if req.full_url.endswith("/v1/audio/transcriptions"):
            return FakeResp({"text": TRANSCRIPT})
        if req.full_url.endswith("/api/generate"):
            return FakeResp({"response": json.dumps({"assistant_style": 0.7, "assistant_style_reason": "scripted",
                                                     "scam_framing": 0.9, "scam_framing_reason": "gift cards", "disclosed_ai": False}),
                             "prompt_eval_count": 5, "eval_count": 5})
        raise AssertionError(f"unexpected local URL {req.full_url}")


@pytest.fixture
def engines(monkeypatch):
    e = LocalEngines()
    monkeypatch.setattr(localhost, "_OPENER", types.SimpleNamespace(open=e))
    return e


def wav(kind="tts", seed=3):
    return to_wav_bytes(make_call(kind, seed=seed))


# ---------------- positive control: the guard really works ----------------
def test_guard_records_and_raises_on_non_loopback_connect(guard):
    with pytest.raises(NetworkGuardViolation):
        socket.create_connection(("93.184.216.34", 80))
    assert guard.attempts == [("create_connection", "93.184.216.34")]


@pytest.mark.parametrize("call", [
    lambda: socket.socket().connect(("93.184.216.34", 80)),
    lambda: socket.socket().connect_ex(("93.184.216.34", 80)),
    lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("93.184.216.34", 53)),
    lambda: socket.getaddrinfo("example.com", 80),
    lambda: socket.gethostbyname("example.com"),
    lambda: socket.gethostbyname_ex("example.com"),
    lambda: urllib.request.urlopen("http://example.com", timeout=1),
])
def test_guard_blocks_every_entry_point(guard, call):
    with pytest.raises(OSError):
        call()
    assert guard.attempts, "guard did not record the attempt"


def test_guard_allows_loopback(guard):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        c = socket.create_connection(srv.getsockname(), timeout=2)
        c.close()
        socket.getaddrinfo("localhost", 80)
    finally:
        srv.close()
    guard.assert_clean()
    assert ("create_connection", "127.0.0.1") in guard.allowed


def test_assert_clean_fails_after_an_attempt(guard):
    with pytest.raises(NetworkGuardViolation):
        socket.gethostbyname("example.com")
    with pytest.raises(AssertionError):
        guard.assert_clean()


# ---------------- mutation: a leaky voter must be caught ----------------
def test_leaky_voter_in_pipeline_is_caught(guard, engines, monkeypatch):
    def leaky(x, seconds):
        try:
            urllib.request.urlopen("http://example.com", data=b"audio", timeout=1)
        except OSError:
            pass   # a voter that swallows the error must still be caught by the record
        return []
    monkeypatch.setattr(pipeline.neural, "analyze", leaky)
    pipeline.analyze(wav(), TRANSCRIPT)
    assert any(host == "example.com" for _, host in guard.attempts)
    with pytest.raises(AssertionError):
        guard.assert_clean()


def test_leaky_llm_stage_is_caught(guard, monkeypatch):
    def leak(transcript):
        socket.create_connection(("93.184.216.34", 443))
    monkeypatch.setattr(pipeline.llm, "interpret", leak)
    with pytest.raises(NetworkGuardViolation):
        pipeline.analyze(None, TRANSCRIPT)
    assert guard.attempts


# ---------------- the real pipeline stays on loopback ----------------
def test_full_pipeline_makes_no_non_loopback_attempt(guard, engines, monkeypatch):
    monkeypatch.setenv("TELL_STT", "voicestudio")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    privacy.reset()
    v = pipeline.analyze(wav("tts", 3), None)    # no transcript: STT (VoiceStudio) then Ollama, both fake over loopback
    assert v.egress["context"]["transcript_source"] == "local_voicestudio"
    assert len(engines.urls) == 2                # one STT call, one Ollama call
    guard.assert_clean()
    assert any(op == "getaddrinfo" for op, _ in guard.allowed), "guard saw no loopback resolution: is it wired up?"
    e = v.egress
    assert e["external_requests"] == 0 and e["bytes_sent_external"] == 0 and e["caller_audio_bytes_sent"] == 0
    assert e["localhost_requests"] == 2


@pytest.mark.parametrize("kind,seed", [("human", 5), ("tts", 9)])
def test_stub_pipeline_with_transcript(guard, kind, seed, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    pipeline.analyze(wav(kind, seed), TRANSCRIPT)
    pipeline.analyze(None, TRANSCRIPT)
    guard.assert_clean()


def test_pipeline_whisper_mode_makes_no_attempt(guard, monkeypatch):
    monkeypatch.setenv("TELL_STT", "whisper")
    pipeline.analyze(wav(), None)
    guard.assert_clean()


def test_non_loopback_ollama_url_is_refused_before_any_socket(guard, engines, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://example.com:11434")
    pipeline.analyze(None, TRANSCRIPT)
    assert engines.urls == []
    guard.assert_clean()   # localhost._check refuses by host name, so not even a lookup is attempted


# ---------------- the API ----------------
@pytest.fixture
def client(guard, engines, monkeypatch, tmp_path):
    monkeypatch.setenv("TELL_STT", "voicestudio")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("TELL_CALLS_DIR", str(tmp_path / "calls"))
    from tell.main import app
    with TestClient(app) as c:
        yield c


def test_api_endpoints_stay_on_loopback(client, guard):
    assert client.get("/health").status_code == 200
    assert client.get("/thresholds").status_code == 200
    assert client.get("/redteam/samples").status_code == 200
    r = client.post("/analyze", files={"audio": ("c.wav", wav(), "audio/wav")}, data={"transcript": TRANSCRIPT})
    assert r.status_code == 200
    r = client.post("/analyze", files={"audio": ("c.wav", wav(), "audio/wav")})   # STT path through fake VoiceStudio
    assert r.status_code == 200 and r.json()["egress"]["context"]["transcript_source"] == "local_voicestudio"
    r = client.post("/analyze", data={"transcript": TRANSCRIPT})
    assert r.status_code == 200
    guard.assert_clean()


def test_api_startup_warmup_stays_on_loopback(guard, engines, monkeypatch, tmp_path):
    monkeypatch.setenv("TELL_WARMUP", "1")
    monkeypatch.setenv("TELL_STT", "voicestudio")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    from tell.main import app
    with TestClient(app) as c:
        c.get("/health")
    guard.assert_clean()
    assert engines.urls, "warm-up should have exercised the fake local engines"


def test_api_history_endpoint_if_present(client, guard):
    paths = {getattr(r, "path", "") for r in client.app.routes}
    if "/history" not in paths:
        pytest.skip("no /history endpoint in this build")
    assert client.get("/history").status_code == 200
    guard.assert_clean()
