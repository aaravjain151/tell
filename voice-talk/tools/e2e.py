"""End-to-end check against a running server (python run.py): type text, collect audio, print latencies.
    python tools/e2e.py --voice demo-say --target es "Hello, how are you today? We are testing a live translation."
Saves nothing to disk unless --wav is given (to a path you choose)."""
import argparse
import asyncio
import json
import time
import wave

import websockets


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--voice", default="demo-say")
    ap.add_argument("--source", default="en")
    ap.add_argument("--target", default="es")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--wav")
    a = ap.parse_args()
    pcm, sr = bytearray(), 24000
    async with websockets.connect(f"ws://127.0.0.1:{a.port}/ws") as ws:
        json.loads(await ws.recv())
        t0 = time.perf_counter()
        await ws.send(json.dumps({"type": "start", "voice": a.voice, "source": a.source, "target": a.target}))
        sent = False
        want_done = None
        done = 0
        seen_src = False
        while True:
            m = await asyncio.wait_for(ws.recv(), 120)
            now = time.perf_counter() - t0
            if isinstance(m, bytes):
                pcm += m
                continue
            d = json.loads(m)
            if d["type"] in ("translation", "disclosure"):
                print(f"{now:6.2f}s {d['type']:<11} #{d['seq']} {d['text']}")
            elif d["type"] == "audio":
                sr = d["sample_rate"]
                print(f"{now:6.2f}s audio       #{d['seq']} {d['samples']/sr:.2f}s")
            elif d["type"] == "chunk_done":
                done += 1
                print(f"{now:6.2f}s chunk_done  #{d['seq']} {d['metrics']}")
                if d["seq"] == 1 and not sent:  # disclosure finished -> now type
                    sent = True
                    t_text = time.perf_counter()
                    await ws.send(json.dumps({"type": "text", "text": a.text}))
                    await ws.send(json.dumps({"type": "flush"}))
                    want_done = None
            elif d["type"] == "error":
                print("ERROR", d)
            if d["type"] == "source":
                seen_src = True
            if sent and seen_src and d["type"] == "state" and d["state"] == "ready":
                break
        print(f"total {time.perf_counter()-t0:.1f}s")
    if a.wav:
        with wave.open(a.wav, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(bytes(pcm))


asyncio.run(main())
