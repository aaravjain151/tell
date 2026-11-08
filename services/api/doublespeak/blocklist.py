"""Local-only block list for the caller-ID side of Doublespeak.

The list is the user's own. It lives in ONE AES-256-GCM encrypted file (same key and helpers as secure_store.py, key in
the OS keychain only) and never leaves the device: no crowd upload, no cloud reputation lookup, no number is ever sent
anywhere. Phone numbers are personal data: they are never logged, never put in an egress report, a verdict, a
signature or an error message. Logs here carry counts and exception class names only.

Routes (mounted by main.py): GET/POST /blocklist, DELETE /blocklist/{id}, POST /blocklist/check, GET /blocklist/export.
No network code lives here.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from . import secure_store

log = logging.getLogger("doublespeak.blocklist")

BLOCKLIST_FILE = "blocklist.enc"
MAX_ITEMS = 5000
MAX_NUMBER_CHARS = 32
MAX_LABEL = 64
MAX_REASON = 200
MAX_BODY = 4096
WRITES_PER_MIN = 60
ANY_PER_MIN = 300
MIN_DIGITS, MAX_DIGITS = 7, 15          # E.164 allows 15 digits including the country code

# --- number normalisation ----------------------------------------------------------------------------------------
# Rules (no network, no external library; `phonenumbers` is NOT used even when installed so results are the same
# everywhere). Output is E.164 ("+14155550123") or None. It never raises.
#   1. Input must be a str of at most 32 chars containing only digits, space . - ( ) / and an optional leading "+".
#      Letters (vanity numbers, "ext"), "#", "*", and anything else are refused.
#   2. "+" or a leading "00" means an explicit country code: keep it, 7..15 digits, first digit not 0.
#   3. Otherwise the number is national and DOUBLESPEAK_DEFAULT_REGION (default "US") decides:
#        US/CA (NANP): 10 digits, or 11 digits starting with 1, area code and exchange start 2-9 -> +1...
#        GB: leading 0 trunk prefix + 10 digits -> +44...      IN: 10 digits starting 6-9, or 0 + 10 -> +91...
#        AU: leading 0 + 9 digits -> +61...
#      Other regions, or anything that does not fit the rule, return None (the API answers 422).
# It cannot: validate that a number is assigned or dialable, expand short codes (911, 5-6 digit SMS codes), handle
# extensions, vanity letters, or non-NANP numbers dialled without a country code outside the four regions above.
_ALLOWED = re.compile(r"^\+?[0-9 ().\-/]+$")


def default_region() -> str:
    return os.environ.get("DOUBLESPEAK_DEFAULT_REGION", "US").strip().upper()


def normalise(raw: Any, region: str | None = None) -> str | None:
    try:
        if not isinstance(raw, str):
            return None
        s = raw.strip()
        if not s or len(s) > MAX_NUMBER_CHARS or not _ALLOWED.match(s):
            return None
        digits = re.sub(r"\D", "", s)
        explicit = s.startswith("+")
        if not explicit and digits.startswith("00"):
            digits, explicit = digits[2:], True
        if explicit:
            return "+" + digits if MIN_DIGITS <= len(digits) <= MAX_DIGITS and digits[0] != "0" else None
        reg = (region or default_region()).upper()
        if reg in ("US", "CA"):
            if len(digits) == 11 and digits[0] == "1":
                digits = digits[1:]
            if len(digits) == 10 and digits[0] in "23456789" and digits[3] in "23456789":
                return "+1" + digits
            return None
        if reg == "GB" and len(digits) == 11 and digits[0] == "0":
            return "+44" + digits[1:]
        if reg == "IN":
            if len(digits) == 11 and digits[0] == "0":
                digits = digits[1:]
            return "+91" + digits if len(digits) == 10 and digits[0] in "6789" else None
        if reg == "AU" and len(digits) == 10 and digits[0] == "0":
            return "+61" + digits[1:]
        return None
    except Exception:  # noqa: BLE001 — junk in, None out
        return None


# --- encrypted single-document store -----------------------------------------------------------------------------
_lock = threading.Lock()


class StorageUnavailable(Exception):
    """Keychain/crypto not available or file unreadable. Message never contains user data."""


def path() -> Path:
    return secure_store.data_dir() / BLOCKLIST_FILE


def _key() -> bytes:
    try:
        return secure_store.keyring_key_provider()
    except secure_store.HistoryUnavailable as e:
        raise StorageUnavailable(str(e)) from e


def _load() -> list[dict]:
    p = path()
    if not p.exists():
        return []
    key = _key()
    try:
        doc = json.loads(secure_store._decrypt(key, p.read_text(encoding="ascii")))
        items = doc["items"]
        return items if isinstance(items, list) else []
    except secure_store.HistoryUnavailable as e:
        raise StorageUnavailable(str(e)) from e
    except Exception as e:  # noqa: BLE001 — tampered or corrupt file: say nothing about content
        log.warning("blocklist unreadable: %s", type(e).__name__)
        raise StorageUnavailable("blocklist file unreadable") from e


def _save(items: list[dict]) -> None:
    key = _key()
    line = secure_store._encrypt(key, json.dumps({"v": 1, "items": items}, sort_keys=True).encode("utf-8"))
    secure_store._ensure_dir()
    tmp = path().with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, (line + "\n").encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path())


def _clean_text(v: Any, limit: int) -> str | None:
    if v is None:
        return ""
    if not isinstance(v, str) or len(v) > limit * 4:
        return None
    t = "".join(ch for ch in v if ch.isprintable()).strip()
    return t if len(t) <= limit else None


def _public(it: dict) -> dict:
    return {k: it[k] for k in ("id", "number", "label", "reason", "added_at", "reports")}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_items() -> list[dict]:
    with _lock:
        items = _load()
    return [_public(i) for i in sorted(items, key=lambda i: i["added_at"], reverse=True)]


def add(number: str, label: str = "", reason: str = "") -> dict:
    """number must already be E.164. A repeat increments `reports` (and fills a missing label/reason)."""
    with _lock:
        items = _load()
        for it in items:
            if it["number"] == number:
                it["reports"] = min(int(it["reports"]) + 1, 1_000_000)
                it["label"] = label or it["label"]
                it["reason"] = reason or it["reason"]
                _save(items)
                return _public(it)
        if len(items) >= MAX_ITEMS:
            raise OverflowError("blocklist full")
        it = {"id": secrets.token_hex(6), "number": number, "label": label, "reason": reason,
              "added_at": _now(), "reports": 1}
        items.append(it)
        _save(items)
        return _public(it)


def remove(item_id: str) -> bool:
    with _lock:
        items = _load()
        kept = [i for i in items if i["id"] != item_id]
        if len(kept) == len(items):
            return False
        _save(kept)
        return True


def check(number: str) -> dict | None:
    with _lock:
        for it in _load():
            if it["number"] == number:
                return _public(it)
    return None


def wipe() -> int:
    with _lock:
        n = 0
        try:
            n = len(_load()) if path().exists() else 0
        except StorageUnavailable:
            pass
        for p in (path(), path().with_suffix(".tmp")):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
        return n


def export_numbers() -> list[int]:
    """Sorted ascending, de-duplicated integers of the E.164 numbers: the order CXCallDirectoryProvider requires."""
    with _lock:
        nums = {int(i["number"][1:]) for i in _load()}
    return sorted(nums)


def _csv_cell(s: str) -> str:
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def export_csv() -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["number", "label", "reason", "added_at", "reports"])
    for i in list_items():
        w.writerow([i["number"], _csv_cell(i["label"]), _csv_cell(i["reason"]), i["added_at"], i["reports"]])
    return out.getvalue()


# --- rate limit (in-process, per kind) ---------------------------------------------------------------------------
_hits: dict[str, deque] = {"any": deque(), "write": deque()}
_rl = threading.Lock()


def rate(write: bool) -> None:
    now = time.monotonic()
    with _rl:
        for kind, cap in (("any", ANY_PER_MIN), ("write", WRITES_PER_MIN)):
            if kind == "write" and not write:
                continue
            q = _hits[kind]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= cap:
                raise HTTPException(429, "too many requests", headers={"Retry-After": "30"})
            q.append(now)


def reset_rate_limits() -> None:
    with _rl:
        for q in _hits.values():
            q.clear()


# --- HTTP --------------------------------------------------------------------------------------------------------
router = APIRouter()


async def read_json_object(request: Request) -> dict:
    """Body must be a small JSON object. Errors are generic: never echo the input (it can be a phone number)."""
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "request body too large")
    try:
        obj = json.loads(raw)
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "body must be a JSON object") from None
    if not isinstance(obj, dict):
        raise HTTPException(400, "body must be a JSON object")
    return obj


def _unavailable() -> HTTPException:
    return HTTPException(503, "secure storage unavailable")


@router.get("/blocklist/export")
def export(format: str = "calldirectory") -> Response:
    rate(False)
    try:
        if format == "calldirectory":
            body = "".join(f"{n}\n" for n in export_numbers())
            mt = "text/plain; charset=utf-8"
        elif format == "csv":
            body, mt = export_csv(), "text/csv; charset=utf-8"
        else:
            raise HTTPException(400, "format must be calldirectory or csv")
    except StorageUnavailable:
        raise _unavailable() from None
    return Response(body, media_type=mt, headers={"Cache-Control": "no-store"})


@router.get("/blocklist")
def get_list() -> dict:
    rate(False)
    try:
        return {"items": list_items()}
    except StorageUnavailable:
        raise _unavailable() from None


@router.post("/blocklist")
async def post_item(request: Request) -> dict:
    rate(True)
    body = await read_json_object(request)
    num = normalise(body.get("number"))
    label, reason = _clean_text(body.get("label"), MAX_LABEL), _clean_text(body.get("reason"), MAX_REASON)
    if num is None:
        raise HTTPException(422, "number not recognised")
    if label is None or reason is None:
        raise HTTPException(422, "label or reason invalid")
    try:
        return add(num, label, reason)
    except StorageUnavailable:
        raise _unavailable() from None
    except OverflowError:
        raise HTTPException(409, "blocklist is full") from None


@router.post("/blocklist/check")
async def post_check(request: Request) -> dict:
    rate(False)
    num = normalise((await read_json_object(request)).get("number"))
    if num is None:
        raise HTTPException(422, "number not recognised")
    try:
        item = check(num)
    except StorageUnavailable:
        raise _unavailable() from None
    return {"blocked": True, "item": item} if item else {"blocked": False}


@router.delete("/blocklist/{item_id}")
def delete_item(item_id: str) -> dict:
    rate(True)
    if not re.fullmatch(r"[0-9a-f]{12}", item_id):
        raise HTTPException(404, "not found")
    try:
        if not remove(item_id):
            raise HTTPException(404, "not found")
    except StorageUnavailable:
        raise _unavailable() from None
    return {"ok": True}
