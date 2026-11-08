"""Independent, OS-level proof that nothing left the machine (idea ported from teammate branch sam_dev1).

privacy.py counts what *our code* says it sent, which is self-reported. This asks the operating system instead: which
non-loopback remote endpoints do this process and its children hold connections to? During every analysis a short
poll collects any that appear, and the verdict reports them next to our own counters. `Cumulative` does the same for
the whole engine lifetime (one 250 ms poller from start) and feeds /health and /ready with counts only.

It is a transparency check, not a firewall: polling can miss a connection that lives for less than the poll interval,
unconnected UDP (e.g. a DNS lookup) has no remote endpoint to read, and separate programs we call (Ollama, VoiceStudio)
are their own processes. Needs `psutil`; without it the check reports `unavailable` and nothing else changes.
Deliberately imports no network library (tests/test_privacy.py scans this package).
"""
from __future__ import annotations

import ipaddress
import threading
import time

try:
    import psutil
except ImportError:  # the check degrades, the product does not
    psutil = None

_LIVE = {"ESTABLISHED", "SYN_SENT", "SYN_RECV", "CLOSE_WAIT", "FIN_WAIT1", "FIN_WAIT2", "LAST_ACK", "CLOSING", "TIME_WAIT"}


def _is_loopback(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return False
    return ip.is_loopback or bool(getattr(ip, "ipv4_mapped", None) and ip.ipv4_mapped.is_loopback)


def _procs():
    me = psutil.Process()
    return [me, *me.children(recursive=True)]


def outbound() -> list[str] | None:
    """Non-loopback remote endpoints ("host:port") held right now by this process and its children, or None if unavailable."""
    if psutil is None:
        return None
    seen: set[str] = set()
    try:
        for p in _procs():
            try:
                conns = p.net_connections(kind="inet") if hasattr(p, "net_connections") else p.connections(kind="inet")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            for c in conns:
                if not c.raddr or (c.status and c.status != "NONE" and c.status not in _LIVE):
                    continue
                if not _is_loopback(c.raddr.ip):
                    seen.add(f"{c.raddr.ip}:{c.raddr.port}")
    except Exception:  # noqa: BLE001 - an unreadable process table must not break an analysis
        return None
    return sorted(seen)


class watch:
    """Context manager: poll `outbound()` on a background thread and remember everything seen."""

    def __init__(self, interval_s: float = 0.05):
        self.interval, self.seen, self.polls, self.ok = interval_s, set(), 0, psutil is not None
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def _poll(self) -> None:
        r = outbound()
        if r is None:
            self.ok = False
            return
        self.polls += 1
        self.seen.update(r)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._poll()

    def __enter__(self) -> "watch":
        self._poll()
        if self.ok:
            self._t = threading.Thread(target=self._run, daemon=True)
            self._t.start()
        return self

    def __exit__(self, *exc) -> bool:
        self._stop.set()
        if self._t:
            self._t.join(timeout=1)
        self._poll()
        return False

    def report(self) -> dict:
        return {"os_check": "ok" if self.ok else "unavailable", "os_outbound_count": len(self.seen),
                "os_outbound_seen": sorted(self.seen)[:20], "os_polls": self.polls}


def snapshot_report() -> dict:
    r = outbound()
    return {"os_check": "unavailable" if r is None else "ok", "os_outbound_count": len(r or []), "os_outbound_seen": (r or [])[:20]}


class Cumulative:
    """Engine-lifetime watcher: polls `outbound()` every `interval_s` on one daemon thread from engine start and
    remembers every non-loopback endpoint the engine process tree has held. /health and /ready report it, so the
    number on screen covers everything since start, not a snapshot at request time. Same limits as `watch`
    (sub-interval connections and unconnected UDP can be missed). Reports counts only, never the addresses."""

    def __init__(self, interval_s: float = 0.25) -> None:
        self.interval = interval_s
        self.ok = psutil is not None
        self.endpoints: set[str] = set()
        self.first_seen: float | None = None
        self.polls = 0
        self.started_at: float | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def poll(self) -> None:
        r = outbound()
        with self._lock:
            if r is None:
                self.ok = False
                return
            self.ok = True
            self.polls += 1
            if r and self.first_seen is None:
                self.first_seen = time.time()
            self.endpoints.update(r)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.poll()

    def start(self) -> "Cumulative":
        with self._lock:
            if self._t is not None and self._t.is_alive():
                return self
            if self.started_at is None:
                self.started_at = time.time()
            self._stop.clear()
            t = self._t = threading.Thread(target=self._run, name="net-watch", daemon=True)
        self.poll()
        if psutil is not None:
            t.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def report(self) -> dict:
        def iso(t: float | None) -> str | None:
            return None if t is None else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
        with self._lock:
            hosts = {e.rsplit(":", 1)[0] for e in self.endpoints}
            return {"os_check": "ok" if self.ok else "unavailable", "scope": "since_engine_start",
                    "since": iso(self.started_at), "os_outbound_count": len(self.endpoints),
                    "os_remote_addresses": len(hosts), "os_first_seen": iso(self.first_seen),
                    "os_polls": self.polls, "interval_s": self.interval}


CUMULATIVE = Cumulative()


def cumulative_report() -> dict:
    """Counts since engine start (starts the watcher on first use, e.g. a test without the startup event)."""
    return CUMULATIVE.start().report()
