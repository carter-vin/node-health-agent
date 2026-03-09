"""
agent.runtime

Shared collector orchestration and report pipeline helpers.

Responsibilities:
- Execute all collectors (plain and timed variants)
- Classify non-identity collector failures into events and reasons
- Evaluate health, build report, and serialize to JSON
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from agent.collectors.base import CollectorOutcome, run_collector
from agent.collectors.cpu import collect_cpu
from agent.collectors.disk import collect_disk
from agent.collectors.heartbeat import collect_heartbeat
from agent.collectors.identity import IdentityResult, collect_identity
from agent.collectors.memory import collect_memory
from agent.collectors.network import collect_network
from agent.evaluate import evaluate_health
from agent.logging import emit_event, utc_now_iso
from agent.model import build_report_from_collectors, report_to_json


@dataclass(frozen=True)
class CollectorResults:
    ident: CollectorOutcome
    heartbeat: CollectorOutcome
    cpu: CollectorOutcome
    memory: CollectorOutcome
    disk: CollectorOutcome
    network: CollectorOutcome


def collect_all() -> CollectorResults:
    return CollectorResults(
        ident=run_collector("identity", collect_identity),
        heartbeat=run_collector("heartbeat", collect_heartbeat),
        cpu=run_collector("cpu", collect_cpu),
        memory=run_collector("memory", collect_memory),
        disk=run_collector("disk", collect_disk),
        network=run_collector("network", collect_network),
    )


def collect_all_timed() -> tuple[CollectorResults, dict[str, int]]:
    """Returns (results, per-collector duration in ms)."""
    timings: dict[str, int] = {}
    named: dict[str, CollectorOutcome] = {}
    for name, fn in (
        ("identity", collect_identity),
        ("heartbeat", collect_heartbeat),
        ("cpu", collect_cpu),
        ("memory", collect_memory),
        ("disk", collect_disk),
        ("network", collect_network),
    ):
        t0 = time.monotonic()
        named[name] = run_collector(name, fn)
        timings[name] = int((time.monotonic() - t0) * 1000)
    return CollectorResults(
        ident=named["identity"],
        heartbeat=named["heartbeat"],
        cpu=named["cpu"],
        memory=named["memory"],
        disk=named["disk"],
        network=named["network"],
    ), timings


# Collectors that contribute failure reasons (network is best-effort, identity is mode-specific).
_REASON_COLLECTORS = (
    ("heartbeat", "heartbeat"),
    ("cpu", "cpu"),
    ("memory", "memory"),
    ("disk", "disk"),
)


def emit_failure_events(
    mode: str,
    results: CollectorResults,
    *,
    agent_version: str,
) -> list[str]:
    """
    Emit collector_failed events for heartbeat/cpu/memory/disk failures.

    Returns a list of failure reasons. Network and identity are intentionally
    excluded: network is best-effort (caller decides whether to emit an event);
    identity failure semantics differ between oneshot and run.
    """
    reasons: list[str] = []
    for attr, collector_name in _REASON_COLLECTORS:
        out: CollectorOutcome = getattr(results, attr)
        if not out.ok:
            emit_event(
                "collector_failed",
                agent_version=agent_version,
                mode=mode,
                collector=collector_name,
                error_type=out.error_type,
                message=out.error_message,
            )
            reasons.append(f"collector_failed:{collector_name}")
    return reasons


def build_report_json(
    ident: IdentityResult,
    seq: int,
    results: CollectorResults,
    reasons: list[str],
    *,
    cfg: dict[str, Any],
    cfg_profile: str,
    cfg_hash: str,
    agent_version: str,
) -> str:
    """Evaluate health, assemble report, and return serialized JSON."""
    health, eval_reasons = evaluate_health(
        results.cpu.value if results.cpu.ok else None,
        results.memory.value if results.memory.ok else None,
        results.disk.value if results.disk.ok else None,
        reasons,
        config=cfg,
    )
    report = build_report_from_collectors(
        ident,
        emitted_at=utc_now_iso(),
        seq=seq,
        agent_version=agent_version,
        heartbeat=results.heartbeat.value if results.heartbeat.ok else None,
        cpu=results.cpu.value if results.cpu.ok else None,
        memory=results.memory.value if results.memory.ok else None,
        disk=results.disk.value if results.disk.ok else None,
        network=results.network.value if results.network.ok else None,
        health=health,
        reasons=eval_reasons,
        threshold_profile=cfg_profile,
        thresholds_hash=cfg_hash,
    )
    return report_to_json(report)
