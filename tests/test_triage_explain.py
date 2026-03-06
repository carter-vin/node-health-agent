"""
Tests for ExplainRenderer: config-awareness and no hardcoded threshold constants.
"""

from __future__ import annotations

from triage.render.explain import ExplainRenderer
from triage.summarize import NodeSummary


def _make_summary(
    node_id: str = "node-x",
    health: str = "OK",
    reasons: list[str] | None = None,
    threshold_profile: str = "default",
    thresholds_hash: str = "abc1234567890abc",
    loadavg_1m: float | None = None,
    cpu_count_logical: int | None = None,
) -> NodeSummary:
    return NodeSummary(
        node_id=node_id,
        current_boot_id="boot-1",
        latest_seq=1,
        latest_emitted_at="2026-01-01T00:00:01+00:00",
        current_health=health,
        current_reasons=reasons or [],
        reports_seen_tail=1,
        degraded_count_tail=0,
        unhealthy_count_tail=0,
        top_reasons_tail=[],
        loadavg_1m=loadavg_1m,
        loadavg_5m=None,
        loadavg_15m=None,
        cpu_count_logical=cpu_count_logical,
        mem_total_bytes=None,
        mem_available_bytes=None,
        disk_total_bytes=None,
        disk_free_bytes=None,
        threshold_profile=threshold_profile,
        thresholds_hash=thresholds_hash,
    )


_META = {"nodes_seen_tail": 1, "nodes_emitted": 1}


def test_explain_shows_threshold_profile_default() -> None:
    """Explain output includes threshold_profile from summary."""
    renderer = ExplainRenderer()
    summary = _make_summary(threshold_profile="default", thresholds_hash="deadbeef12345678")
    output = renderer.render([summary], meta=_META)
    assert "threshold_profile: default" in output
    assert "deadbeef12345678" in output


def test_explain_shows_non_default_threshold_profile() -> None:
    """Explain output shows non-default profile name."""
    renderer = ExplainRenderer()
    summary = _make_summary(threshold_profile="strict", thresholds_hash="1234567890abcdef")
    output = renderer.render([summary], meta=_META)
    assert "threshold_profile: strict" in output
    assert "1234567890abcdef" in output


def test_explain_states_exact_values_require_config_source() -> None:
    """Explain output must explicitly state that exact values require original config."""
    renderer = ExplainRenderer()
    summary = _make_summary()
    output = renderer.render([summary], meta=_META)
    assert "exact threshold values require original config source" in output


def test_explain_shows_unavailable_when_hash_empty() -> None:
    """Explain output shows '(unavailable)' when thresholds_hash is empty."""
    renderer = ExplainRenderer()
    summary = _make_summary(thresholds_hash="")
    output = renderer.render([summary], meta=_META)
    assert "(unavailable)" in output


def test_explain_no_hardcoded_threshold_values_in_cpu_reason() -> None:
    """CPU signal reasons show current load, not hardcoded threshold comparisons."""
    renderer = ExplainRenderer()
    summary = _make_summary(
        health="DEGRADED",
        reasons=["signal:cpu_high"],
        loadavg_1m=3.5,
        cpu_count_logical=4,
        threshold_profile="default",
        thresholds_hash="abc1234567890abc",
    )
    output = renderer.render([summary], meta=_META)
    # Must show the reason label
    assert "CPU load high" in output
    # Must show current load value, not a static threshold comparison like "> 3.40"
    assert "3.50" in output
    # Must NOT hardcode the threshold: 4 * 0.85 = 3.40
    assert "3.40" not in output


def test_explain_no_agent_evaluate_import() -> None:
    """ExplainRenderer must not import constants from agent.evaluate."""
    import ast
    import pathlib

    src = pathlib.Path("triage/render/explain.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", "") or ""
            assert "agent.evaluate" not in module, (
                "explain.py must not import from agent.evaluate"
            )
