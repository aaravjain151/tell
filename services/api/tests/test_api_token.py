"""Per-install API token (tell/api_token.py + limits.GuardMiddleware): every data/control route needs it, /health and
/ready stay public and carry no call content, the SSE query token never reaches the access log, the token file is
0600 and reused, the comparison is constant-time. The route table is read from the app, so a NEW route is covered
(and refused without the token) automatically."""
import json
import logging
import os
import socket
import stat
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from tell import api_token, limits, net_monitor
from tell.main import app
from tests.conftest import AUTH, TEST_TOKEN

ORIGIN = "http://localhost:5173"
PUBLIC = {"/health", "/ready", "/thresholds"}


def _concrete(path: str) -> str:
    import re
    return re.sub(r"\{[^}]+\}", "x", path)


def protected_routes():
    """Every HTTP route the app serves (from its OpenAPI table, which also walks included routers), minus PUBLIC,
    plus the framework's own docs pages (deny by default covers them too)."""
    out = [("GET", p) for p in ("/docs", "/openapi.json", "/redoc")]
    for path, ops in app.openapi()["paths"].items():
        if path in PUBLIC:
            continue
        for m in ops:
            if m.upper() in ("GET", "POST", "DELETE", "PUT", "PATCH"):
                out.append((m.upper(), _concrete(path)))
    return sorted(set(out))


ROUTES = protected_routes()
bare = TestClient(app)                     # no token, no Origin: what another local process sends


def test_route_table_covers_every_data_and_control_route():
    paths = {p for _, p in ROUTES}
    for must in ("/live/events", "/live/dismiss", "/session", "/session/x", "/history", "/history/status", "/blocklist",
                 "/blocklist/x", "/blocklist/check", "/blocklist/export", "/feedback", "/personal", "/panic",
                 "/analyze", "/speak", "/redteam/samples"):
        assert must in paths, must


@pytest.mark.parametrize("method,path", ROUTES)
def test_401_without_token_on_every_protected_route(method, path):
    r = bare.request(method, path)
    assert r.status_code == 401, (method, path, r.status_code)
    assert r.headers.get("www-authenticate", "").startswith("Bearer")


@pytest.mark.parametrize("method,path", ROUTES)
def test_401_with_allowed_origin_but_no_token(method, path):
    """A forged browser Origin is not a credential: any local process can send one."""
    assert bare.request(method, path, headers={"Origin": ORIGIN}).status_code == 401


@pytest.mark.parametrize("method,path", ROUTES)
def test_401_with_wrong_token(method, path):
    assert bare.request(method, path, headers={"X-Tell-Token": TEST_TOKEN[:-1] + "!"}).status_code == 401


@pytest.mark.parametrize("path", ["/history", "/history/status", "/blocklist", "/personal", "/redteam/samples"])
def test_200_with_header_token(path):
    assert bare.get(path, headers=AUTH).status_code == 200
    assert bare.get(path, headers={"Authorization": "Bearer " + TEST_TOKEN}).status_code == 200


def test_public_routes_need_no_token():
    for p in sorted(PUBLIC):
        assert bare.get(p).status_code == 200, p


def test_panic_and_session_refused_without_token_and_do_nothing(monkeypatch):
    from tell import blocklist
    wiped = []
    monkeypatch.setattr(blocklist, "wipe", lambda: wiped.append(1))
    assert bare.post("/panic").status_code == 401 and not wiped
    assert bare.post("/session", headers={"Origin": ORIGIN}).status_code == 401
    assert bare.post("/session", headers={"Origin": ORIGIN, **AUTH}).status_code == 200


def test_query_token_only_on_live_events():
    assert bare.get("/history?token=" + TEST_TOKEN).status_code == 401
    assert bare.post("/panic?token=" + TEST_TOKEN).status_code == 401


