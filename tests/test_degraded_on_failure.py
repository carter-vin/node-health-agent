"""
Contract test for degraded assessment behavior on collector failure.

This test mirrors the intended policy: a heartbeat failure marks the report
as DEGRADED and records a deterministic reason string.
"""

from agent.collectors.heartbeat import HeartbeatResult
from agent.collectors.identity import IdentityResult
from agent.model import build_report_from_collectors


def test_heartbeat_failure_yields_degraded_reason() -> None:
    """
    Heartbeat failure should set health to DEGRADED and add the reason tag.
    """
    ident = IdentityResult(node_id="test-node", boot_id="test-boot", source="test")
    hb = HeartbeatResult(heartbeat_ok=False)

    report = build_report_from_collectors(
        ident,
        hb,
        emitted_at="2026-01-01T00:00:00+00:00",
        seq=1,
        agent_version="0.1.0",
        health="DEGRADED",
        reasons=["collector_failed:heartbeat"],
    )

    payload = report.to_dict()

    assert payload["assessment"]["health"] == "DEGRADED"
    assert payload["assessment"]["reasons"] == ["collector_failed:heartbeat"]
    assert payload["signals"]["heartbeat_ok"] is False
