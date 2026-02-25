"""
Contract tests for `node-health-triage status` command.

Rules:
- Reads last valid report from tail (no heavy aggregation)
- Text output: deterministic single line with node_id, health, seq, emitted_at, reasons
- JSON output: single object with the same fields
- Exit code always 0 on success
- Missing spool → stderr error + exit 1
- No valid reports → stderr error + exit 1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from triage.cli import app

# Minimal valid report fixture
_REPORT = json.dumps({
    "assessment": {"health": "OK", "reasons": []},
    "identity": {"node_id": "test-node", "boot_id": "boot-abc"},
    "meta": {"agent_version": "0.1.0", "schema_version": "1"},
    "signals": {"heartbeat_ok": True},
    "timing": {"emitted_at": "2026-01-01T00:00:00+00:00", "seq": 7},
})

_REPORT_DEGRADED = json.dumps({
    "assessment": {"health": "DEGRADED", "reasons": ["collector_failed:heartbeat", "signal:mem_available_low"]},
    "identity": {"node_id": "test-node"},
    "meta": {"agent_version": "0.1.0", "schema_version": "1"},
    "signals": {},
    "timing": {"emitted_at": "2026-01-01T00:01:00+00:00", "seq": 8},
})


def test_status_text_format(tmp_path: Path) -> None:
    """
    Text output is a deterministic single line with required fields.
    """
    spool = tmp_path / "reports.jsonl"
    spool.write_text(_REPORT + "\n")

    runner = CliRunner()
    result = runner.invoke(app, ["status", "--spool", str(spool)])

    assert result.exit_code == 0
    assert "node_id=test-node" in result.output
    assert "health=OK" in result.output
    assert "seq=7" in result.output
    assert "emitted_at=2026-01-01T00:00:00+00:00" in result.output
    assert "reasons=none" in result.output


def test_status_text_format_with_reasons(tmp_path: Path) -> None:
    """
    Reasons are comma-joined in text output.
    """
    spool = tmp_path / "reports.jsonl"
    spool.write_text(_REPORT_DEGRADED + "\n")

    runner = CliRunner()
    result = runner.invoke(app, ["status", "--spool", str(spool)])

    assert result.exit_code == 0
    assert "health=DEGRADED" in result.output
    assert "reasons=collector_failed:heartbeat,signal:mem_available_low" in result.output


def test_status_json_format(tmp_path: Path) -> None:
    """
    JSON output is a parseable single object with the expected fields.
    """
    spool = tmp_path / "reports.jsonl"
    spool.write_text(_REPORT + "\n")

    runner = CliRunner()
    result = runner.invoke(app, ["status", "--spool", str(spool), "--format", "json"])

    assert result.exit_code == 0
    obj = json.loads(result.output.strip())
    assert obj["node_id"] == "test-node"
    assert obj["health"] == "OK"
    assert obj["seq"] == 7
    assert obj["emitted_at"] == "2026-01-01T00:00:00+00:00"
    assert obj["reasons"] == []


def test_status_returns_last_valid_report(tmp_path: Path) -> None:
    """
    Status reads the last valid report, not the first.
    """
    spool = tmp_path / "reports.jsonl"
    spool.write_text(_REPORT + "\n" + _REPORT_DEGRADED + "\n")

    runner = CliRunner()
    result = runner.invoke(app, ["status", "--spool", str(spool)])

    assert result.exit_code == 0
    assert "seq=8" in result.output
    assert "health=DEGRADED" in result.output


def test_status_missing_spool_exits_nonzero() -> None:
    """
    Missing spool file → error message and exit code 1.
    """
    runner = CliRunner()
    result = runner.invoke(app, ["status", "--spool", "/nonexistent/path.jsonl"])

    assert result.exit_code == 1
    assert "error" in result.output.lower()


def test_status_empty_spool_exits_nonzero(tmp_path: Path) -> None:
    """
    Spool with no valid reports → error message and exit code 1.
    """
    spool = tmp_path / "reports.jsonl"
    spool.write_text("")

    runner = CliRunner()
    result = runner.invoke(app, ["status", "--spool", str(spool)])

    assert result.exit_code == 1
    assert "error" in result.output.lower()


def test_status_exit_code_always_zero_for_degraded(tmp_path: Path) -> None:
    """
    Exit code is 0 even when health is DEGRADED (status, not filtering).
    """
    spool = tmp_path / "reports.jsonl"
    spool.write_text(_REPORT_DEGRADED + "\n")

    runner = CliRunner()
    result = runner.invoke(app, ["status", "--spool", str(spool)])

    assert result.exit_code == 0
