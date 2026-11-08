"""Headless Chrome check of the web page against a running engine, over the DevTools protocol (no extension, no npm).

    .venv/bin/python tools/web/devtools_check.py --page http://localhost:5184/ --api http://127.0.0.1:8014 \
        --token-file /path/to/api_token --shot /tmp/home.png

Opens `<page>?api=<api>#token=<token>` (the pairing link `make pair-url` prints), waits up to --wait-s for the Home
chip to say it is connected and for the privacy rows to show real /health numbers, prints what it saw as JSON and
exits 0 when both rendered, 1 otherwise. The token is passed in the URL fragment, which never reaches any server.
Needs Google Chrome (or CHROME=/path/to/chrome) and the `websockets` package from the API requirements.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

CHROME_CANDIDATES = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium")

PROBE_JS = r"""(() => {
  const t = id => { const e = document.getElementById(id); return e ? e.textContent.trim() : null; };
  const facts = [...document.querySelectorAll('#home-facts > div')].map(d => [d.children[0] && d.children[0].textContent.trim(), d.children[1] && d.children[1].textContent.trim()]);
  return {chip_state: (document.getElementById('chip') || {}).dataset ? document.getElementById('chip').dataset.state : null,
          chip: t('chiptext'), hero: t('home-h'), hero_state: (document.getElementById('home-hero') || {dataset: {}}).dataset.s,
          facts, url: location.href, hash: location.hash,
          token_in_session: (() => { try { return !!sessionStorage.getItem('tell-token'); } catch (e) { return null; } })()};
})()"""


def chrome_binary() -> str | None:
    env = os.environ.get("CHROME")
    for c in ((env,) if env else ()) + CHROME_CANDIDATES:
        if c and (Path(c).exists() or shutil.which(c)):
            return c if Path(c).exists() else shutil.which(c)
    return None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Chrome:
    def __init__(self, binary: str, width: int = 1280, height: int = 900) -> None:
        self.port = free_port()
        self.profile = tempfile.mkdtemp(prefix="tell-cdp-")
        self.proc = subprocess.Popen([binary, "--headless=new", f"--remote-debugging-port={self.port}",
                                      f"--user-data-dir={self.profile}", "--no-first-run", "--no-default-browser-check",
                                      "--force-prefers-reduced-motion", f"--window-size={width},{height}", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def ws_url(self, timeout: float = 15.0) -> str:
        end = time.time() + timeout
        while time.time() < end:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list", timeout=1) as r:
                    for t in json.load(r):
                        if t.get("type") == "page":
                            return t["webSocketDebuggerUrl"]
            except OSError:
                pass
            time.sleep(0.2)
        raise RuntimeError("Chrome did not open a DevTools port")

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


class CDP:
    def __init__(self, ws) -> None:
        self.ws, self.n = ws, 0

    async def call(self, method: str, **params):
        self.n += 1
        mid = self.n
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            m = json.loads(await self.ws.recv())
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})

    async def eval(self, expr: str):
        r = await self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")


def _fact(seen: dict, prefix: str) -> str | None:
    return next((v for k, v in (tuple(f) for f in seen.get("facts") or [] if len(f) == 2) if k and k.startswith(prefix)), None)


def connected(seen: dict) -> bool:
    """Paired and connected: chip 'up', hero Armed, both privacy rows show real /health numbers, token out of the URL."""
    audio = _fact(seen, "Caller audio blocked from leaving by code")
    osrow = _fact(seen, "Engine network connections seen by the OS")
    return (seen.get("chip_state") == "up" and seen.get("hero") in ("Armed", "Listening now")
            and audio is not None and audio.endswith(" B") and audio[:1].isdigit()
            and osrow is not None and osrow[:1].isdigit() and "token" not in (seen.get("hash") or ""))


def unpaired(seen: dict) -> bool:
    """Engine up, page not paired: the calm 'Pair this page' state, never ARMED."""
    return seen.get("chip_state") == "pair" and seen.get("hero_state") == "pair" and seen.get("hero") == "Pair this page"


async def check(page: str, wait_s: float, shot: str | None, binary: str, want=connected) -> dict:
    import websockets
    chrome = Chrome(binary)
    try:
        async with websockets.connect(chrome.ws_url(), max_size=1 << 26, proxy=None) as ws:
            cdp = CDP(ws)
            await cdp.call("Page.enable")
            t0 = time.time()
            await cdp.call("Page.navigate", url=page)
            seen: dict = {}
            while time.time() - t0 < wait_s:
                await asyncio.sleep(0.1)
                try:
                    seen = await cdp.eval(PROBE_JS) or {}
                except RuntimeError:
                    continue
                if want(seen):
                    break
            seen["elapsed_s"] = round(time.time() - t0, 2)
            seen["ok"] = want(seen)
            if shot:
                img = await cdp.call("Page.captureScreenshot", format="png")
                Path(shot).write_bytes(base64.b64decode(img["data"]))
                seen["screenshot"] = shot
            return seen
    finally:
        chrome.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--page", required=True, help="where the page is served, e.g. http://localhost:5173/")
    ap.add_argument("--api", help="engine base URL passed as ?api= (loopback only)")
    ap.add_argument("--token-file", help="pair with the token in this file (default: none, i.e. unpaired)")
    ap.add_argument("--wait-s", type=float, default=2.0)
    ap.add_argument("--shot", help="write a PNG screenshot here")
    ap.add_argument("--expect", choices=("paired", "unpaired"), default="paired",
                    help="paired: connected chip + real privacy numbers; unpaired: the 'Pair this page' state")
    a = ap.parse_args(argv)
    binary = chrome_binary()
    if not binary:
        print("Chrome not found; set CHROME=/path/to/chrome", file=sys.stderr)
        return 2
    url = a.page + (("&" if "?" in a.page else "?") + "api=" + a.api if a.api else "")
    if a.token_file:
        url += "#token=" + Path(a.token_file).read_text().strip()
    seen = asyncio.run(check(url, a.wait_s, a.shot, binary, connected if a.expect == "paired" else unpaired))
    seen["url"] = (seen.get("url") or "").split("#token=")[0]          # never print the token
    print(json.dumps(seen, indent=2))
    return 0 if seen.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
