#!/usr/bin/env python3
"""Replay a WAV file into a running Doublespeak API over the streaming WebSocket, as if it were a live call.

    python3 tools/stream_wav.py data/calls/human/x.wav [--speed 1] [--side far] [--url http://127.0.0.1:8000]

Used by tests and as the demo fallback when no live audio source is available. Loopback only: it refuses any
non-loopback --url. Needs numpy and `websockets` (both come with services/api/requirements.txt). Audio is read from the
file and sent frame by frame; nothing is written anywhere. Exit code 0 when a final message arrived.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

import numpy as np  # noqa: E402

from doublespeak import audio  # noqa: E402

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def load_pcm16(path: str) -> bytes:
    x, _sr, _ms = audio.decode(Path(path).read_bytes())          # mono float32 @ 16 kHz
    return (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()


def create_session(base: str, origin: str) -> dict:
    # No proxies: a loopback request must not be carried anywhere else by HTTP_PROXY.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(base + "/session", method="POST", data=b"{}",
                                 headers={"Origin": origin, "Content-Type": "application/json"})
    with opener.open(req, timeout=10) as r:
        return json.loads(r.read())


def fmt(m: dict) -> str:
    if m.get("type") == "verdict":
        return (f"[{m['window'][0]:6.1f}-{m['window'][1]:6.1f}s] {m['tier']:<14} p_ai={m['p_ai']:.2f} "
                f"p_scam={m['p_scam']:.2f} conf={m['confidence']:.2f} lag={m['lag_s']:.1f}s  {m['headline']}")
    return json.dumps(m)


async def run(args: argparse.Namespace) -> int:
    import websockets

    u = urlparse(args.url)
    if (u.hostname or "") not in LOOPBACK:
        print("refusing: --url must be a loopback address", file=sys.stderr)
        return 2
    pcm = load_pcm16(args.wav)
    info = create_session(args.url.rstrip("/"), args.origin)
    ws_url = f"ws://{u.netloc}{info['ws_path']}"
    frame_bytes = int(16000 * args.frame_ms / 1000) * 2
    got_final = False
    async with websockets.connect(ws_url, additional_headers={"Origin": args.origin}, max_size=1 << 20,
                                  proxy=None) as ws:
        await ws.send(json.dumps({"type": "hello", "token": info["token"], "sample_rate": 16000,
                                  "format": "pcm_s16le", "side": args.side}))
        first = json.loads(await ws.recv())
        if first.get("type") != "ready":
            print(fmt(first), file=sys.stderr)
            return 1

        async def reader() -> None:
            nonlocal got_final
            async for raw in ws:
                m = json.loads(raw)
                print(fmt(m), flush=True)
                if m.get("type") == "final":
                    got_final = True
                    return
                if m.get("type") == "error":
                    return

        rd = asyncio.ensure_future(reader())
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        sent = 0
        for i in range(0, len(pcm), frame_bytes):
            if rd.done():
                break
            await ws.send(pcm[i:i + frame_bytes])
            sent += min(frame_bytes, len(pcm) - i)
            due = t0 + (sent / 2 / 16000) / args.speed
            await asyncio.sleep(max(0.0, due - loop.time()))
        if not rd.done():
            if args.drain_s > 0:                       # let the last tick finish before we stop
                await asyncio.sleep(args.drain_s)
            await ws.send(json.dumps({"type": "stop"}))
        try:
            await asyncio.wait_for(rd, 15)
        except asyncio.TimeoutError:
            print("no final message", file=sys.stderr)
    return 0 if got_final else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("wav")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--speed", type=float, default=1.0, help="1 = real time, 4 = four times faster")
    ap.add_argument("--side", choices=("far", "near", "mix"), default="far")
    ap.add_argument("--frame-ms", type=int, default=100)
    ap.add_argument("--origin", default="http://localhost:5173", help="an allowed UI origin (DOUBLESPEAK_CORS_ORIGINS)")
    ap.add_argument("--drain-s", type=float, default=2.0)
    args = ap.parse_args()
    if args.speed <= 0:
        ap.error("--speed must be positive")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