def test_live_events_with_query_token_streams_and_strips_it():
    seen = {}

    async def spy_app(scope, receive, send):
        seen["qs"] = scope.get("query_string")
        from starlette.responses import PlainTextResponse
        await PlainTextResponse("ok")(scope, receive, send)

    guard = limits.GuardMiddleware(spy_app)
    c = TestClient(guard)
    assert c.get(f"/live/events?a=1&token={TEST_TOKEN}&b=2").status_code == 200
    assert seen["qs"] == b"a=1&b=2"                       # the token is gone from the scope uvicorn logs from
    assert c.get("/live/events?token=nope").status_code == 401


def test_401_is_readable_by_an_allowed_page_only():
    r = bare.get("/history", headers={"Origin": ORIGIN})
    assert r.status_code == 401 and r.headers.get("access-control-allow-origin") == ORIGIN
    assert "access-control-allow-origin" not in bare.get("/history").headers


def test_cors_preflight_allows_the_token_header():
    r = bare.options("/history", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET",
                                          "Access-Control-Request-Headers": "x-tell-token"})
    assert r.status_code == 200 and "x-tell-token" in r.headers.get("access-control-allow-headers", "").lower()


def test_companion_escape_is_off_by_default_and_never_helps_originless(monkeypatch):
    monkeypatch.delenv("TELL_COMPANION_ALLOW", raising=False)
    assert bare.get("/history", headers={"Origin": ORIGIN}).status_code == 401
    monkeypatch.setenv("TELL_COMPANION_ALLOW", "1")
    assert bare.get("/history", headers={"Origin": ORIGIN}).status_code == 200
    assert bare.get("/history").status_code == 401
    assert bare.get("/history", headers={"Origin": "https://evil.example"}).status_code == 403


def test_constant_time_compare_is_used(monkeypatch):
    calls = []
    real = api_token.hmac.compare_digest
    monkeypatch.setattr(api_token.hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    assert bare.get("/history", headers=AUTH).status_code == 200
    assert bare.get("/history", headers={"X-Tell-Token": "x" * 43}).status_code == 401
    assert len(calls) >= 2


# --- token file ----------------------------------------------------------------------------------------------------

@pytest.fixture
def file_mode(monkeypatch, tmp_path):
    monkeypatch.delenv("TELL_API_TOKEN", raising=False)
    p = tmp_path / "Tell" / "api_token"
    monkeypatch.setenv("TELL_API_TOKEN_FILE", str(p))
    api_token._cache.clear()
    yield p
    api_token._cache.clear()


def test_token_file_created_0600_in_0700_dir_and_reused(file_mode):
    t1 = api_token.ensure()
    assert len(t1) >= 43 and file_mode.read_text().strip() == t1
    assert stat.S_IMODE(file_mode.stat().st_mode) == 0o600
    assert stat.S_IMODE(file_mode.parent.stat().st_mode) == 0o700
    api_token._cache.clear()
    assert api_token.ensure() == t1                      # reused across restarts
    assert api_token.matches(t1) and not api_token.matches(t1[:-1]) and not api_token.matches(None)


def test_loosened_permissions_are_tightened(file_mode):
    api_token.ensure()
    os.chmod(file_mode, 0o644)
    api_token._cache.clear()
    api_token.ensure()
    assert stat.S_IMODE(file_mode.stat().st_mode) == 0o600


def test_rotated_file_is_picked_up(file_mode):
    t1 = api_token.ensure()
    file_mode.unlink()
    t2 = api_token.ensure()
    assert t2 != t1 and api_token.matches(t2) and not api_token.matches(t1)


def test_default_path_is_per_user_app_support(monkeypatch):
    monkeypatch.delenv("TELL_API_TOKEN_FILE", raising=False)
    p = api_token.token_path()
    assert p.name == "api_token" and str(p).startswith(str(os.path.expanduser("~")))
    if os.uname().sysname == "Darwin":
        assert p.parent == api_token.Path.home() / "Library" / "Application Support" / "Tell"


def test_short_env_override_is_refused(monkeypatch):
    monkeypatch.setenv("TELL_API_TOKEN", "short")
    with pytest.raises(api_token.TokenError):
        api_token.ensure()
    assert not api_token.matches("short")


def test_token_never_logged_at_startup(caplog, monkeypatch, file_mode):
    monkeypatch.setenv("TELL_WARMUP", "0")
    with caplog.at_level(logging.INFO):
        with TestClient(app):
            pass
    tok = file_mode.read_text().strip()
    assert tok not in caplog.text and "api_token" in caplog.text


# --- access log ----------------------------------------------------------------------------------------------------

def test_redact_filter_drops_token_from_uvicorn_access_records():
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("127.0.0.1:1", "GET", f"/live/events?token={TEST_TOKEN}&x=1", "1.1", 200), None)
    api_token.RedactQueryFilter().filter(rec)
    assert TEST_TOKEN not in rec.getMessage() and "/live/events?x=1" in rec.getMessage()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_real_uvicorn_sse_with_query_token_and_access_log_has_no_token(monkeypatch):
    """A real server: the browser-style SSE call works and uvicorn's access log never records the token, even with
    the logging filter removed (the middleware already stripped it from the request)."""
    uvicorn = pytest.importorskip("uvicorn")
    monkeypatch.setenv("TELL_WARMUP", "0")
    access = logging.getLogger("uvicorn.access")
    saved = list(access.filters)
    for f in saved:
        access.removeFilter(f)
    lines: list[str] = []

    class H(logging.Handler):
        def emit(self, record):
            lines.append(record.getMessage())

    h = H()
    access.addHandler(h)
    access.setLevel(logging.INFO)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, access_log=True,
                                           lifespan="on"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    try:
        deadline = time.time() + 10
        while not server.started and time.time() < deadline:
            time.sleep(0.05)
        assert server.started
        with httpx.Client(trust_env=False, timeout=5) as c:
            assert c.get(f"http://127.0.0.1:{port}/live/events").status_code == 401
            with c.stream("GET", f"http://127.0.0.1:{port}/live/events?token={TEST_TOKEN}") as r:
                assert r.status_code == 200
                first = next(r.iter_lines())
                assert first.startswith("data: ") and json.loads(first[6:])["type"] == "state"
        time.sleep(0.2)
    finally:
        server.should_exit = True
        t.join(10)
        access.removeHandler(h)
        for f in saved:
            access.addFilter(f)
    assert any("/live/events" in ln for ln in lines), lines
    assert not any(TEST_TOKEN in ln for ln in lines), lines


