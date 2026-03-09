"""
Tests for operator-focused triage improvements:
- Fleet summary header in render_text and PrettyRenderer
- Explain renderer threshold profile context
- changes-only filter
- Demo fixture parsing
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from triage.cli import app
from triage.render.explain import ExplainRenderer
from triage.render.pretty import PrettyRenderer
from triage.summarize import NodeSummary, apply_filters, render_text, summarize_by_node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_summary(node_id: str, health: str, transitions: int = 0) -> NodeSummary:
    return NodeSummary(
        node_id=node_id,
        current_boot_id="boot-x",
        latest_seq=1,
        latest_emitted_at="2026-03-06T00:00:00+00:00",
        current_health=health,
        current_reasons=[],
        reports_seen_tail=2,
        degraded_count_tail=1 if health == "DEGRADED" else 0,
        unhealthy_count_tail=1 if health == "UNHEALTHY" else 0,
        top_reasons_tail=[],
        loadavg_1m=1.0,
        loadavg_5m=0.9,
        loadavg_15m=0.8,
        cpu_count_logical=4,
        mem_total_bytes=8589934592,
        mem_available_bytes=6442450944,
        disk_total_bytes=214748364800,
        disk_free_bytes=107374182400,
        health_transitions_tail=transitions,
    )


_BASE_META = {
    "tail_n": 50,
    "nodes_seen_tail": 3,
    "nodes_emitted": 3,
    "reports_parsed": 6,
    "reports_invalid": 0,
    "computed_at": "2026-03-06T00:00:00+00:00",
}


# ---------------------------------------------------------------------------
# Fleet summary header — render_text
# ---------------------------------------------------------------------------

def test_render_text_fleet_header_counts() -> None:
    summaries = [
        _make_summary("n1", "OK"),
        _make_summary("n2", "DEGRADED"),
        _make_summary("n3", "UNHEALTHY"),
    ]
    out = render_text(summaries, meta=_BASE_META)
    assert "fleet_ok: 1" in out
    assert "fleet_degraded: 1" in out
    assert "fleet_unhealthy: 1" in out


def test_render_text_fleet_header_all_ok() -> None:
    summaries = [_make_summary("n1", "OK"), _make_summary("n2", "OK")]
    meta = dict(_BASE_META, nodes_seen_tail=2, nodes_emitted=2)
    out = render_text(summaries, meta=meta)
    assert "fleet_ok: 2" in out
    assert "fleet_degraded: 0" in out
    assert "fleet_unhealthy: 0" in out


def test_render_text_fleet_header_empty() -> None:
    out = render_text([], meta={"nodes_seen_tail": 0})
    assert "fleet_ok: 0" in out
    assert "fleet_degraded: 0" in out
    assert "fleet_unhealthy: 0" in out


# ---------------------------------------------------------------------------
# Fleet summary header — PrettyRenderer
# ---------------------------------------------------------------------------

def test_pretty_renderer_fleet_header() -> None:
    summaries = [
        _make_summary("n1", "OK"),
        _make_summary("n2", "DEGRADED"),
    ]
    out = PrettyRenderer().render(summaries, meta=_BASE_META)
    assert "Fleet: 1 OK / 1 DEGRADED / 0 UNHEALTHY" in out


def test_pretty_renderer_fleet_header_appears_before_nodes() -> None:
    summaries = [_make_summary("n1", "OK")]
    out = PrettyRenderer().render(summaries, meta=_BASE_META)
    fleet_pos = out.index("Fleet:")
    node_pos = out.index("NODE n1")
    assert fleet_pos < node_pos


# ---------------------------------------------------------------------------
# Explain renderer — threshold profile context
# ---------------------------------------------------------------------------

def test_explain_renderer_default_profile() -> None:
    summaries = [_make_summary("n1", "OK")]
    out = ExplainRenderer().render(summaries, meta=_BASE_META)
    assert "Config: threshold_profile=default" in out


def test_explain_renderer_named_profile() -> None:
    summaries = [_make_summary("n1", "OK")]
    meta = dict(_BASE_META, threshold_profile="strict")
    out = ExplainRenderer().render(summaries, meta=meta)
    assert "Config: threshold_profile=strict" in out


def test_explain_renderer_config_appears_before_nodes() -> None:
    summaries = [_make_summary("n1", "OK")]
    out = ExplainRenderer().render(summaries, meta=_BASE_META)
    config_pos = out.index("Config:")
    node_pos = out.index("Node: n1")
    assert config_pos < node_pos


# ---------------------------------------------------------------------------
# changes-only filter
# ---------------------------------------------------------------------------

def test_changes_only_filters_stable_nodes() -> None:
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
            "--changes-only",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    # node-a has 2 transitions; node-b has 0 → only node-a passes
    nodes = payload["nodes"]
    assert all(n["health_transitions_tail"] > 0 for n in nodes)


def test_changes_only_returns_empty_when_none_transition() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "summarize",
            "--spool",
            str(Path("fixtures") / "spool_degraded.jsonl"),
            "--tail",
            "50",
            "--format",
            "json",
            "--changes-only",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["nodes"] == []


def test_changes_only_summarize_dir() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "summarize-dir",
            "--dir",
            "fixtures",
            "--glob",
            "demo_mixed.jsonl",
            "--tail",
            "50",
            "--format",
            "json",
            "--changes-only",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    # demo_mixed has 3 transitions
    assert len(payload["nodes"]) == 1
    assert payload["nodes"][0]["health_transitions_tail"] == 3


# ---------------------------------------------------------------------------
# Demo fixture parsing
# ---------------------------------------------------------------------------

def _load_fixture(name: str) -> list[dict]:
    from triage.read import tail_jsonl_with_stats
    reports, _ = tail_jsonl_with_stats(Path("fixtures") / name, 200)
    return reports


def test_demo_healthy_fixture_all_ok() -> None:
    reports = _load_fixture("demo_healthy.jsonl")
    summaries = summarize_by_node(reports)
    assert len(summaries) == 3
    assert all(s.current_health == "OK" for s in summaries)


def test_demo_degraded_fixture_all_degraded() -> None:
    reports = _load_fixture("demo_degraded.jsonl")
    summaries = summarize_by_node(reports)
    assert len(summaries) == 2
    assert all(s.current_health == "DEGRADED" for s in summaries)


def test_demo_mixed_fixture_transitions() -> None:
    reports = _load_fixture("demo_mixed.jsonl")
    summaries = summarize_by_node(reports)
    assert len(summaries) == 1
    assert summaries[0].health_transitions_tail == 3
    assert summaries[0].current_health == "OK"


def test_demo_reboot_fixture_boot_id_changes() -> None:
    reports = _load_fixture("demo_reboot.jsonl")
    summaries = summarize_by_node(reports)
    assert len(summaries) == 1
    # Latest boot_id wins
    assert summaries[0].current_boot_id == "boot-g2"
    assert summaries[0].node_id == "demo-node-g"


# ---------------------------------------------------------------------------
# apply_filters mutual exclusion
# ---------------------------------------------------------------------------

def test_apply_filters_mutual_exclusion_raises() -> None:
    summaries = [_make_summary("node-a", "DEGRADED")]
    with pytest.raises(ValueError, match="mutually exclusive"):
        apply_filters(
            summaries,
            node=None,
            only_degraded=True,
            only_unhealthy=True,
            min_degraded_count=None,
        )
