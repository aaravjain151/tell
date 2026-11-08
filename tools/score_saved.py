#!/usr/bin/env python3
"""Score WAVs saved by `listen.py --save-labeled DIR` against the LOCAL API and compare label vs verdict.

    python3 tools/score_saved.py DIR [--url http://127.0.0.1:8000]

Posts each DIR/<label>/*.wav to <url>/analyze (loopback only; any other host is refused) and prints label vs p_ai,
p_scam, tier and quadrant, then a summary per label. A handful of clips is a SANITY CHECK, not an evaluation: do not
quote an accuracy from it. Nothing is written or sent anywhere else.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlparse

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
LABELS = ("human", "ai", "scam_human", "scam_ai")
CAVEAT = "Caveat: a few clips is a sanity check, not an evaluation. Do not read an accuracy figure into it."


def is_loopback_url(url: str) -> bool:
    try:
        u = urlparse(url)
    except ValueError:
        return False
    return u.scheme in ("http", "https") and (u.hostname or "") in LOOPBACK


def find_clips(root: Path) -> list[tuple[str, Path]]:
    return [(lab, w) for lab in LABELS if (root / lab).is_dir() for w in sorted((root / lab).glob("*.wav"))]


def post_wav(base: str, path: Path, opener=None) -> dict:
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))   # loopback must never use a proxy
    b = uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="audio"; filename="{path.name}"\r\n'
            f"Content-Type: audio/wav\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(base.rstrip("/") + "/analyze", data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    with opener.open(req, timeout=300) as r:
        return json.loads(r.read())


def row(label: str, name: str, v: dict) -> dict:
    q = v.get("quadrant") or {}
    return {"label": label, "file": name, "p_ai": v.get("p_ai"), "p_scam": v.get("p_scam"), "tier": v.get("tier"),
            "quadrant": q.get("combo_label") or q.get("combo")}


def summary(rows: list[dict]) -> list[str]:
    out = [f"{'label':<11}{'clips':>6}{'mean p_ai':>11}{'mean p_scam':>13}  tiers"]
    for lab in LABELS:
        rs = [r for r in rows if r["label"] == lab]
        if not rs:
            continue
        tiers: dict[str, int] = {}
        for r in rs:
            tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1
        out.append(f"{lab:<11}{len(rs):>6}{sum(r['p_ai'] for r in rs) / len(rs):>11.2f}"
                   f"{sum(r['p_scam'] for r in rs) / len(rs):>13.2f}  " + ", ".join(f"{k}={n}" for k, n in sorted(tiers.items())))
    return out


def main(argv: list[str] | None = None, poster=post_wav) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dir")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    a = ap.parse_args(argv)
    if not is_loopback_url(a.url):
        print("refusing: --url must be loopback (127.0.0.1, localhost, ::1). Saved audio never leaves this machine.", file=sys.stderr)
        return 2
    root = Path(a.dir).expanduser()
    clips = find_clips(root)
    if not clips:
        print(f"no WAVs under {root}/<{'|'.join(LABELS)}>/", file=sys.stderr)
        return 2
    rows = []
    for lab, w in clips:
        try:
            v = poster(a.url, w)
        except Exception as e:  # noqa: BLE001
            print(f"{lab:<11}{w.name:<24} FAILED: {e}")
            continue
        r = row(lab, w.name, v)
        rows.append(r)
        print(f"{lab:<11}{w.name:<24} p_ai={r['p_ai']:<6} p_scam={r['p_scam']:<6} tier={r['tier']:<15} {r['quadrant']}")
    print()
    print("\n".join(summary(rows)))
    print(CAVEAT)
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
