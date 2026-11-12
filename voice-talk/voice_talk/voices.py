"""Reference-voice store with a mandatory consent record.

voices/<name>/ref.wav, ref_text.txt, meta.json, consent.json
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundfile as sf

ATTESTATION = "This is my own voice, or the speaker gave me their permission to clone it"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
MIN_SEC, MAX_SEC = 3.0, 30.0
CONSENT_KEYS = {"schema", "voice", "attestation", "speaker_name", "granted_at"}


class ConsentError(PermissionError):
    pass


class VoiceError(ValueError):
    pass


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise VoiceError("voice name must be 1-40 letters, digits, '_' or '-'")
    return name


MIN_CUSTOM_ATTESTATION = 15


def make_consent(voice: str, speaker_name: str, attested: bool, now: datetime | None = None,
                 attestation: str | None = None) -> dict:
    """schema 1 = the fixed UI tick-box text. schema 2 = free text supplied by a human (tools/import_voice.py);
    there is no default for it: it is either given explicitly or the record is refused."""
    if attested is not True:
        raise ConsentError("consent attestation is required to use a reference voice")
    if not isinstance(speaker_name, str) or not speaker_name.strip():
        raise ConsentError("the speaker's name is required")
    schema, text = 1, ATTESTATION
    if attestation is not None:
        text = attestation.strip() if isinstance(attestation, str) else ""
        if len(text) < MIN_CUSTOM_ATTESTATION or len(text.split()) < 3:
            raise ConsentError("the attestation text is missing or too short; it must state what the speaker agreed to")
        schema = 2
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    return {"schema": schema, "voice": voice, "attestation": text,
            "speaker_name": speaker_name.strip(), "granted_at": ts}


def check_consent_record(rec: object, voice: str) -> dict:
    if not isinstance(rec, dict) or set(rec) != CONSENT_KEYS:
        raise ConsentError("consent.json is malformed")
    if rec["voice"] != voice or rec["schema"] not in (1, 2):
        raise ConsentError("consent.json does not match this voice")
    if rec["schema"] == 1 and rec["attestation"] != ATTESTATION:
        raise ConsentError("consent.json does not match this voice")
    if rec["schema"] == 2 and (not isinstance(rec["attestation"], str) or len(rec["attestation"].strip()) < MIN_CUSTOM_ATTESTATION):
        raise ConsentError("consent.json has no attestation text")
    if not isinstance(rec["speaker_name"], str) or not rec["speaker_name"].strip():
        raise ConsentError("consent.json has no speaker name")
    try:
        datetime.fromisoformat(rec["granted_at"])
    except Exception:
        raise ConsentError("consent.json has an invalid timestamp") from None
    return rec


def analyze_clip(audio: np.ndarray, sr: int, ref_text: str) -> dict:
    """Return {duration, speech_ratio, errors[], warnings[]} for a reference clip."""
    errors: list[str] = []
    warnings: list[str] = []
    mono = audio if audio.ndim == 1 else audio.mean(axis=1)
    dur = len(mono) / float(sr) if sr else 0.0
    if dur < MIN_SEC:
        errors.append(f"clip is {dur:.1f}s; it must be at least {MIN_SEC:.0f}s")
    if dur > MAX_SEC:
        errors.append(f"clip is {dur:.1f}s; it must be at most {MAX_SEC:.0f}s")
    frame = max(1, int(sr * 0.03))
    n = len(mono) // frame
    ratio = 0.0
    if n:
        frames = mono[: n * frame].reshape(n, frame)
        rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
        peak = float(np.abs(mono).max())
        thr = max(0.01, 0.1 * float(np.percentile(rms, 95)))
        ratio = float((rms > thr).mean()) if peak > 0.02 else 0.0
    if ratio < 0.15:
        errors.append("no speech detected in the clip (too quiet or silent)")
    elif ratio < 0.4:
        warnings.append("the clip contains a lot of silence; trim it for better cloning")
    text = (ref_text or "").strip()
    if not text:
        errors.append("the exact words spoken in the clip (ref_text) are required")
    elif dur > 0:
        spaced = len(text.split()) >= 3 and " " in text
        if spaced:
            rate, lo, hi, unit = len(text.split()) / dur, 1.0, 4.5, "words/s"
        else:
            rate, lo, hi, unit = len(text) / dur, 2.0, 9.0, "characters/s"
        if rate < lo or rate > hi:
            warnings.append(
                f"ref_text has {rate:.1f} {unit} for a {dur:.1f}s clip (expected {lo}-{hi}); "
                "it probably does not match what is spoken, which degrades the clone"
            )
    return {"duration": round(dur, 2), "speech_ratio": round(ratio, 2), "errors": errors, "warnings": warnings}


class VoiceStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _dir(self, name: str) -> Path:
        return self.root / validate_name(name)

    def create(self, name: str, wav_bytes: bytes, ref_text: str, speaker_name: str, attested: bool,
               attestation: str | None = None) -> dict:
        """Validate and store a voice. Without a valid attestation nothing is written."""
        validate_name(name)
        consent = make_consent(name, speaker_name, attested, attestation=attestation)  # raises before touching disk
        import io
        try:
            audio, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
        except Exception as e:
            raise VoiceError(f"could not read the audio file: {e}") from None
        report = analyze_clip(audio, sr, ref_text)
        if report["errors"]:
            raise VoiceError("; ".join(report["errors"]))
        d = self._dir(name)
        if d.exists():
            raise VoiceError(f"voice {name!r} already exists; delete it first")
        d.mkdir(parents=True)
        try:
            (d / "ref.wav").write_bytes(wav_bytes)
            (d / "ref_text.txt").write_text(ref_text.strip(), encoding="utf-8")
            (d / "meta.json").write_text(json.dumps({"duration": report["duration"], "sample_rate": sr}), encoding="utf-8")
            (d / "consent.json").write_text(json.dumps(consent, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            shutil.rmtree(d, ignore_errors=True)
            raise
        return {"name": name, **report}

    def attach_consent(self, name: str, speaker_name: str, attested: bool) -> None:
        d = self._dir(name)
        if not (d / "ref.wav").exists():
            raise VoiceError("no such voice")
        (d / "consent.json").write_text(
            json.dumps(make_consent(name, speaker_name, attested), indent=2, ensure_ascii=False), encoding="utf-8")

    def consent(self, name: str) -> dict:
        p = self._dir(name) / "consent.json"
        if not p.exists():
            raise ConsentError(f"voice {name!r} has no consent record; synthesis is refused")
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            raise ConsentError("consent.json is unreadable") from None
        return check_consent_record(rec, name)

    def require_usable(self, name: str) -> tuple[Path, str]:
        """The consent gate: returns (ref wav path, ref_text) or raises ConsentError."""
        self.consent(name)
        d = self._dir(name)
        if not (d / "ref.wav").exists() or not (d / "ref_text.txt").exists():
            raise VoiceError(f"voice {name!r} is incomplete")
        return d / "ref.wav", (d / "ref_text.txt").read_text(encoding="utf-8").strip()

    def list(self) -> list[dict]:
        out = []
        if not self.root.exists():
            return out
        for d in sorted(p for p in self.root.iterdir() if p.is_dir() and NAME_RE.match(p.name)):
            try:
                c = self.consent(d.name)
                ok, who = True, c["speaker_name"]
            except (ConsentError, VoiceError):
                ok, who = False, None
            dur = None
            try:
                dur = json.loads((d / "meta.json").read_text())["duration"]
            except Exception:
                pass
            out.append({"name": d.name, "consent": ok, "speaker": who, "duration": dur})
        return out

    def delete(self, name: str) -> None:
        d = self._dir(name)
        if d.exists():
            shutil.rmtree(d)
