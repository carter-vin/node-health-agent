"""
agent.collectors.base
AUTHOR: carter-vin

Light result wrapper -> prevent collector errors from crashing agent
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional, Protocol

@dataclass(frozen=True)
class CollectorOutcome:
    """
    Normalized collector result
    - ok: false=failure, error details in error field
    - value: collector result object if ok=true
    """

    name: str
    ok: bool
    value: Optional[Any] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None


def run_collector(name: str, fn, *args, **kwargs) -> CollectorOutcome:
    """
    Run collector & collect failure as data
    """
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

        