"""
agent.collectors.disk
AUTHOR: carter-vin

Disk collector
- Uses shutil.disk_usage for cross-platform support
- stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass
import shutil


@dataclass(frozen=True)
class DiskResult:
    disk_total_bytes: int
    disk_used_bytes: int
    disk_free_bytes: int


def collect_disk(path: str = "/") -> DiskResult:
    """
    Collect disk usage for a given path
    """
    usage = shutil.disk_usage(path)
    return DiskResult(
        disk_total_bytes=usage.total,
        disk_used_bytes=usage.used,
        disk_free_bytes=usage.free,
    )
