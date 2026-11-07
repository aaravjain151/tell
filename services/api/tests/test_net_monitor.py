import socket
import types

import pytest

from doublespeak import net_monitor

psutil = pytest.importorskip("psutil")


def conn(ip, port=443, status="ESTABLISHED"):
    return types.SimpleNamespace(raddr=types.SimpleNamespace(ip=ip, port=port) if ip else (), status=status)


class FakeProc:
    def __init__(self, conns): self._c = conns
    def net_connections(self, kind="inet"): return self._c
    def children(self, recursive=True): return []


def fake_table(monkeypatch, conns):
    monkeypatch.setattr(net_monitor, "_procs", lambda: [FakeProc(conns)])


def test_loopback_variants_are_not_counted(monkeypatch):
    fake_table(monkeypatch, [conn("127.0.0.1"), conn("::1"), conn("127.0.0.2"), conn("::ffff:127.0.0.1"), conn("fe80::1%lo0", status="LISTEN")])
    assert net_monitor.outbound() == []


def test_outside_endpoints_are_reported(monkeypatch):
    fake_table(monkeypatch, [conn("93.184.216.34", 443), conn("192.168.1.20", 8080), conn("127.0.0.1")])
    assert net_monitor.outbound() == ["192.168.1.20:8080", "93.184.216.34:443"]


def test_listening_sockets_and_unconnected_sockets_are_ignored(monkeypatch):
    fake_table(monkeypatch, [conn("8.8.8.8", status="LISTEN"), conn(None)])
    assert net_monitor.outbound() == []


def test_watch_remembers_a_connection_that_closed_before_the_end(monkeypatch):
    states = iter([[], ["1.2.3.4:443"], ["1.2.3.4:443"], []] + [[]] * 500)
    monkeypatch.setattr(net_monitor, "outbound", lambda: next(states))
    with net_monitor.watch(interval_s=0.001) as w:
        import time; time.sleep(0.05)
    r = w.report()
    assert r["os_outbound_count"] == 1 and r["os_outbound_seen"] == ["1.2.3.4:443"] and r["os_check"] == "ok"


def test_reports_unavailable_instead_of_raising_without_psutil(monkeypatch):
    monkeypatch.setattr(net_monitor, "psutil", None)
    assert net_monitor.outbound() is None
    with net_monitor.watch() as w:
        pass
    assert w.report()["os_check"] == "unavailable" and net_monitor.snapshot_report()["os_check"] == "unavailable"


def test_real_loopback_connection_is_not_counted():
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
    cli = socket.create_connection(srv.getsockname()); peer, _ = srv.accept()
    try:
        assert net_monitor.outbound() == []
    finally:
        for s in (cli, peer, srv): s.close()


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))               # UDP connect only picks a route; sends nothing
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return None if ip.startswith("127.") else ip


def test_real_non_loopback_connection_is_counted():
    ip = lan_ip()
    if not ip:
        pytest.skip("no non-loopback interface on this machine")
    srv = socket.socket(); srv.bind((ip, 0)); srv.listen(1)       # a listener on our own LAN address: never leaves the machine
    cli = socket.create_connection(srv.getsockname()); peer, _ = srv.accept()
    try:
        assert f"{ip}:{srv.getsockname()[1]}" in net_monitor.outbound()
    finally:
        for s in (cli, peer, srv): s.close()


def test_analysis_reports_the_os_check():
    from doublespeak import pipeline
    v = pipeline.analyze(None, "hello there, this is a short test call about lunch plans for tomorrow afternoon")
    assert v.egress["os_check"] in ("ok", "unavailable") and v.egress["os_outbound_count"] == 0
