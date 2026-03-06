"""
Contract test for triage summarize-dir
"""

import json

import pytest
from typer.testing import CliRunner

from triage.cli import app
from triage.summarize import NodeSummary, detect_mixed_thresholds


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


def test_triage_summarize_dir_json_includes_thresholds_hash() -> None:
    """nodes in JSON output include thresholds_hash field."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["summarize-dir", "--dir", "fixtures", "--glob", "spool_node_*.jsonl",
         "--tail", "50", "--format", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    for node in payload["nodes"]:
        assert "thresholds_hash" in node


# ---------------------------------------------------------------------------
# detect_mixed_thresholds unit tests
# ---------------------------------------------------------------------------

def _make_summary(node_id: str, thresholds_hash: str = "") -> NodeSummary:
    return NodeSummary(
        node_id=node_id,
        current_boot_id="boot-x",
        latest_seq=1,
        latest_emitted_at="2026-01-01T00:00:00+00:00",
        current_health="OK",
        current_reasons=[],
        reports_seen_tail=1,
        degraded_count_tail=0,
        unhealthy_count_tail=0,
        top_reasons_tail=[],
        loadavg_1m=None,
        loadavg_5m=None,
        loadavg_15m=None,
        cpu_count_logical=None,
        mem_total_bytes=None,
        mem_available_bytes=None,
        disk_total_bytes=None,
        disk_free_bytes=None,
        thresholds_hash=thresholds_hash,
    )


def test_detect_mixed_thresholds_all_same() -> None:
    summaries = [_make_summary("node-a", "abc123"), _make_summary("node-b", "abc123")]
    mixed, hashes = detect_mixed_thresholds(summaries)
    assert not mixed
    assert hashes == ["abc123"]


def test_detect_mixed_thresholds_different_hashes() -> None:
    summaries = [_make_summary("node-a", "aaa"), _make_summary("node-b", "bbb")]
    mixed, hashes = detect_mixed_thresholds(summaries)
    assert mixed
    assert hashes == ["aaa", "bbb"]


def test_detect_mixed_thresholds_all_empty() -> None:
    summaries = [_make_summary("node-a", ""), _make_summary("node-b", "")]
    mixed, hashes = detect_mixed_thresholds(summaries)
    assert not mixed
    assert hashes == []


def test_warn_mixed_thresholds_cli_no_mix(tmp_path) -> None:
    """--warn-mixed-thresholds with uniform hashes produces no warning."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["summarize-dir", "--dir", "fixtures", "--glob", "spool_node_*.jsonl",
         "--tail", "50", "--format", "text", "--warn-mixed-thresholds"],
    )
    assert result.exit_code == 0
    assert "WARNING" not in result.output


def test_warn_mixed_thresholds_cli_json_meta(tmp_path) -> None:
    """--warn-mixed-thresholds injects mixed_thresholds into JSON meta."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["summarize-dir", "--dir", "fixtures", "--glob", "spool_node_*.jsonl",
         "--tail", "50", "--format", "json", "--warn-mixed-thresholds"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "mixed_thresholds" in payload["meta"]
    assert "thresholds_hashes_seen" in payload["meta"]


def test_warn_mixed_thresholds_warning_text(tmp_path) -> None:
    """--warn-mixed-thresholds with genuinely different hashes emits WARNING."""
    import json as _json

    # Build two spool files with different thresholds_hash values
    report_a = {
        "assessment": {"health": "OK", "reasons": []},
        "identity": {"node_id": "fleet-a", "boot_id": "boot-a"},
        "meta": {"agent_version": "0.1.0", "schema_version": "1",
                 "threshold_profile": "default", "thresholds_hash": "aaaa1111"},
        "signals": {},
        "timing": {"emitted_at": "2026-01-01T00:00:00+00:00", "seq": 1},
    }
    report_b = {
        "assessment": {"health": "OK", "reasons": []},
        "identity": {"node_id": "fleet-b", "boot_id": "boot-b"},
        "meta": {"agent_version": "0.1.0", "schema_version": "1",
                 "threshold_profile": "custom", "thresholds_hash": "bbbb2222"},
        "signals": {},
        "timing": {"emitted_at": "2026-01-01T00:00:01+00:00", "seq": 1},
    }
    spool_a = tmp_path / "node_fleet_a.jsonl"
    spool_b = tmp_path / "node_fleet_b.jsonl"
    spool_a.write_text(_json.dumps(report_a) + "\n")
    spool_b.write_text(_json.dumps(report_b) + "\n")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["summarize-dir", "--dir", str(tmp_path), "--glob", "node_fleet_*.jsonl",
         "--tail", "50", "--format", "text", "--warn-mixed-thresholds"],
    )
    assert result.exit_code == 0
    assert "WARNING" in result.output
    assert "aaaa1111" in result.output
    assert "bbbb2222" in result.output


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
