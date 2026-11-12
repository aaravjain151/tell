"""Score QA recordings with the Doublespeak detector API (loopback only).

    python tools/qa_score.py qa_out/ --api http://127.0.0.1:8000

POSTs each qa_out/<scenario>/call.wav to <api>/analyze (multipart field 'audio') and prints
scenario | expected | got tier | p_ai | p_scam | confidence | correct?. Non-loopback API URLs are refused.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlparse

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class NotLoopback(ValueError):
    pass


def ensure_loopback(url: str) -> str:
    u = urlparse(url)
    if u.scheme not in ("http", "https") or u.hostname not in LOOPBACK:
        raise NotLoopback(f"refused: --api must be a loopback URL (127.0.0.1 / localhost / ::1), got {url!r}")
    return url.rstrip("/")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None  # never follow a redirect off the loopback host


def post_audio(api: str, wav: bytes, filename: str = "call.wav", timeout: float = 120.0) -> dict:
    api = ensure_loopback(api)
    b = uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"{filename}\"\r\n"
            f"Content-Type: audio/wav\r\n\r\n").encode() + wav + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(api + "/analyze", data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)  # no proxies either
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read())


def load_runs(root: Path) -> list[tuple[dict, Path]]:
    runs = []
    for lab in sorted(Path(root).glob("*/label.json")):
        wav = lab.parent / "call.wav"
        if wav.exists():
            runs.append((json.loads(lab.read_text(encoding="utf-8")), wav))
    return runs


def format_table(rows: list[dict]) -> str:
    head = ["scenario", "expected", "got tier", "p_ai", "p_scam", "confidence", "correct?"]
    cells = [head] + [[r["scenario"], r["expected"], r["got"], r["p_ai"], r["p_scam"], r["confidence"], r["correct"]] for r in rows]
    w = [max(len(str(c[i])) for c in cells) for i in range(len(head))]
    line = lambda c: " | ".join(str(x).ljust(w[i]) for i, x in enumerate(c))  # noqa: E731
    return "\n".join([line(head), "-+-".join("-" * x for x in w)] + [line(c) for c in cells[1:]])


def main(argv=None, poster=post_audio) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", help="qa_out/ directory")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    a = ap.parse_args(argv)
    try:
        api = ensure_loopback(a.api)
    except NotLoopback as e:
        print(e, file=sys.stderr)
        return 2
    runs = load_runs(Path(a.root))
    if not runs:
        print(f"no qa_out/<scenario>/call.wav + label.json found under {a.root}", file=sys.stderr)
        return 1
    rows = []
    for label, wav in runs:
        try:
            v = poster(api, wav.read_bytes())
        except (urllib.error.URLError, OSError, ValueError) as e:
            print(f"{label['scenario']}: detector request failed: {e}", file=sys.stderr)
            return 1
        got = v.get("tier")
        rows.append({"scenario": label["scenario"], "expected": label["expected_tier"], "got": got,
                     "p_ai": f"{v.get('p_ai', float('nan')):.2f}", "p_scam": f"{v.get('p_scam', float('nan')):.2f}",
                     "confidence": f"{v.get('confidence', float('nan')):.2f}",
                     "correct": "yes" if got == label["expected_tier"] else "NO"})
    print(format_table(rows))
    ok = sum(r["correct"] == "yes" for r in rows)
    print(f"\n{ok}/{len(rows)} correct.")
    print("Caveat: a handful of synthetic clips from one voice is a sanity check, not a measurement; it says nothing "
          "about accuracy on real calls, other voices or other phrasings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
