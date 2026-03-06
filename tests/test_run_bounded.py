"""
Tests for run --max-iterations bounded mode.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agent.main import app


def _parse_events(output: str) -> list[dict]:
    events = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


def test_run_max_iterations_spool_line_count() -> None:
    """run --max-iterations N writes exactly N reports to spool."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["run", "--max-iterations", "3", "--interval", "1"])
        assert result.exit_code == 0
        spool = Path("spool") / "node_reports.jsonl"
        lines = [l for l in spool.read_text().splitlines() if l.strip()]
        assert len(lines) == 3


def test_run_max_iterations_1() -> None:
    """run --max-iterations 1 emits exactly 1 report."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["run", "--max-iterations", "1", "--interval", "1"])
        assert result.exit_code == 0
        spool = Path("spool") / "node_reports.jsonl"
        lines = [l for l in spool.read_text().splitlines() if l.strip()]
        assert len(lines) == 1


def test_run_max_iterations_event_sequence() -> None:
    """run --max-iterations N emits agent_start, N health_report_emitted, agent_shutdown."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["run", "--max-iterations", "2", "--interval", "1"])
    assert result.exit_code == 0
    events = _parse_events(result.output)
    types = [e["event_type"] for e in events]

    assert types[0] == "agent_start"
    assert types[-1] == "agent_shutdown"
    emitted = [e for e in events if e["event_type"] == "health_report_emitted"]
    assert len(emitted) == 2


def test_run_max_iterations_in_agent_start_event() -> None:
    """run --max-iterations N includes max_iterations in agent_start event."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["run", "--max-iterations", "2", "--interval", "1"])
    assert result.exit_code == 0
    events = _parse_events(result.output)
    start = next(e for e in events if e["event_type"] == "agent_start")
    assert start["max_iterations"] == 2


def test_run_max_iterations_reports_have_sequential_seq() -> None:
    """Reports emitted in bounded run have monotonically increasing seq numbers."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["run", "--max-iterations", "3", "--interval", "1"])
        assert result.exit_code == 0
        spool = Path("spool") / "node_reports.jsonl"
        reports = [json.loads(l) for l in spool.read_text().splitlines() if l.strip()]

    seqs = [r["timing"]["seq"] for r in reports]
    assert seqs == sorted(seqs)
    assert seqs == list(range(seqs[0], seqs[0] + 3))
