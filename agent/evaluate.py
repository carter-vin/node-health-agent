"""
agent.evaluate
AUTHOR: carter-vin

Health evaluation based on collector signals
"""

from __future__ import annotations

from typing import Any, Iterable

from agent.collectors.cpu import CpuResult
from agent.collectors.disk import DiskResult
from agent.collectors.memory import MemoryResult

# Retained as module-level defaults for backward compatibility.
# Prefer passing a config dict from agent.config.load_config().
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
    *,
    config: dict[str, Any] | None = None,
) -> tuple[str, list[str]]:
    """
    Evaluate health and reasons from signals and failures.

    config: normalized threshold config from agent.config.load_config().
            Falls back to module-level constants when None.
    """
    cfg_cpu = (config or {}).get("cpu", {})
    cfg_mem = (config or {}).get("mem", {})
    cfg_disk = (config or {}).get("disk", {})

    cpu_degraded_factor = cfg_cpu.get("degraded_factor", CPU_DEGRADED_FACTOR)
    cpu_unhealthy_factor = cfg_cpu.get("unhealthy_factor", CPU_UNHEALTHY_FACTOR)
    mem_degraded_pct = cfg_mem.get("degraded_pct", MEM_DEGRADED_PCT)
    mem_unhealthy_pct = cfg_mem.get("unhealthy_pct", MEM_UNHEALTHY_PCT)
    disk_degraded_pct = cfg_disk.get("degraded_pct", DISK_DEGRADED_PCT)
    disk_unhealthy_pct = cfg_disk.get("unhealthy_pct", DISK_UNHEALTHY_PCT)

    reason_set = set(failure_reasons)

    if cpu and cpu.loadavg_1m is not None and cpu.cpu_count_logical:
        degraded_threshold = cpu.cpu_count_logical * cpu_degraded_factor
        unhealthy_threshold = cpu.cpu_count_logical * cpu_unhealthy_factor
        if cpu.loadavg_1m > unhealthy_threshold:
            reason_set.add("signal:cpu_critical")
        elif cpu.loadavg_1m > degraded_threshold:
            reason_set.add("signal:cpu_high")

    if memory and memory.mem_available_bytes is not None and memory.mem_total_bytes:
        mem_pct = _pct(memory.mem_available_bytes, memory.mem_total_bytes)
        if mem_pct is not None:
            if mem_pct < mem_unhealthy_pct:
                reason_set.add("signal:mem_available_critical")
            elif mem_pct < mem_degraded_pct:
                reason_set.add("signal:mem_available_low")

    if disk and disk.disk_free_bytes is not None and disk.disk_total_bytes:
        disk_pct = _pct(disk.disk_free_bytes, disk.disk_total_bytes)
        if disk_pct is not None:
            if disk_pct < disk_unhealthy_pct:
                reason_set.add("signal:disk_free_critical")
            elif disk_pct < disk_degraded_pct:
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
