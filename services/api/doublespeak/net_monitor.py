"""Independent, OS-level proof that nothing left the machine (idea ported from teammate branch sam_dev1).

privacy.py counts what *our code* says it sent, which is self-reported. This asks the operating system instead: which
non-loopback remote endpoints do this process and its children hold connections to? During every analysis a short
poll collects any that appear, and the verdict reports them next to our own counters.

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
