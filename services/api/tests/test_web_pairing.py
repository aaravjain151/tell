"""The web page's pairing flow in a real headless Chrome (DevTools protocol, tools/web/devtools_check.py) against a real
engine process: with `#token=` in the link the Home chip says connected and the privacy rows show /health's numbers
within 2 s, the token leaves the address bar and lands in sessionStorage; without it the page shows the calm
'Pair this page' state, never ARMED. Both http://localhost and http://127.0.0.1 page origins are checked.
Skipped when Chrome is not installed (CI)."""
import asyncio
import functools
import http.server
import importlib.util
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from tests.conftest import TEST_TOKEN

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("devtools_check", ROOT / "tools" / "web" / "devtools_check.py")
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)

pytestmark = pytest.mark.skipif(dc.chrome_binary() is None, reason="Google Chrome not installed")
pytest.importorskip("websockets")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def stack():
    web_port, api_port = _free_port(), _free_port()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "apps" / "web"))
    handler.log_message = lambda *a: None
    web = http.server.ThreadingHTTPServer(("127.0.0.1", web_port), handler)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    env = dict(os.environ, TELL_WARMUP="0", TELL_OFFLINE="1", TELL_API_TOKEN=TEST_TOKEN,
               TELL_CORS_ORIGINS=f"http://localhost:{web_port},http://127.0.0.1:{web_port}")
    env.pop("TELL_COMPANION_ALLOW", None)
    eng = subprocess.Popen([sys.executable, "-m", "uvicorn", "tell.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
                           cwd=ROOT / "services" / "api", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f"http://127.0.0.1:{api_port}/health", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("engine did not start")
        yield web_port, api_port
    finally:
        eng.terminate()
        eng.wait(10)
        web.shutdown()


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_paired_page_shows_connected_chip_and_real_privacy_numbers_within_2s(stack, host):
    web_port, api_port = stack
    url = f"http://{host}:{web_port}/?api=http://127.0.0.1:{api_port}#token={TEST_TOKEN}"
    seen = asyncio.run(dc.check(url, 4.0, None, dc.chrome_binary()))
    assert seen["ok"], seen
    assert seen["elapsed_s"] <= 2.5, seen                       # 2 s budget + DevTools overhead
    assert seen["chip_state"] == "up" and "0 B out" in seen["chip"]
    assert seen["hash"] == "" and seen["token_in_session"] is True and "token" not in seen["url"]


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_unpaired_page_shows_pair_state_not_armed(stack, host):
    web_port, api_port = stack
    url = f"http://{host}:{web_port}/?api=http://127.0.0.1:{api_port}"
    seen = asyncio.run(dc.check(url, 4.0, None, dc.chrome_binary(), dc.unpaired))
    assert seen["ok"], seen
    assert seen["hero"] != "Armed" and "make pair-url" in seen["chip"]


def test_bad_token_in_link_is_dropped_and_page_asks_to_pair(stack):
    web_port, api_port = stack
    url = f"http://localhost:{web_port}/?api=http://127.0.0.1:{api_port}#token={'z' * 43}"
    seen = asyncio.run(dc.check(url, 4.0, None, dc.chrome_binary(), dc.unpaired))
    assert seen["ok"], seen
    assert seen["token_in_session"] is False                    # a stale/wrong token is cleared after the 401
