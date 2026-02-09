"""
Contract test for degraded assessment behavior on collector failure
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from agent.main import app


def test_heartbeat_failure_yields_degraded_reason() -> None:
    """
    Heartbeat failure should set health to DEGRADED and add the reason tag
    """
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            ["oneshot"],
            env={"NODE_AGENT_FAIL_HEARTBEAT": "1"},
        )

        assert result.exit_code == 0

        lines = (Path("spool") / "node_reports.jsonl").read_text().splitlines()
        report = json.loads(lines[-1])

        assert report["assessment"]["health"] == "DEGRADED"
        assert "collector_failed:heartbeat" in report["assessment"]["reasons"]
