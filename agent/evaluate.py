"""
agent.evaluate
AUTHOR: carter-vin

Health evaluation based on collector signals
"""

from __future__ import annotations

from typing import Iterable

from agent.collectors.cpu import CpuResult
from agent.collectors.disk import DiskResult
from agent.collectors.memory import MemoryResult

CPU_DEGRADED_FACTOR = 0.85
CPU_UNHEALTHY_FACTOR = 1.25

MEM_DEGRADED_PCT = 15.0
MEM_UNHEALTHY_PCT = 8.0

DISK_DEGRADED_PCT = 10.0
DISK_UNHEALTHY_PCT = 5.0


def _pct(available: int, total: int) -> float | None:
    if total <= 0:
        return None
    return (available / total) * 100.0


def evaluate_health(
    cpu: CpuResult | None,
    memory: MemoryResult | None,
    disk: DiskResult | None,
    failure_reasons: Iterable[str],
) -> tuple[str, list[str]]:
    """
    Evaluate health and reasons from signals and failures
    """
    reason_set = set(failure_reasons)

    if cpu and cpu.loadavg_1m is not None and cpu.cpu_count_logical:
        degraded_threshold = cpu.cpu_count_logical * CPU_DEGRADED_FACTOR
        unhealthy_threshold = cpu.cpu_count_logical * CPU_UNHEALTHY_FACTOR
        if cpu.loadavg_1m > unhealthy_threshold:
            reason_set.add("signal:cpu_critical")
        elif cpu.loadavg_1m > degraded_threshold:
            reason_set.add("signal:cpu_high")

    if memory and memory.mem_available_bytes is not None and memory.mem_total_bytes:
        mem_pct = _pct(memory.mem_available_bytes, memory.mem_total_bytes)
        if mem_pct is not None:
            if mem_pct < MEM_UNHEALTHY_PCT:
                reason_set.add("signal:mem_available_critical")
            elif mem_pct < MEM_DEGRADED_PCT:
                reason_set.add("signal:mem_available_low")

    if disk and disk.disk_free_bytes is not None and disk.disk_total_bytes:
        disk_pct = _pct(disk.disk_free_bytes, disk.disk_total_bytes)
        if disk_pct is not None:
            if disk_pct < DISK_UNHEALTHY_PCT:
                reason_set.add("signal:disk_free_critical")
            elif disk_pct < DISK_DEGRADED_PCT:
                reason_set.add("signal:disk_free_low")

    reasons = sorted(reason_set)

    has_critical = any(reason.endswith("_critical") for reason in reasons)
    has_signal = any(reason.startswith("signal:") for reason in reasons)
    has_failure = any(reason.startswith("collector_failed:") for reason in reasons)

    if has_critical:
        return "UNHEALTHY", reasons
    if has_signal or has_failure:
        return "DEGRADED", reasons
    return "OK", reasons
