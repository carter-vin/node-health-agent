"""
Contract test for triage filters and exit codes
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from triage.cli import app


def test_triage_only_degraded_exit_code_and_output() -> None:
    """
    only-degraded filters nodes and returns exit code 2
    """
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "summarize",
            "--spool",
            str(Path("fixtures") / "spool_multi.jsonl"),
            "--tail",
            "50",
            "--format",
            "json",
            "--only-degraded",
        ],
    )

    assert result.exit_code == 2

    payload = json.loads(result.stdout)
    assert payload["meta"]["nodes_seen_tail"] == 2
    assert payload["meta"]["nodes_emitted"] == 1
    assert len(payload["nodes"]) == 1
    assert payload["nodes"][0]["node_id"] == "node-b"


def test_triage_only_unhealthy_exit_code_empty() -> None:
    """
    only-unhealthy returns exit code 0 when none match
    """
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "summarize",
            "--spool",
            str(Path("fixtures") / "spool_multi.jsonl"),
            "--tail",
            "50",
            "--format",
            "json",
            "--only-unhealthy",
        ],
    )

    assert result.exit_code == 0

    payload = json.loads(result.stdout)
    assert payload["meta"]["nodes_emitted"] == 0
    assert payload["nodes"] == []
