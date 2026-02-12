"""
triage.render.utils
AUTHOR: carter-vin

Formatting helpers for renderers
"""

from __future__ import annotations


def format_gb(bytes_value: int | None) -> str:
    if bytes_value is None:
        return "n/a"
    gb = bytes_value / (1024 ** 3)
    if gb >= 10:
        return f"{gb:.0f} GB"
    return f"{gb:.1f} GB"


def format_gb_compact(bytes_value: int | None) -> str:
    if bytes_value is None:
        return "n/a"
    gb = bytes_value / (1024 ** 3)
    if gb >= 10:
        return f"{gb:.0f}G"
    return f"{gb:.1f}G"


def format_load(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"
