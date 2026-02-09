"""
agent.collectors.cpu
AUTHOR: carter-vin

CPU collector
- Linux-first, macOS compatible for load average
- stdlib only
- degrade gracefully when load averages are unavailable
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional


@dataclass(frozen=True)
class CpuResult:
    loadavg_1m: Optional[float]
    loadavg_5m: Optional[float]
    loadavg_15m: Optional[float]
    cpu_count_logical: Optional[int]


def collect_cpu() -> CpuResult:
    """
    Collect CPU load averages and logical CPU count

    Load averages are unavailable on some platforms
    """
    loadavg_1m: Optional[float] = None
    loadavg_5m: Optional[float] = None
    loadavg_15m: Optional[float] = None

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