# --- /health and /ready: public, no call content, cumulative OS count -----------------------------------------------

def test_cumulative_os_counter_increments_on_a_fake_connection(monkeypatch):
    w = net_monitor.Cumulative(interval_s=10)
    monkeypatch.setattr(net_monitor, "outbound", lambda: [])
    w.poll()
    r0 = w.report()
    assert r0["os_outbound_count"] == 0 and r0["os_first_seen"] is None and r0["os_check"] == "ok"
    monkeypatch.setattr(net_monitor, "outbound", lambda: ["93.184.216.34:443"])
    w.poll()
    monkeypatch.setattr(net_monitor, "outbound", lambda: [])      # the connection closed: it still counts
    w.poll()
    r = w.report()
    assert r["os_outbound_count"] == 1 and r["os_remote_addresses"] == 1 and r["os_first_seen"]
    assert r["scope"] == "since_engine_start" and r["os_polls"] == 3
    assert "93.184.216.34" not in json.dumps(r)                   # counts only, never the address


def test_health_and_ready_report_counts_but_no_addresses_or_content(monkeypatch):
    monkeypatch.setattr(net_monitor.CUMULATIVE, "endpoints", {"93.184.216.34:443"})
    for path in ("/health", "/ready"):
        body = bare.get(path).text
        assert "93.184.216.34" not in body
        for word in ("transcript", "number", "token", "os_outbound_seen"):
            assert word not in body.lower(), (path, word)
    h = bare.get("/health").json()
    assert h["os_network"]["os_outbound_count"] == 1 and h["os_network"]["scope"] == "since_engine_start"
    assert h["egress"]["caller_audio_bytes_sent"] == 0
