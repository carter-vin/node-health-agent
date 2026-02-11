"""
agent.logging
AUTHOR: carter-vin

Structured JSON event logging for ops ingestion

Contract:
- One JSON object per line to stdout
- Stable event vocabulary (allowlist)
- UTC timestamps only
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

# Event types
VALID_EVENT_TYPES = {
    "agent_start",
    "agent_tick",
    "health_report_emitted",
    "collector_failed",
    "spool_write_failed",
    "spool_rotated",
    "agent_shutdown",
}


def _truncate_message(value: str, *, limit: int = 200) -> str:
    """
    Cap message length to keep events compact
    """
    if len(value) <= limit:
        return value
    return value[:limit] + f"...[truncated {len(value) - limit} chars]"


# Time: current in UTC ISO 8601
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit_event(event_type: str, *, agent_version: str, **fields: Any) -> None:
    """
    Emit structured event line to stdout

    Rules:
    - event_type in VALID_EVENT_TYPES
    - event_type, agent_version, timestamp always present
    - sort_keys + compact separators for format
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"invalid event_type: {event_type}")

    if "message" in fields and isinstance(fields["message"], str):
        # Avoid emitting long strings in event fields
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
