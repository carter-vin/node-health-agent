"""
agent.collectors.heartbeat

Always returns heartbeat_ok=True. Exists to validate the collector→report
pipeline end-to-end. Raises on NODE_AGENT_FAIL_HEARTBEAT=1 (test hook).
"""

from __future__ import annotations
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class HeartbeatResult:
    heartbeat_ok: bool


def collect_heartbeat() -> HeartbeatResult:
    if os.environ.get("NODE_AGENT_FAIL_HEARTBEAT") == "1":
        raise RuntimeError("Simulated heartbeat failure")

    return HeartbeatResult(heartbeat_ok=True)
