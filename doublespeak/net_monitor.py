"""Network-proof monitor.

DoubleSpeak promises your call never leaves the machine. This module counts the
*outbound* network connections opened by this app's own process, ignoring
loopback (``127.0.0.1`` / ``::1``). It also renders a large, always-visible
Streamlit panel: green "0 outside connections" when clean, red with the remote
address when not. It is a transparency tool, not a firewall.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import psutil

#: Loopback addresses are on-device and therefore ignored (this covers the
#: allowed Ollama connection to localhost:11434).
_LOOPBACK = {"127.0.0.1", "::1", "0.0.0.0", "::"}


@dataclass
class Outbound:
    """A single non-loopback outbound connection."""

    remote_host: str
    remote_port: int
    status: str

    @property
    def label(self) -> str:
        return f"{self.remote_host}:{self.remote_port} ({self.status})"


@dataclass
class OutboundReport:
    """Snapshot of this process's outbound (non-loopback) connections."""

    connections: list[Outbound] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.connections)

    @property
    def is_clean(self) -> bool:
        return self.count == 0


def count_outbound() -> OutboundReport:
    """Return this process's outbound connections, excluding loopback.

    Scoped to the current PID so we report only what DoubleSpeak itself does.
    """
    try:
        proc = psutil.Process(os.getpid())
        raw = proc.net_connections(kind="inet")
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        raw = []

    out: list[Outbound] = []
    for c in raw:
        if not c.raddr:  # no remote address => listening/unconnected socket
            continue
        host = c.raddr.ip
        if host in _LOOPBACK:
            continue
        out.append(Outbound(remote_host=host, remote_port=c.raddr.port, status=c.status))
    return OutboundReport(connections=out)


def render_panel(st, run_every: float = 2.0) -> None:  # noqa: ANN001
    """Render the live network-proof panel in Streamlit.

    Uses ``st.fragment(run_every=...)`` so the panel refreshes about every two
    seconds without rerunning the whole app. Falls back to a one-shot render on
    older Streamlit versions without fragments.
    """

    def _body() -> None:
        report = count_outbound()
        if report.is_clean:
            st.markdown(
                '<div class="net-ok">&#10003; 0 outside connections<br>'
                '<span style="font-size:18px;font-weight:400;">'
                "Your call is staying on this computer.</span></div>",
                unsafe_allow_html=True,
            )
        else:
            rows = "<br>".join(c.label for c in report.connections)
            st.markdown(
                f'<div class="net-bad">&#9888; {report.count} outside '
                f"connection(s)!<br>"
                f'<span style="font-size:18px;font-weight:400;">{rows}</span></div>',
                unsafe_allow_html=True,
            )

    fragment = getattr(st, "fragment", None)
    if fragment is not None:
        decorated = fragment(run_every=run_every)(_body)
        decorated()
    else:  # pragma: no cover - very old Streamlit
        _body()
