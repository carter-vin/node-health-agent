"""
agent.model
AUTHOR: carter-vin

Report schema + deterministic serialization primitives.

Design goals:
- Versioned, stable report envelope ("schema_version" = "1")
- Explicit structure (no accidental serialization via __dict__)
- Deterministic ordering where it matters (reasons list, keys)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import json

from agent.collectors.cpu import CpuResult
from agent.collectors.disk import DiskResult
from agent.collectors.heartbeat import HeartbeatResult
from agent.collectors.identity import IdentityResult
from agent.collectors.memory import MemoryResult

# Schema constants
SCHEMA_VERSION = "1"


# Components
@dataclass(frozen=True)
class Identity:
    """
    Tie report to specific node and boot
    - node_id: stable host identifier
    - boot_id: change on boot
    """

    node_id: str
    boot_id: str

    def to_dict(self) -> dict[str, Any]:
        # Explicit key mapping for stability
        return {
            "node_id": self.node_id,
            "boot_id": self.boot_id,
        }


@dataclass(frozen=True)
class Timing:
    """
    Timing for order & ingest
    - emitted_at: timestamp (UTC, string)
    - seq: counter per boot_id
    """

    # time in ISO 8601
    emitted_at: str
    seq: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "emitted_at": self.emitted_at,
            "seq": self.seq,
        }


@dataclass(frozen=True)
class Assessment:
    """
    Health assessment (high-level)
    - health: "OK" | "DEGRADED" | "UNHEALTHY"
    - reasons: deterministic -> stable ordering
    """

    health: str
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        # Enforce sorting for `reasons` to keep outputs stable
        return {
            "health": self.health,
            "reasons": sorted(self.reasons),
        }


@dataclass(frozen=True)
class Meta:
    """
    Metadata for versioning & traceability
    - schema_version: report schema version -> used for validate compatibility
    - agent_version: version string (later possible git sha)
    """

    schema_version: str
    agent_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "agent_version": self.agent_version,
        }


@dataclass(frozen=True)
class HealthReport:
    """
    Top-level report
    Designed to remain stable as signals expand
    """

    identity: Identity
    timing: Timing
    signals: dict[str, Any]
    assessment: Assessment
    meta: Meta

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to dict

        - keys exactly as defined
        - child blocks nested & versioned via meta.schema_version
        """
        return {
            "identity": self.identity.to_dict(),
            "timing": self.timing.to_dict(),
            "signals": dict(self.signals),  # Shallow copy for safety
            "assessment": self.assessment.to_dict(),
            "meta": self.meta.to_dict(),
        }


# -----------------------------
# Phase 1A: Helper
# -----------------------------
def utc_now_iso() -> str:
    """
    Current time in ISO 8601 (UTC)
    """
    return datetime.now(timezone.utc).isoformat()


def report_to_json(report: HealthReport) -> str:
    """
    Serialize a HealthReport

    Rules:
    - sort_keys=True ensures stable key order
    - separators remove whitespace to avoid formatting drift
    - ensure_ascii=False keeps UTF-8 readable if any future fields include it

    Output single JSON object string
    """
    payload = report.to_dict()

    # Stabilize key order in nested dicts
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


# Set valid response check
VALID_HEALTH = {"OK", "DEGRADED", "UNHEALTHY"}


def validate_report(report: HealthReport) -> None:
    """
    Validate report structure + content

    Raises ValueError on invalid

    (FUTURE: possible to downgrade failures to "collector_failed" reasons?)
    """
    # Identity checks
    if not report.identity.node_id:
        raise ValueError("identity.node_id is empty")
    if not report.identity.boot_id:
        raise ValueError("identity.boot_id is empty")

    # Timing checks
    if report.timing.seq < 1:
        raise ValueError("timing.seq must be >= 1")
    if not report.timing.emitted_at:
        raise ValueError("timing.emitted_at is empty")

    # Assessment checks
    if report.assessment.health not in VALID_HEALTH:
        raise ValueError(f"assessment.health must be: {sorted(VALID_HEALTH)}")

    # Meta checks
    if report.meta.schema_version != SCHEMA_VERSION:
        raise ValueError(f"meta.schema_version must be: '{SCHEMA_VERSION}'")
    if not report.meta.agent_version:
        raise ValueError("meta.agent_version must be non-empty")

    # Signals should always be a dict
    if not isinstance(report.signals, dict):
        raise ValueError("signals must be a dict")


def demo_report_json() -> str:
    """
    Generate a deterministic demo report JSON string.

    This is a testing harness, not production behavior:
    - emitted_at is fixed so output is stable for smoke tests and fixtures
    - identity uses fixed values

    Use this to prove schema + serialization without having collectors built yet.
    """
    report = HealthReport(
        identity=Identity(node_id="demo-node", boot_id="demo-boot"),
        timing=Timing(emitted_at="2026-01-01T00:00:00+00:00", seq=1),
        signals={
            # Minimal placeholder signals
            "heartbeat_ok": True,
        },
        assessment=Assessment(
            health="OK",
            reasons=[],
        ),
        meta=Meta(schema_version=SCHEMA_VERSION, agent_version="0.1.0"),
    )

    # Never serialize invalid objects
    validate_report(report)
    return report_to_json(report)


def build_report_from_collectors(
    identity: IdentityResult,
    *,
    emitted_at: str,
    seq: int,
    agent_version: str,
    heartbeat: HeartbeatResult | None = None,
    cpu: CpuResult | None = None,
    memory: MemoryResult | None = None,
    disk: DiskResult | None = None,
    health: str = "OK",
    reasons: list[str] | None = None,
) -> HealthReport:
    """
    Assemble a HealthReport from collector results
    """
    if reasons is None:
        reasons = []

    signals: dict[str, Any] = {}

    if heartbeat is not None:
        signals["heartbeat_ok"] = heartbeat.heartbeat_ok

    if cpu is not None:
        if cpu.loadavg_1m is not None:
            signals["loadavg_1m"] = cpu.loadavg_1m
        if cpu.loadavg_5m is not None:
            signals["loadavg_5m"] = cpu.loadavg_5m
        if cpu.loadavg_15m is not None:
            signals["loadavg_15m"] = cpu.loadavg_15m
        if cpu.cpu_count_logical is not None:
            signals["cpu_count_logical"] = cpu.cpu_count_logical

    if memory is not None:
        if memory.mem_total_bytes is not None:
            signals["mem_total_bytes"] = memory.mem_total_bytes
        if memory.mem_available_bytes is not None:
            signals["mem_available_bytes"] = memory.mem_available_bytes

    if disk is not None:
        signals["disk_total_bytes"] = disk.disk_total_bytes
        signals["disk_used_bytes"] = disk.disk_used_bytes
        signals["disk_free_bytes"] = disk.disk_free_bytes

    report = HealthReport(
        identity=Identity(
            node_id=identity.node_id,
            boot_id=identity.boot_id,
        ),
        timing=Timing(
            emitted_at=emitted_at,
            seq=seq,
        ),
        signals=signals,
        assessment=Assessment(
            health=health,
            reasons=reasons,
        ),
        meta=Meta(
            schema_version=SCHEMA_VERSION,
            agent_version=agent_version,
        ),
    )

    # validate before returning
    validate_report(report)
    return report
