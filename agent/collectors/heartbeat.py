"""
agent.collectors.heartbeat

AUTHOR: carter-vin

- Always returns heartbeat_ok=True unless the process is in a known degraded state
- This is intentionally trivial; it exists to validate the collector→report pipeline

Future extension:
- include monotonic tick / loop timing stats
- include "last_emit_success" once emission pipeline exists
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HeartbeatResult:
    heartbeat_ok: bool


def collect_heartbeat() -> HeartbeatResult:
    """
    Return a simple heartbeat signal
    """
    return HeartbeatResult(heartbeat_ok=True)