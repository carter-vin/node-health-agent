"""
agent.logging

Structured JSON event emission to stdout.

Contract: one JSON object per line, stable event vocabulary (allowlist), UTC timestamps.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

# Event types
VALID_EVENT_TYPES = {
    "agent_start",
    "agent_tick",
    "agent_tick_metrics",
    "health_report_emitted",
    "collector_failed",
    "spool_write_failed",
    "spool_rotated",
    "agent_shutdown",
}


def _truncate_message(value: str, *, limit: int = 200) -> str:
    """Cap message length to keep events compact."""
    if len(value) <= limit:
        return value
    return value[:limit] + f"...[truncated {len(value) - limit} chars]"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit_event(event_type: str, *, agent_version: str, **fields: Any) -> None:
    """Emit a structured JSON event line to stdout. Raises ValueError for unknown event types."""
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"invalid event_type: {event_type}")

    if "message" in fields and isinstance(fields["message"], str):
        fields["message"] = _truncate_message(fields["message"])

    payload: dict[str, Any] = {
        "event_type": event_type,
        "utc_now": utc_now_iso(),
        "agent_version": agent_version,
        **fields,
    }

    print(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
