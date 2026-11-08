"""Per-install API token for the loopback API (docs/THREAT-MODEL.md, "other local process").

Loopback is not a security boundary: any process on the Mac (another user account, malware, a package's postinstall
script) can connect to 127.0.0.1:8000. Without a secret it could read the live transcript feed, the decrypted history
and block list, or wipe them. So every data or control route requires a 256-bit token that only the user's own
account can read:

  * created on first engine start: 32 random bytes, urlsafe base64, in a 0600 file inside a 0700 directory
    (macOS: ~/Library/Application Support/Tell/api_token; elsewhere $XDG_CONFIG_HOME/tell/api_token);
  * TELL_API_TOKEN overrides it (tests, CI); TELL_API_TOKEN_FILE moves the file;
  * presented as `Authorization: Bearer <token>` or `X-Tell-Token: <token>`; only GET /live/events also accepts
    `?token=` because a browser EventSource cannot set headers. limits.GuardMiddleware strips that parameter from
    the request before anything (uvicorn's access log included) can record it, and `RedactQueryFilter` is a second
    line of defence on the access logger;
  * compared with hmac.compare_digest (constant time).

The token is never logged. `pair_url()` builds the one-time pairing link for the web page; the token travels in the
URL *fragment*, which browsers never send to any server.
"""
from __future__ import annotations

import base64
import hmac
import logging
import os
import secrets
import sys
import threading
from pathlib import Path

from . import env as _env

HEADER = "x-tell-token"
QUERY_PARAM = "token"
MIN_LEN = 32            # an override shorter than this is refused (a typo must not become a weak secret)

_lock = threading.Lock()
_cache: dict[str, tuple[int, str]] = {}    # path -> (mtime_ns, token): re-read only when the file changes


class TokenError(RuntimeError):
    """The token file cannot be created or read (permissions, read-only home)."""


def token_path() -> Path:
    """Where the token lives. TELL_API_TOKEN_FILE wins; then the per-user app-support directory."""
    override = _env.get("TELL_API_TOKEN_FILE")
    if override:
        return Path(override).expanduser()
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Tell" / "api_token"
    base = os.environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    return Path(base) / "tell" / "api_token"


def _env_token() -> str | None:
    v = _env.get("TELL_API_TOKEN")
    if v is None or not v.strip():
        return None
    v = v.strip()
    if len(v) < MIN_LEN:
        raise TokenError(f"TELL_API_TOKEN is too short (need >= {MIN_LEN} characters)")
    return v


def _new_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")


def _read(path: Path) -> str | None:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    if st.st_mode & 0o077:                          # someone loosened it: tighten instead of trusting a shared file
        os.chmod(path, 0o600)
    tok = path.read_text(encoding="ascii").strip()
    return tok if len(tok) >= MIN_LEN else None


def _create(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tok = _new_token()
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, (tok + "\n").encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.link(tmp, path)                          # atomic and never overwrites a token another process just wrote
    except FileExistsError:
        pass
    finally:
        tmp.unlink(missing_ok=True)
    got = _read(path)
    if got is None:
        raise TokenError(f"could not create the API token at {path}")
    return got


def ensure() -> str:
    """The token in force: TELL_API_TOKEN, else the file (created on first use, reused afterwards)."""
    env_tok = _env_token()
    if env_tok is not None:
        return env_tok
    path = token_path()
    key = str(path)
    with _lock:
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            mtime = None
        hit = _cache.get(key)
        if hit is not None and mtime is not None and hit[0] == mtime:
            return hit[1]
        try:
            tok = _read(path)
            if tok is None:
                if path.exists():                   # empty or truncated file: replace it
                    path.unlink()
                tok = _create(path)
        except OSError as e:
            raise TokenError(f"cannot read or create the API token at {path}: {type(e).__name__}") from None
        _cache[key] = (path.stat().st_mtime_ns, tok)
        return tok


def matches(presented: str | None) -> bool:
    """Constant-time comparison against the token in force. Any failure to load the token refuses."""
    if not presented or not isinstance(presented, str):
        return False
    try:
        expected = ensure()
    except TokenError:
        return False
    return hmac.compare_digest(presented.strip().encode("utf-8", "replace"), expected.encode("ascii"))


def from_headers(headers: dict[str, str]) -> str | None:
    """`Authorization: Bearer <t>` or `X-Tell-Token: <t>` (lower-cased header names)."""
    auth = headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip() or None
    return headers.get(HEADER) or None


def _unquote(v: bytes) -> str:
    """Percent-decoding for one query value (this package imports no urllib; tests/test_import_scan.py)."""
    v = v.replace(b"+", b" ")
    out, i = bytearray(), 0
    while i < len(v):
        hexpair = v[i + 1:i + 3]
        if v[i] == 0x25 and len(hexpair) == 2 and all(c in b"0123456789abcdefABCDEF" for c in hexpair):
            out.append(int(v[i + 1:i + 3], 16))
            i += 3
        else:
            out.append(v[i])
            i += 1
    return out.decode("utf-8", "replace")


def split_query(query: bytes) -> tuple[str | None, bytes]:
    """(token from ?token=, the query string without it). Keeps every other parameter byte for byte."""
    token, kept = None, []
    for part in query.split(b"&") if query else []:
        name, _, value = part.partition(b"=")
        if name == QUERY_PARAM.encode():
            token = _unquote(value)
        elif part:
            kept.append(part)
    return token, b"&".join(kept)


def pair_url(page: str = "http://localhost:5173/") -> str:
    return page + "#token=" + ensure()


class RedactQueryFilter(logging.Filter):
    """uvicorn.access records are ("client", "METHOD", "path?query", "HTTP/x", status): drop any `token=` value.
    The middleware already removed it from the request; this guards against a future route reading it."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str) and "token=" in args[2]:
            path, _, query = args[2].partition("?")
            kept = [p for p in query.split("&") if p and not p.startswith("token=")]
            record.args = (*args[:2], path + ("?" + "&".join(kept) if kept else ""), *args[3:])
        if isinstance(record.msg, str) and "token=" in record.msg:
            import re
            record.msg = re.sub(r"token=[^&\s\"]*", "token=[redacted]", record.msg)
        return True


def install_log_filter() -> None:
    lg = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactQueryFilter) for f in lg.filters):
        lg.addFilter(RedactQueryFilter())


def main(argv: list[str] | None = None) -> int:
    """`python -m tell.api_token [--path|--pair-url PAGE]` (used by `make pair-url`). Prints, never logs."""
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv[:1] == ["--path"]:
            print(token_path())
        elif argv[:1] == ["--pair-url"]:
            print(pair_url(argv[1] if len(argv) > 1 else "http://localhost:5173/"))
        else:
            ensure()
            print(f"API token ready at {token_path()} (0600). Print the pairing link with: make pair-url")
    except TokenError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
