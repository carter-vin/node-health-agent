"""
agent.collectors.memory

Memory totals from /proc/meminfo (Linux). Returns None values on non-Linux.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROC_MEMINFO = Path("/proc/meminfo")


@dataclass(frozen=True)
class MemoryResult:
    mem_total_bytes: int | None
    mem_available_bytes: int | None


def _parse_meminfo(contents: str) -> dict[str, int]:
    """Parse /proc/meminfo into a dict of field name → bytes."""
    values: dict[str, int] = {}
    for line in contents.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        key = parts[0].rstrip(":")
        try:
            value_kb = int(parts[1])
        except ValueError:
            continue
        values[key] = value_kb * 1024
    return values


def collect_memory() -> MemoryResult:
    """Return memory totals from /proc/meminfo; returns None values on non-Linux."""
    if not PROC_MEMINFO.exists():
        return MemoryResult(mem_total_bytes=None, mem_available_bytes=None)

    contents = PROC_MEMINFO.read_text(encoding="utf-8")
    values = _parse_meminfo(contents)

    mem_total = values.get("MemTotal")
    mem_available = values.get("MemAvailable")

    if mem_total is None or mem_available is None:
        raise RuntimeError("MemAvailable or MemTotal missing in /proc/meminfo")

    return MemoryResult(mem_total_bytes=mem_total, mem_available_bytes=mem_available)
