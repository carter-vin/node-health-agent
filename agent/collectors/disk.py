"""
agent.collectors.disk

Disk usage via shutil.disk_usage (cross-platform, stdlib only).
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
    """Collect disk usage statistics for the given filesystem path."""
    usage = shutil.disk_usage(path)
    return DiskResult(
        disk_total_bytes=usage.total,
        disk_used_bytes=usage.used,
        disk_free_bytes=usage.free,
    )
