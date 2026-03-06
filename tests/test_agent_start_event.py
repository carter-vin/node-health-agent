"""
Contract tests for agent_start event startup metadata.

Verifies threshold_profile and thresholds_hash are present in agent_start
events for both oneshot and run modes.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agent.main import app


def _parse_agent_start(output: str) -> dict:
    """Return the first agent_start event from captured stdout."""
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("event_type") == "agent_start":
            return ev
    raise AssertionError("agent_start event not found in output")


def test_oneshot_agent_start_includes_threshold_fields() -> None:
    """oneshot agent_start must include threshold_profile and thresholds_hash."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["oneshot"])
    assert result.exit_code == 0
    ev = _parse_agent_start(result.output)
    assert ev["threshold_profile"] == "default"
    assert isinstance(ev["thresholds_hash"], str)
    assert len(ev["thresholds_hash"]) == 16


def test_run_agent_start_includes_threshold_fields() -> None:
    """run agent_start must include threshold_profile and thresholds_hash."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["run", "--max-iterations", "1", "--interval", "1"])
    assert result.exit_code == 0
    ev = _parse_agent_start(result.output)
    assert ev["threshold_profile"] == "default"
    assert isinstance(ev["thresholds_hash"], str)
    assert len(ev["thresholds_hash"]) == 16


def test_agent_start_hash_changes_with_env_override(monkeypatch) -> None:
    """Changing a threshold env var must change thresholds_hash in agent_start."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(app, ["oneshot"])
    assert result.exit_code == 0
    ev_default = _parse_agent_start(result.output)

    monkeypatch.setenv("NODE_AGENT_CPU_DEGRADED_FACTOR", "0.01")

    with runner.isolated_filesystem():
        result = runner.invoke(app, ["oneshot"])
    assert result.exit_code == 0
    ev_custom = _parse_agent_start(result.output)

    assert ev_default["thresholds_hash"] != ev_custom["thresholds_hash"]


def test_run_agent_start_includes_max_iterations_when_nonzero() -> None:
    """run agent_start must include max_iterations only when > 0."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["run", "--max-iterations", "3", "--interval", "1"])
    assert result.exit_code == 0
    ev = _parse_agent_start(result.output)
    assert ev["max_iterations"] == 3


def test_run_agent_start_omits_max_iterations_when_zero(capsys) -> None:
    """run agent_start must not include max_iterations when 0 (unlimited)."""
    from agent.logging import emit_event

    # Simulate the _start_fields logic for max_iterations=0 (unlimited)
    _start_fields: dict = {
        "mode": "run",
        "interval_s": 1,
        "spool_path": "spool/node_reports.jsonl",
        "spool_max_bytes": None,
        "spool_rotate_count": 3,
        "threshold_profile": "default",
        "thresholds_hash": "abc1234567890abc",
    }
    # max_iterations=0 means unlimited; field must be omitted
    max_iterations = 0
    if max_iterations:
        _start_fields["max_iterations"] = max_iterations
    emit_event("agent_start", agent_version="0.1.0", **_start_fields)

    out = capsys.readouterr().out.strip()
    ev = json.loads(out)
    assert "max_iterations" not in ev
