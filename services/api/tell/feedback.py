"""Local, encrypted user feedback ("this was a scam / not a scam / AI / human") for the learning layer.

Stores ONLY: the label, an optional small integer tick, and a coarse timestamp (UTC, truncated to the hour), plus
per-label counters. No call id, number, transcript, audio or evidence is kept (a supplied call_id is validated and
discarded). One AES-256-GCM file, key in the OS keychain (shared helpers with secure_store.py). No network code.

API for the learning code: ``recent(n)`` -> newest-first list of {label, tick, ts}; ``counters()`` -> {label: count}.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from . import blocklist, secure_store

log = logging.getLogger("tell.feedback")

FEEDBACK_FILE = "feedback.enc"
LABELS = ("scam", "not_scam", "ai", "human")
KEEP = 500
MAX_TICK = 1_000_000
_lock = threading.Lock()
router = APIRouter()


def path() -> Path:
    return secure_store.data_dir() / FEEDBACK_FILE


def _empty() -> dict:
    return {"v": 1, "counters": {k: 0 for k in LABELS}, "recent": []}


def _load() -> dict:
    p = path()
    if not p.exists():
        return _empty()
    try:
        doc = json.loads(secure_store._decrypt(secure_store.keyring_key_provider(), p.read_text(encoding="ascii")))
        if isinstance(doc.get("counters"), dict) and isinstance(doc.get("recent"), list):
            return doc
    except secure_store.HistoryUnavailable:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("feedback unreadable: %s", type(e).__name__)
    raise secure_store.HistoryUnavailable("feedback file unreadable")


def _save(doc: dict) -> None:
    line = secure_store._encrypt(secure_store.keyring_key_provider(), json.dumps(doc, sort_keys=True).encode("utf-8"))
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


def record(label: str, tick: int | None = None) -> None:
    if label not in LABELS:
        raise ValueError("bad label")
    ts = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat(timespec="hours")
    with _lock:
        doc = _load()
        doc["counters"][label] = int(doc["counters"].get(label, 0)) + 1
        doc["recent"].append({"label": label, "tick": tick, "ts": ts})
        doc["recent"] = doc["recent"][-KEEP:]
        _save(doc)


def recent(n: int = 50) -> list[dict]:
    """Newest first, at most n (capped at 500). Returns [] when storage is unavailable."""
    try:
        with _lock:
            rows = _load()["recent"]
    except secure_store.HistoryUnavailable:
        return []
    return [dict(r) for r in reversed(rows)][: max(0, min(int(n), KEEP))]


def counters() -> dict:
    try:
        with _lock:
            return dict(_load()["counters"])
    except secure_store.HistoryUnavailable:
        return {k: 0 for k in LABELS}


def wipe() -> None:
    with _lock:
        for p in (path(), path().with_suffix(".tmp")):
            try:
                p.unlink()
            except FileNotFoundError:
                pass


@router.post("/feedback")
async def post_feedback(request: Request) -> dict:
    blocklist.rate(True)
    body = await blocklist.read_json_object(request)
    label, tick, cid = body.get("label"), body.get("tick"), body.get("call_id")
    if not isinstance(label, str) or label not in LABELS:
        raise HTTPException(422, "label must be scam, not_scam, ai or human")
    if cid is not None and not (isinstance(cid, str) and re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", cid)):
        raise HTTPException(422, "call_id invalid")
    if tick is not None and not (isinstance(tick, int) and not isinstance(tick, bool) and 0 <= tick <= MAX_TICK):
        raise HTTPException(422, "tick invalid")
    try:
        record(label, tick)
    except secure_store.HistoryUnavailable:
        raise HTTPException(503, "secure storage unavailable") from None
    return {"ok": True}
