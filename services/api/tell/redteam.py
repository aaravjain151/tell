"""Read-only access to generated red-team clips (data/calls) so the web UI can load them as samples.

Layout: <calls>/<engine>/<script>.wav (+ <script>.txt, + <script>.opus8k.wav), humans in <calls>/human/**.wav.
Local files only; nothing here touches the network or the analysis path. Absolute paths are never returned.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from . import env as _env

ROOT = Path(__file__).resolve().parents[3]
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MAX_CLIPS = 200
router = APIRouter(prefix="/redteam", tags=["redteam"])


def calls_dir() -> Path:
    p = Path(_env.get("TELL_CALLS_DIR") or "data/calls")
    return (p if p.is_absolute() else ROOT / p).resolve()


def _inside(p: Path, base: Path) -> bool:
    try:
        return p.resolve().is_relative_to(base)
    except (OSError, RuntimeError):
        return False


def _bad(*names: str) -> bool:
    return not all(NAME_RE.match(n) for n in names) or ".." in "".join(names)


def _scan() -> dict[tuple[str, str], Path]:
    """{(engine, script): wav path} for every safe, regular clip. Human clips in subfolders get script 'speaker__name'."""
    base = calls_dir()
    out: dict[tuple[str, str], Path] = {}
    if not base.is_dir():
        return out
    for wav in sorted(base.rglob("*.wav")):
        if wav.name.endswith(".opus8k.wav") or not wav.is_file() or not _inside(wav, base):
            continue
        parts = wav.relative_to(base).with_suffix("").parts
        if len(parts) < 2 or (len(parts) > 2 and parts[0] != "human"):
            continue
        engine, script = parts[0], "__".join(parts[1:])
        if not _bad(engine, script):
            out[(engine, script)] = wav
        if len(out) >= MAX_CLIPS:
            break
    return out


def _lookup(engine: str, script: str) -> Path:
    wav = None if _bad(engine, script) else _scan().get((engine, script))
    if wav is None:
        raise HTTPException(404, "no such clip")
    return wav


def _sibling(wav: Path, suffix: str) -> Path | None:
    p = wav.with_name(wav.stem + suffix)
    return p if p.is_file() and _inside(p, calls_dir()) else None


@router.get("/samples")
def list_samples() -> list[dict]:
    rows = []
    for (engine, script), wav in _scan().items():
        rows.append({"id": f"{engine}/{script}", "engine": engine, "script": script,
                     "label": "human" if engine == "human" else "ai",
                     "has_text": _sibling(wav, ".txt") is not None,
                     "has_opus8k": _sibling(wav, ".opus8k.wav") is not None})
    return sorted(rows, key=lambda r: (r["engine"], r["script"]))[:MAX_CLIPS]


@router.get("/clip/{engine}/{script}")
def get_clip(engine: str, script: str, variant: str | None = None) -> FileResponse:
    wav = _lookup(engine, script)
    if variant == "opus8k":
        wav = _sibling(wav, ".opus8k.wav")
        if wav is None:
            raise HTTPException(404, "no such variant")
    elif variant:
        raise HTTPException(404, "no such variant")
    return FileResponse(wav, media_type="audio/wav")


@router.get("/text/{engine}/{script}")
def get_text(engine: str, script: str) -> PlainTextResponse:
    txt = _sibling(_lookup(engine, script), ".txt")
    if txt is None:
        raise HTTPException(404, "no transcript")
    return PlainTextResponse(txt.read_text(encoding="utf-8", errors="replace"))
