"""
agent.collectors.cpu

CPU load averages and logical core count. Degrades gracefully on platforms
where load averages are unavailable (e.g. Windows).
"""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class CpuResult:
    loadavg_1m: float | None
    loadavg_5m: float | None
    loadavg_15m: float | None
    cpu_count_logical: int | None


def collect_cpu() -> CpuResult:
    """Collect CPU load averages and logical CPU count."""
    loadavg_1m: float | None = None
    loadavg_5m: float | None = None
    loadavg_15m: float | None = None

    try:
        loadavg_1m, loadavg_5m, loadavg_15m = os.getloadavg()
    except (OSError, AttributeError):
        pass

    cpu_count = os.cpu_count()

    if loadavg_1m is None and cpu_count is None:
        raise RuntimeError("CPU metrics unavailable")

    return CpuResult(
        loadavg_1m=loadavg_1m,
        loadavg_5m=loadavg_5m,
        loadavg_15m=loadavg_15m,
        cpu_count_logical=cpu_count,
    )
