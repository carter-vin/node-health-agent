"""
agent.collectors.network

Network I/O and active TCP connections from /proc (Linux). Returns None
values on non-Linux without raising.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROC_NET_DEV = Path("/proc/net/dev")
PROC_NET_TCP = Path("/proc/net/tcp")
PROC_NET_TCP6 = Path("/proc/net/tcp6")

_TCP_ESTABLISHED = "01"  # /proc/net/tcp state field value for ESTABLISHED


@dataclass(frozen=True)
class NetworkResult:
    net_rx_bytes_total: int | None
    net_tx_bytes_total: int | None
    net_active_tcp_connections: int | None


def _parse_net_dev(contents: str) -> tuple[int, int]:
    """
    Parse /proc/net/dev and return (rx_bytes_total, tx_bytes_total)
    summed across all non-loopback interfaces.

    File layout (after 2-line header):
      iface: rx_bytes rx_packets rx_errs ... tx_bytes tx_packets ...
    Columns (space-delimited after the colon):
      [0]=rx_bytes [8]=tx_bytes
    """
    rx_total = 0
    tx_total = 0
    for line in contents.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        iface, rest = line.split(":", 1)
        iface = iface.strip()
        if iface == "lo":
            continue
        parts = rest.split()
        if len(parts) < 9:
            continue
        try:
            rx_total += int(parts[0])
            tx_total += int(parts[8])
        except (ValueError, IndexError):
            continue
    return rx_total, tx_total


def _count_established_tcp(contents: str) -> int:
    """
    Count ESTABLISHED TCP connections from /proc/net/tcp or /proc/net/tcp6.
    State field (4th column, index 3) == "01" means ESTABLISHED.
    The first line is a header; lines with fewer than 4 parts are skipped.
    """
    count = 0
    for line in contents.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        if parts[3] == _TCP_ESTABLISHED:
            count += 1
    return count


def collect_network() -> NetworkResult:
    """
    Collect network I/O totals from /proc/net/dev when available.
    Optionally reads /proc/net/tcp and /proc/net/tcp6 for connection count.

    On non-Linux systems, all fields return None without raising.
    """
    rx_total: int | None = None
    tx_total: int | None = None
    tcp_count: int | None = None

    if PROC_NET_DEV.exists():
        contents = PROC_NET_DEV.read_text(encoding="utf-8")
        rx, tx = _parse_net_dev(contents)
        rx_total = rx
        tx_total = tx

    if PROC_NET_TCP.exists():
        contents = PROC_NET_TCP.read_text(encoding="utf-8")
        tcp_count = _count_established_tcp(contents)
        if PROC_NET_TCP6.exists():
            contents6 = PROC_NET_TCP6.read_text(encoding="utf-8")
            tcp_count += _count_established_tcp(contents6)

    return NetworkResult(
        net_rx_bytes_total=rx_total,
        net_tx_bytes_total=tx_total,
        net_active_tcp_connections=tcp_count,
    )
