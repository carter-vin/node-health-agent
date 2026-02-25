"""
Contract tests for identity collector behavior.

Rules:
- node_id is always present (env override > hostname)
- boot_id is best-effort: omitted from report when unavailable
- No random IDs in normal mode (node_id comes from env or hostname)
"""

import json
import socket
from pathlib import Path

from typer.testing import CliRunner

from agent.main import app


def test_node_id_env_override() -> None:
    """
    NODE_AGENT_NODE_ID env override must take precedence over hostname.
    """
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            ["oneshot"],
            env={"NODE_AGENT_NODE_ID": "abc"},
        )

        assert result.exit_code == 0
        lines = (Path("spool") / "node_reports.jsonl").read_text().splitlines()
        report = json.loads(lines[-1])

        assert report["identity"]["node_id"] == "abc"


def test_node_id_defaults_to_hostname() -> None:
    """
    Without env override, node_id must equal socket.gethostname() — no random values.
    """
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(app, ["oneshot"])

        assert result.exit_code == 0
        lines = (Path("spool") / "node_reports.jsonl").read_text().splitlines()
        report = json.loads(lines[-1])

        assert report["identity"]["node_id"] == socket.gethostname()


def test_boot_id_absent_on_failure() -> None:
    """
    When NODE_AGENT_FAIL_IDENTITY=1 (boot_id unavailable):
    - report is still emitted (exit 0)
    - identity.boot_id key is absent from the report
    - assessment.reasons contains collector_failed:identity
    - health is DEGRADED
    """
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            ["oneshot"],
            env={"NODE_AGENT_FAIL_IDENTITY": "1"},
        )

        assert result.exit_code == 0
        lines = (Path("spool") / "node_reports.jsonl").read_text().splitlines()
        report = json.loads(lines[-1])

        assert "boot_id" not in report["identity"]
        assert "collector_failed:identity" in report["assessment"]["reasons"]
        assert report["assessment"]["health"] == "DEGRADED"


def test_node_id_present_even_on_identity_failure() -> None:
    """
    node_id must still be resolved when boot_id acquisition fails.
    """
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            ["oneshot"],
            env={"NODE_AGENT_NODE_ID": "test-node", "NODE_AGENT_FAIL_IDENTITY": "1"},
        )

        assert result.exit_code == 0
        lines = (Path("spool") / "node_reports.jsonl").read_text().splitlines()
        report = json.loads(lines[-1])

        assert report["identity"]["node_id"] == "test-node"
