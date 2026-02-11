"""
triage.read
AUTHOR: carter-vin

JSONL reader utilities for triage
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import json


def _tail_lines(path: Path, n: int, *, block_size: int = 4096) -> list[str]:
    """
    Read the last n lines of a text file without loading the full file
    """
    if n <= 0:
        return []

    with path.open("rb") as handle:
        handle.seek(0, 2)
        position = handle.tell()
        buffer = b""

        while position > 0 and buffer.count(b"\n") <= n:
            read_size = min(block_size, position)
            position -= read_size
            handle.seek(position)
            buffer = handle.read(read_size) + buffer

        lines = buffer.splitlines()
        if len(lines) > n:
            lines = lines[-n:]

        # Replace invalid bytes to keep tail deterministic
        return [line.decode("utf-8", errors="replace") for line in lines]


def _parse_json_line(line: str) -> dict[str, object] | None:
    """
    Parse a single JSONL line into a dict or return None if invalid
    """
    line = line.strip()
    if not line:
        return None
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def read_jsonl(path: Path) -> Iterable[dict[str, object]]:
    """
    Yield parsed JSON objects from a JSONL file
    """
    # Missing spool means no reports yet
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            payload = _parse_json_line(line)
            if payload is None:
                # Skip invalid JSON without failing triage
                continue
            yield payload


def tail_jsonl_with_stats(path: Path, n: int) -> tuple[list[dict[str, object]], int]:
    """
    Read and parse the last n JSONL entries from a file

    Returns:
    - list of parsed JSON objects
    - count of invalid lines in the tail window
    """
    if n <= 0:
        return [], 0

    # Missing spool means no reports yet
    if not path.exists():
        return [], 0

    tail = _tail_lines(path, n)

    reports: list[dict[str, object]] = []
    invalid = 0
    for line in tail:
        payload = _parse_json_line(line)
        if payload is None:
            if line.strip():
                # Count only non-empty invalid lines
                invalid += 1
            continue
        reports.append(payload)

    return reports, invalid


def tail_jsonl(path: Path, n: int) -> list[dict[str, object]]:
    """
    Read and parse the last n JSONL entries from a file
    """
    reports, _ = tail_jsonl_with_stats(path, n)
    return reports
