"""
Contract tests for report schema stability.

These tests focus on fast, deterministic checks that ensure the report shape
stays stable as the code evolves. If these fail, downstream consumers may break.
"""

from agent.collectors.heartbeat import HeartbeatResult
from agent.collectors.identity import IdentityResult
from agent.model import SCHEMA_VERSION, build_report_from_collectors


def test_report_schema_keys_exist() -> None:
    """
    Ensure the top-level and nested schema keys remain stable.

    This guards the JSON envelope contract used by log shippers and triage.
    """
    ident = IdentityResult(node_id="test-node", boot_id="test-boot", source="test")
    hb = HeartbeatResult(heartbeat_ok=True)

    report = build_report_from_collectors(
        ident,
        hb,
        emitted_at="2026-01-01T00:00:00+00:00",
        seq=1,
        agent_version="0.1.0",
    )

    payload = report.to_dict()

    # Top-level envelope keys are contract-critical.
    assert set(payload.keys()) == {"identity", "timing", "signals", "assessment", "meta"}

    # Nested keys must be stable for downstream parsers.
    assert set(payload["identity"].keys()) == {"node_id", "boot_id"}
    assert set(payload["timing"].keys()) == {"emitted_at", "seq"}
    assert set(payload["assessment"].keys()) == {"health", "reasons"}
    assert set(payload["meta"].keys()) == {"schema_version", "agent_version"}

    # Schema version must match the constant.
    assert payload["meta"]["schema_version"] == SCHEMA_VERSION
