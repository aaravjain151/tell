#!/usr/bin/env python3
"""Tiny local mock of the Doublespeak live feed, so apps/web/index.html can be tested without the engine.

    python3 apps/web/mock_live.py                       # both scripts in a loop, one tick every 2 s
    python3 apps/web/mock_live.py --script scam --interval 0.05 --stop-at 12   # hold at tick 12 (for screenshots)
    open "apps/web/index.html?api=http://127.0.0.1:8123"

Implements the SSE contract: GET /live/events (state, verdict, ended), POST /live/dismiss, POST /live/stop,
plus /health and /thresholds so the page's header chip works. Standard library only, loopback only.
Verdicts reuse the real engine output embedded in index.html (#samples-data), so the shape is the real one.
"""
import argparse, copy, json, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
html = (HERE / "index.html").read_text(encoding="utf-8")
SAMPLES = json.loads(re.search(r'<script id="samples-data" type="application/json">(.*?)</script>', html, re.S).group(1))

# (tick the line is spoken at, text)
SCAM_LINES = [
    (0, "Hi Grandma, it's me."), (2, "How are you doing? I wanted to hear your voice."),
    (4, "I was thinking about coming over this weekend."),
    (7, "Grandma, it's me, this is your grandson."),
    (8, "I'm in trouble, I got in an accident and I'm at the police station."),
    (10, "I need bail money right now, please don't tell mom or dad."),
    (12, "The officer says you can wire the money within the hour."),
    (14, "Please hurry, I'm scared."), (17, "Don't hang up. Just do it quickly."),
]
AI_LINES = [
    (0, "Hello, I'm an AI assistant calling on behalf of Summit Realty."), (2, "This call is AI generated."),
    (4, "I am here to help schedule a showing for the unit you inquired about."),
    (7, "Would Wednesday at noon work for you?"), (10, "Is there anything else I can help you with?"),
]


def scam_stage(k):
    """-> (instant verdict tier, stable dict) for the grandparent-scam script."""
    if k <= 2: return "unsure", dict(tier="unsure", state="warming", alert="none", since_s=0, reasons=[])
    if k <= 6: return "human", dict(tier="human", state="steady", alert="none", since_s=3, reasons=["Nothing in this call stood out strongly."])
    if k <= 8: return "unsure", dict(tier="unsure", state="escalated", alert="amber", since_s=7,
                                      reasons=["They claimed to be someone you know or trust"])
    return "scam", dict(tier="scam", state="latched", alert="red", since_s=9, reasons=[
        "They claimed to be someone you know or trust", "They asked you to pay or send money",
        "They pressed you to act right now", "They asked you to keep this secret"])


def ai_stage(k):
    if k <= 1: return "unsure", dict(tier="unsure", state="warming", alert="none", since_s=0, reasons=[])
    return "ai_disclosed", dict(tier="ai_disclosed", state="steady", alert="none", since_s=2,
                                reasons=["The caller said it is automated"])


SCRIPTS = {
    "scam": dict(source="BlackHole 2ch (call audio)", lines=SCAM_LINES, stage=scam_stage, last=22, base="scam"),
    "ai": dict(source="Default microphone", lines=AI_LINES, stage=ai_stage, last=12, base="ai_disclosed"),
}


def verdict_for(name, k, tier):
    sc = SCRIPTS[name]
    v = copy.deepcopy(SAMPLES[sc["base"]])
    v["transcript"] = " ".join(t for at, t in sc["lines"] if at <= k)
    if name == "scam":                       # a human voice with scam wording: the 2x2 and scores are recomputed by the page
        v.pop("scores", None); v.pop("quadrant", None); v["p_ai"] = 0.31; v["disclosed_ai"] = False
        for t in v["tells"]:
            if t["family"] == "acoustic": t["score"] = 0.2
        for key in ("headline", "advice"): v[key] = SAMPLES["scam"][key]
        v["p_scam"] = 0.98 if tier == "scam" else 0.42 if tier == "unsure" and k >= 7 else 0.02
        v["tier"] = tier
        if tier != "scam":
            keep = {"impersonation"} if tier == "unsure" and k >= 7 else set()
            v["tells"] = [t for t in v["tells"] if t["name"] in keep]
        if tier == "human": v["headline"], v["advice"] = SAMPLES["human"]["headline"], SAMPLES["human"]["advice"]
        if tier == "unsure": v["headline"], v["advice"] = "Not sure yet", "Not enough to judge yet."
    else:
        v["tier"] = tier
        if tier == "unsure": v["headline"], v["advice"] = "Not sure yet", "Not enough to judge yet."
    return v


