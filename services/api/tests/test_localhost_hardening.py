"""localhost.py must not be steerable off-machine by environment proxies or redirects (Codex review, D-009).

Real servers, but loopback only: nothing here touches an external network.
"""
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from doublespeak import localhost


def serve(handler_cls):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def recorder(status=200, body=b'{"ok": true}', location=None):
    hits = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("content-length") or 0)
            hits.append((self.path, self.rfile.read(n)))
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    return H, hits


def test_environment_proxies_are_ignored(monkeypatch):
    """HTTP_PROXY pointing at another listener must never receive the request."""
    eng_h, eng_hits = recorder()
    prox_h, prox_hits = recorder()
    eng, eng_port = serve(eng_h)
    prox, prox_port = serve(prox_h)
    try:
        for var in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
            monkeypatch.setenv(var, f"http://127.0.0.1:{prox_port}")
        monkeypatch.delenv("NO_PROXY", raising=False)
        monkeypatch.delenv("no_proxy", raising=False)
        assert localhost.post_json(f"http://127.0.0.1:{eng_port}/x", {"a": 1}) == {"ok": True}
        assert len(eng_hits) == 1 and prox_hits == []
    finally:
        eng.shutdown()
        prox.shutdown()


def test_redirects_are_refused_and_never_followed():
    """A 3xx from a loopback engine must not trigger a second request (and must not replay the body)."""
    target_h, target_hits = recorder()
    target, target_port = serve(target_h)
    try:
        for status in (301, 302, 303, 307, 308):
            src_h, src_hits = recorder(status=status, location=f"http://127.0.0.1:{target_port}/elsewhere")
            src, src_port = serve(src_h)
            try:
                with pytest.raises(urllib.error.HTTPError):
                    localhost.post_json(f"http://127.0.0.1:{src_port}/x", {"secret": "caller audio"})
                assert len(src_hits) == 1
            finally:
                src.shutdown()
        assert target_hits == []
    finally:
        target.shutdown()


def test_default_opener_has_no_handler_that_uses_proxies():
    """build_opener drops a ProxyHandler({}) (nothing to handle), so no handler may carry a proxy map."""
    ph = [h for h in localhost._OPENER.handlers if isinstance(h, localhost.urllib.request.ProxyHandler)]
    assert all(h.proxies == {} for h in ph)


def test_multipart_boundary_uses_the_product_name(monkeypatch):
    seen = {}

    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"text": "hi"}'

    def opener(req, timeout=None):
        seen["ct"] = req.headers.get("Content-type")
        return R()
    localhost.post_multipart("http://127.0.0.1:3900/v1/audio/transcriptions", {"model": "m"}, "file", "a.wav", b"x", opener=opener)
    assert "----doublespeak" in seen["ct"] and "tell" not in seen["ct"]
