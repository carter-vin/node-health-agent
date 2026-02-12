"""
Contract test for triage summarize-dir
"""

import json

from typer.testing import CliRunner

from triage.cli import app


def test_triage_summarize_dir_json() -> None:
    """
    Summarize directory spools with deterministic JSON output
    """
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "summarize-dir",
            "--dir",
            "fixtures",
            "--glob",
            "spool_node_*.jsonl",
            "--tail",
            "50",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0

    payload = json.loads(result.stdout)

    assert payload["meta"]["spool_dir"] == "fixtures"
    assert payload["meta"]["files_seen"] == 2
    assert payload["meta"]["nodes_seen_tail"] == 2
    assert payload["meta"]["nodes_emitted"] == 2
    assert payload["meta"]["reports_parsed"] == 4
    assert payload["meta"]["reports_invalid_total"] == 1

    nodes = payload["nodes"]
    assert nodes[0]["node_id"] == "node-a"
    assert nodes[1]["node_id"] == "node-b"
    assert nodes[1]["current_health"] == "DEGRADED"


def test_triage_summarize_dir_rejects_multi_node_file() -> None:
    """
    summarize-dir rejects files with multiple node_id values
    """
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "summarize-dir",
            "--dir",
            "fixtures",
            "--glob",
            "spool_mixed.jsonl",
            "--tail",
            "50",
        ],
    )

    assert result.exit_code != 0
    assert "multiple node_id" in result.output
