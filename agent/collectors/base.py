"""
agent.collectors.base

Collector result wrapper. Prevents collector errors from crashing the agent.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CollectorOutcome:
    name: str
    ok: bool
    value: Any = None
    error_type: str | None = None
    error_message: str | None = None


def run_collector(name: str, fn, *args, **kwargs) -> CollectorOutcome:
    """Run a collector function, capturing any exception as a failed outcome."""
    try:
        v = fn(*args, **kwargs)
        return CollectorOutcome(name=name, ok=True, value=v, error_type=None, error_message=None)
    except Exception as e:
        return CollectorOutcome(
            name=name,
            ok=False,
            value=None,
            error_type=type(e).__name__,
            error_message=str(e),
        )