class State:
    dismissed = threading.Event()
    stop = threading.Event()
    lock = threading.Lock()


ARGS = None


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type")

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self._cors()
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.send_header("Content-Length", "0"); self.end_headers()

    def do_POST(self):
        if self.path.startswith("/live/dismiss"): State.dismissed.set(); return self._json(200, {"ok": True})
        if self.path.startswith("/live/stop"): State.stop.set(); return self._json(200, {"ok": True})
        self._json(404, {"detail": "not found"})

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._json(200, {"ok": True, "thresholds_version": "mock", "egress": {"caller_audio_bytes_sent": 0}})
        if self.path.startswith("/thresholds"): return self._json(200, {"P_AI_THRESHOLD": 0.6})
        if self.path.startswith("/live/events"): return self.events()
        self._json(404, {"detail": "not found"})

    def send(self, obj):
        self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n"); self.wfile.flush()

    def nap(self, secs):
        end = time.time() + secs
        while time.time() < end:
            if State.stop.is_set(): return
            time.sleep(min(0.05, max(0, end - time.time())))

    def hold(self):
        while True:                           # keep the connection open with comments
            self.wfile.write(b": keepalive\n\n"); self.wfile.flush(); time.sleep(5)

    def events(self):
        self.send_response(200); self._cors()
        self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive"); self.end_headers()
        try:
            names = ["scam", "ai"] if ARGS.script == "both" else [ARGS.script]
            if ARGS.idle:
                self.send({"type": "state", "active": False, "source": "", "elapsed_s": 0, "listening": False}); self.hold()
            n = 0
            while True:
                name = names[n % len(names)]; n += 1; sc = SCRIPTS[name]
                State.dismissed.clear(); State.stop.clear(); t0 = time.time()
                self.send({"type": "state", "active": True, "source": sc["source"], "elapsed_s": 0, "listening": True})
                for k in range(sc["last"] + 1):
                    tier, st = sc["stage"](k)
                    if name == "scam" and State.dismissed.is_set() and st["alert"] == "red":
                        st = dict(st, alert="none")
                    if name == "scam" and k == 17 and not State.dismissed.is_set() and not ARGS.no_auto_dismiss:
                        State.dismissed.set(); st = dict(st, alert="none")
                    el = round(k * (ARGS.clock or ARGS.interval), 1)
                    self.send({"type": "verdict", "tick": k, "elapsed_s": el, "verdict": verdict_for(name, k, tier), "stable": st})
                    if ARGS.stop_at is not None and k >= ARGS.stop_at: self.hold()
                    self.nap(ARGS.interval)
                    if State.stop.is_set(): break
                self.send({"type": "ended", "reason": "stopped" if State.stop.is_set() else "call ended"})
                self.send({"type": "state", "active": False, "source": sc["source"], "elapsed_s": round(time.time() - t0, 1), "listening": False})
                if ARGS.hold_ended: self.hold()
                self.nap(6 if not ARGS.no_gap else 0.2)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8123)
    ap.add_argument("--script", choices=["scam", "ai", "both"], default="both")
    ap.add_argument("--interval", type=float, default=2.0, help="seconds between ticks; elapsed_s advances by the same amount")
    ap.add_argument("--clock", type=float, default=None, help="call seconds per tick (default: same as --interval)")
    ap.add_argument("--stop-at", type=int, default=None, help="hold the feed open after this tick (screenshots)")
    ap.add_argument("--hold-ended", action="store_true", help="after the call ends, stay on the ended screen")
    ap.add_argument("--idle", action="store_true", help="connected, but no call: shows the empty state")
    ap.add_argument("--no-auto-dismiss", action="store_true", help="do not dismiss the red alert by itself near the end")
    ap.add_argument("--no-gap", action="store_true")
    ARGS = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", ARGS.port), H); srv.daemon_threads = True
    print(f"mock live feed on http://127.0.0.1:{ARGS.port}  (open index.html?api=http://127.0.0.1:{ARGS.port})", flush=True)
    srv.serve_forever()
