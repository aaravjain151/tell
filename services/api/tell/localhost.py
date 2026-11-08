"""The ONLY module that opens a socket to a local engine (VoiceStudio STT, Ollama). Decision D-009.

Caller audio / transcript text may go to loopback and nowhere else. Every request is checked
(host resolved, every address must be loopback), counted as `localhost_requests`, and never
counted as external egress. Proxy settings are ignored and redirects are refused. stdlib only; `opener` is injectable so tests never touch a network.
"""
from __future__ import annotations

import ipaddress
import json
import secrets
import socket
import urllib.parse
import urllib.request
from typing import Any, Callable

from . import privacy

ALLOWED_HOSTS = ("127.0.0.1", "::1", "localhost")
Opener = Callable[..., Any]   # urlopen-compatible: opener(request, timeout=...) -> file-like with .read()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A local engine must never bounce a request (and its body) somewhere else."""

    def redirect_request(self, *args, **kwargs):
        return None


# ProxyHandler({}) ignores HTTP_PROXY / HTTPS_PROXY / ALL_PROXY from the environment, so a "loopback" call can never be
# routed through a proxy; _NoRedirect turns any 3xx into an HTTPError instead of following it.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


class NotLoopbackError(RuntimeError):
    """Raised when a local-engine URL does not point at the loopback interface."""


def _check(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or host not in ALLOWED_HOSTS:
        raise NotLoopbackError(f"refusing non-loopback host {host!r}: caller data may only reach {', '.join(ALLOWED_HOSTS)}")
    try:
        addrs = {ai[4][0].split("%")[0] for ai in socket.getaddrinfo(host, parts.port or 80, proto=socket.IPPROTO_TCP)}
    except OSError as e:
        raise NotLoopbackError(f"cannot resolve {host!r}: {e}") from e
    if not addrs or not all(ipaddress.ip_address(a).is_loopback for a in addrs):
        raise NotLoopbackError(f"{host!r} does not resolve to loopback ({sorted(addrs)})")


def _send(req: urllib.request.Request, timeout: float, opener: Opener | None) -> bytes:
    _check(req.full_url)
    privacy.record_localhost()   # attempted requests count, success or not
    with (opener or _OPENER.open)(req, timeout=timeout) as r:
        return r.read()


def post_json(url: str, body: dict, timeout: float = 10.0, opener: Opener | None = None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json"}, method="POST")
    return json.loads(_send(req, timeout, opener))


def get_json(url: str, timeout: float = 1.5, opener: Opener | None = None) -> dict:
    """Read engine status without inference or changing analysis traffic counters."""
    _check(url)
    req = urllib.request.Request(url, method="GET")
    with (opener or _OPENER.open)(req, timeout=timeout) as response:
        return json.loads(response.read())


def post_multipart(url: str, fields: dict[str, str], file_field: str, filename: str, data: bytes,
                   timeout: float = 10.0, opener: Opener | None = None, content_type: str = "audio/wav") -> dict:
    boundary = "----tell" + secrets.token_hex(12)
    out = b""
    for k, v in fields.items():
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=out, headers={"content-type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    return json.loads(_send(req, timeout, opener))
