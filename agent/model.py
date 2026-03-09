"""
agent.model

Report schema and deterministic serialization.

Schema version "1". Deterministic key ordering via sort_keys=True.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import json

from agent.collectors.cpu import CpuResult
from agent.collectors.disk import DiskResult
from agent.collectors.heartbeat import HeartbeatResult
from agent.collectors.identity import IdentityResult
from agent.collectors.memory import MemoryResult
from agent.collectors.network import NetworkResult

# Schema constants
SCHEMA_VERSION = "1"


# Components
@dataclass(frozen=True)
class Identity:
    node_id: str
    boot_id: str | None  # None when boot_id unavailable

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"node_id": self.node_id}
        if self.boot_id is not None:
            d["boot_id"] = self.boot_id
        return d


@dataclass(frozen=True)
class Timing:
    emitted_at: str
    seq: int

    def to_dict(self) -> dict[str, Any]:
        return {"emitted_at": self.emitted_at, "seq": self.seq}


@dataclass(frozen=True)
class Assessment:
    health: str
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"health": self.health, "reasons": sorted(self.reasons)}


@dataclass(frozen=True)
class Meta:
    schema_version: str
    agent_version: str
    threshold_profile: str = "default"
    thresholds_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_version": self.agent_version,
            "schema_version": self.schema_version,
            "threshold_profile": self.threshold_profile,
            "thresholds_hash": self.thresholds_hash,
        }


@dataclass(frozen=True)
class HealthReport:
    identity: Identity
    timing: Timing
    signals: dict[str, Any]
    assessment: Assessment
    meta: Meta

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "timing": self.timing.to_dict(),
            "signals": dict(self.signals),
            "assessment": self.assessment.to_dict(),
            "meta": self.meta.to_dict(),
        }


def report_to_json(report: HealthReport) -> str:
    """Serialize a HealthReport to compact, deterministic JSON."""
    return json.dumps(
        report.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


VALID_HEALTH = {"OK", "DEGRADED", "UNHEALTHY"}


def validate_report(report: HealthReport) -> None:
    """Raise ValueError if the report violates structural contracts."""
    if not report.identity.node_id:
        raise ValueError("identity.node_id is empty")
    # boot_id is best-effort; None is valid (caller adds collector_failed:identity reason)
    if report.timing.seq < 1:
        raise ValueError("timing.seq must be >= 1")
    if not report.timing.emitted_at:
        raise ValueError("timing.emitted_at is empty")
    if report.assessment.health not in VALID_HEALTH:
        raise ValueError(f"assessment.health must be: {sorted(VALID_HEALTH)}")
    if report.meta.schema_version != SCHEMA_VERSION:
        raise ValueError(f"meta.schema_version must be: '{SCHEMA_VERSION}'")
    if not report.meta.agent_version:
        raise ValueError("meta.agent_version must be non-empty")
    if not isinstance(report.signals, dict):
        raise ValueError("signals must be a dict")


def demo_report_json() -> str:
    """Return a fixed-identity, fixed-timestamp report JSON for smoke tests."""
    report = HealthReport(
        identity=Identity(node_id="demo-node", boot_id="demo-boot"),
        timing=Timing(emitted_at="2026-01-01T00:00:00+00:00", seq=1),
        signals={"heartbeat_ok": True},
        assessment=Assessment(health="OK", reasons=[]),
        meta=Meta(schema_version=SCHEMA_VERSION, agent_version="0.1.0"),
    )
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
    network: NetworkResult | None = None,
    health: str = "OK",
    reasons: list[str] | None = None,
    threshold_profile: str = "default",
    thresholds_hash: str = "",
) -> HealthReport:
    """Assemble a HealthReport from collector results and validate before returning."""
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

    if network is not None:
        if network.net_rx_bytes_total is not None:
            signals["net_rx_bytes_total"] = network.net_rx_bytes_total
        if network.net_tx_bytes_total is not None:
            signals["net_tx_bytes_total"] = network.net_tx_bytes_total
        if network.net_active_tcp_connections is not None:
            signals["net_active_tcp_connections"] = network.net_active_tcp_connections

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
            threshold_profile=threshold_profile,
            thresholds_hash=thresholds_hash,
        ),
    )

    # validate before returning
    validate_report(report)
    return report
