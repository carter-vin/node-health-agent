"""
triage.read
AUTHOR: carter-vin

JSONL reader utilities for triage
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import json


def read_jsonl(path: Path) -> Iterable[dict]:
    """
    Yield parsed JSON objects from a JSONL file
    """
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def tail_jsonl(path: Path, n: int) -> list[dict]:
    """
    Read and parse the last n JSONL entries from a file
    """
    if n <= 0:
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    tail = lines[-n:] if n < len(lines) else lines
    return [json.loads(line) for line in tail if line.strip()]
