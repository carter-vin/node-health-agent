"""
Contract tests for agent.config threshold configuration.

Rules:
- Precedence: defaults < JSON file < env vars
- compute_config_hash is stable across key orderings
- evaluate_health uses configured thresholds
- report meta includes threshold_profile and thresholds_hash
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent.collectors.cpu import CpuResult
from agent.collectors.disk import DiskResult
from agent.collectors.memory import MemoryResult
from agent.config import compute_config_hash, load_config, normalize_config
from agent.evaluate import evaluate_health
from agent.main import app


# ---------------------------------------------------------------------------
# normalize_config
# ---------------------------------------------------------------------------

def test_normalize_config_fills_defaults() -> None:
    """Empty input yields full default config."""
    cfg = normalize_config({})
    assert cfg["cpu"]["degraded_factor"] == 0.85
    assert cfg["cpu"]["unhealthy_factor"] == 1.25
    assert cfg["mem"]["degraded_pct"] == 15.0
    assert cfg["mem"]["unhealthy_pct"] == 8.0
    assert cfg["disk"]["degraded_pct"] == 10.0
    assert cfg["disk"]["unhealthy_pct"] == 5.0
    assert cfg["evaluation"]["profile_name"] == "default"


def test_normalize_config_merges_partial_overrides() -> None:
    """Partial section override leaves other keys at defaults."""
    cfg = normalize_config({"cpu": {"degraded_factor": 0.5}})
    assert cfg["cpu"]["degraded_factor"] == 0.5
    assert cfg["cpu"]["unhealthy_factor"] == 1.25  # default preserved


# ---------------------------------------------------------------------------
# compute_config_hash
# ---------------------------------------------------------------------------

def test_config_hash_stable_across_key_orderings() -> None:
    """Hash must not change when dict key order differs."""
    cfg_a = {"cpu": {"degraded_factor": 0.5, "unhealthy_factor": 1.0}}
    cfg_b = {"cpu": {"unhealthy_factor": 1.0, "degraded_factor": 0.5}}
    assert compute_config_hash(cfg_a) == compute_config_hash(cfg_b)


def test_config_hash_changes_when_values_change() -> None:
    """Different thresholds must produce different hashes."""
    cfg_default = load_config()
    cfg_custom = load_config()
    cfg_custom["cpu"]["degraded_factor"] = 0.01
    assert compute_config_hash(cfg_default) != compute_config_hash(cfg_custom)


def test_config_hash_is_16_hex_chars() -> None:
    """Hash is a 16-character hex string."""
    h = compute_config_hash(load_config())
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# load_config — precedence
# ---------------------------------------------------------------------------

def test_load_config_defaults_when_no_args() -> None:
    """load_config() with no args returns default values."""
    cfg = load_config()
    assert cfg["cpu"]["degraded_factor"] == 0.85


def test_load_config_file_overrides_defaults(tmp_path: Path) -> None:
    """JSON file values override defaults."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"cpu": {"degraded_factor": 0.3}}))

    cfg = load_config(str(config_file))
    assert cfg["cpu"]["degraded_factor"] == 0.3
    assert cfg["cpu"]["unhealthy_factor"] == 1.25  # default preserved


def test_load_config_env_overrides_file(tmp_path: Path, monkeypatch) -> None:
    """Env vars override JSON file values."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"cpu": {"degraded_factor": 0.3}}))
    monkeypatch.setenv("NODE_AGENT_CPU_DEGRADED_FACTOR", "0.1")

    cfg = load_config(str(config_file))
    assert cfg["cpu"]["degraded_factor"] == 0.1


def test_load_config_env_overrides_defaults(monkeypatch) -> None:
    """Env vars override defaults even without a config file."""
    monkeypatch.setenv("NODE_AGENT_MEM_DEGRADED_PCT", "25.0")
    cfg = load_config()
    assert cfg["mem"]["degraded_pct"] == 25.0


def test_load_config_invalid_file_falls_back_to_defaults(tmp_path: Path) -> None:
    """Invalid JSON config file falls back to defaults without error."""
    config_file = tmp_path / "bad.json"
    config_file.write_text("not json {{")

    cfg = load_config(str(config_file))
    assert cfg["cpu"]["degraded_factor"] == 0.85


def test_load_config_missing_file_falls_back_to_defaults() -> None:
    """Missing config file falls back to defaults without error."""
    cfg = load_config("/nonexistent/path/config.json")
    assert cfg["cpu"]["degraded_factor"] == 0.85


# ---------------------------------------------------------------------------
# evaluate_health uses configured thresholds
# ---------------------------------------------------------------------------

def test_evaluate_health_uses_custom_cpu_threshold() -> None:
    """
    With a very low CPU degraded_factor, even a tiny load triggers DEGRADED.
    With the default factor the same load would be OK.
    """
    cpu = CpuResult(loadavg_1m=0.1, loadavg_5m=None, loadavg_15m=None, cpu_count_logical=8)

    health_default, _ = evaluate_health(cpu, None, None, [])
    assert health_default == "OK"

    cfg = load_config()
    cfg["cpu"]["degraded_factor"] = 0.001  # 0.001 × 8 = 0.008 threshold
    health_custom, reasons_custom = evaluate_health(cpu, None, None, [], config=cfg)
    assert health_custom == "DEGRADED"
    assert "signal:cpu_high" in reasons_custom


def test_evaluate_health_uses_custom_disk_threshold() -> None:
    """
    With a raised disk_unhealthy_pct, a disk at 6% free triggers UNHEALTHY
    (default threshold is 5%).
    """
    disk = DiskResult(disk_total_bytes=100, disk_used_bytes=94, disk_free_bytes=6)

    health_default, _ = evaluate_health(None, None, disk, [])
    assert health_default == "DEGRADED"  # 6% free: above 5% unhealthy, below 10% degraded

    cfg = load_config()
    cfg["disk"]["unhealthy_pct"] = 8.0  # raise threshold: 6% < 8% → UNHEALTHY
    health_custom, reasons = evaluate_health(None, None, disk, [], config=cfg)
    assert health_custom == "UNHEALTHY"
    assert "signal:disk_free_critical" in reasons


# ---------------------------------------------------------------------------
# report meta includes threshold_profile and thresholds_hash
# ---------------------------------------------------------------------------

def test_report_meta_includes_threshold_fields() -> None:
    """
    Emitted reports must include threshold_profile and thresholds_hash in meta.
    """
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(app, ["oneshot"])
        assert result.exit_code == 0

        lines = (Path("spool") / "node_reports.jsonl").read_text().splitlines()
        report = json.loads(lines[-1])

        assert "threshold_profile" in report["meta"]
        assert "thresholds_hash" in report["meta"]
        assert report["meta"]["threshold_profile"] == "default"
        assert len(report["meta"]["thresholds_hash"]) == 16


def test_report_meta_hash_changes_with_env_override(monkeypatch) -> None:
    """
    Changing a threshold via env var must change the thresholds_hash in the report.
    """
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(app, ["oneshot"])
        assert result.exit_code == 0
        report_default = json.loads(
            (Path("spool") / "node_reports.jsonl").read_text().splitlines()[-1]
        )

    monkeypatch.setenv("NODE_AGENT_CPU_DEGRADED_FACTOR", "0.01")

    with runner.isolated_filesystem():
        result = runner.invoke(app, ["oneshot"])
        assert result.exit_code == 0
        report_custom = json.loads(
            (Path("spool") / "node_reports.jsonl").read_text().splitlines()[-1]
        )

    assert report_default["meta"]["thresholds_hash"] != report_custom["meta"]["thresholds_hash"]
