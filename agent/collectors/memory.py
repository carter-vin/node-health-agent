"""
agent.collectors.memory
AUTHOR: carter-vin

Memory collector
- Linux-first via /proc/meminfo
- macOS and non-Linux degrade gracefully
- stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PROC_MEMINFO = Path("/proc/meminfo")


@dataclass(frozen=True)
class MemoryResult:
    mem_total_bytes: Optional[int]
    mem_available_bytes: Optional[int]


def _parse_meminfo(contents: str) -> dict[str, int]:
    """
    Parse /proc/meminfo into a dict of values in bytes
    """
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
    """
    Collect memory totals from /proc/meminfo when available

    On non-Linux systems, return empty values without failing
    """
    if not PROC_MEMINFO.exists():
        return MemoryResult(mem_total_bytes=None, mem_available_bytes=None)

    contents = PROC_MEMINFO.read_text(encoding="utf-8")
    values = _parse_meminfo(contents)

    mem_total = values.get("MemTotal")
    mem_available = values.get("MemAvailable")

    if mem_total is None or mem_available is None:
        raise RuntimeError("MemAvailable or MemTotal missing in /proc/meminfo")

    return MemoryResult(mem_total_bytes=mem_total, mem_available_bytes=mem_available)
