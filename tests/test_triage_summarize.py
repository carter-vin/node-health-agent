"""
Contract test for deterministic triage summarization
"""

import json
from pathlib import Path

from triage.read import tail_jsonl_with_stats
from triage.summarize import render_json, render_text, summarize_by_node


# ---------------------------------------------------------------------------
# Rolling-window stat helpers
# ---------------------------------------------------------------------------

def _make_report(node_id: str, health: str, loadavg_1m=None,
                 mem_available=None, mem_total=None,
                 disk_free=None, disk_total=None, seq: int = 1) -> dict:
    signals: dict = {}
    if loadavg_1m is not None:
        signals["loadavg_1m"] = loadavg_1m
        signals["cpu_count_logical"] = 4
    if mem_available is not None:
        signals["mem_available_bytes"] = mem_available
        signals["mem_total_bytes"] = mem_total
    if disk_free is not None:
        signals["disk_free_bytes"] = disk_free
        signals["disk_total_bytes"] = disk_total
    return {
        "assessment": {"health": health, "reasons": []},
        "identity": {"node_id": node_id, "boot_id": "boot-x"},
        "meta": {"agent_version": "0.1.0", "schema_version": "1"},
        "signals": signals,
        "timing": {"emitted_at": f"2026-01-01T00:00:0{seq}+00:00", "seq": seq},
    }


def test_rolling_stats_cpu_max() -> None:
    """max_cpu1_tail is the maximum loadavg_1m across all records in the tail."""
    reports = [
        _make_report("node-x", "OK", loadavg_1m=2.0, seq=1),
        _make_report("node-x", "OK", loadavg_1m=4.5, seq=2),
        _make_report("node-x", "OK", loadavg_1m=3.1, seq=3),
    ]
    summaries = summarize_by_node(reports)
    assert summaries[0].max_cpu1_tail == 4.5


def test_rolling_stats_mem_min_pct() -> None:
    """min_mem_available_pct_tail is the minimum available% across records with memory signals."""
    reports = [
        _make_report("node-x", "OK", mem_available=800, mem_total=1000, seq=1),  # 80%
        _make_report("node-x", "OK", mem_available=600, mem_total=1000, seq=2),  # 60%
        _make_report("node-x", "OK", mem_available=700, mem_total=1000, seq=3),  # 70%
    ]
    summaries = summarize_by_node(reports)
    assert summaries[0].min_mem_available_pct_tail == 60.0


def test_rolling_stats_disk_min_pct() -> None:
    """min_disk_free_pct_tail is the minimum free% across records with disk signals."""
    reports = [
        _make_report("node-x", "OK", disk_free=900, disk_total=1000, seq=1),   # 90%
        _make_report("node-x", "OK", disk_free=700, disk_total=1000, seq=2),   # 70%
        _make_report("node-x", "OK", disk_free=800, disk_total=1000, seq=3),   # 80%
    ]
    summaries = summarize_by_node(reports)
    assert summaries[0].min_disk_free_pct_tail == 70.0


def test_rolling_stats_rounding_2_decimals() -> None:
    """Rolling stats are rounded to 2 decimal places."""
    reports = [
        _make_report("node-x", "OK", loadavg_1m=1.123456, seq=1),
        _make_report("node-x", "OK", loadavg_1m=2.987654, seq=2),
    ]
    summaries = summarize_by_node(reports)
    assert summaries[0].max_cpu1_tail == 2.99


def test_rolling_stats_none_when_no_signals() -> None:
    """All rolling signal stats are None when no records have those signals."""
    reports = [_make_report("node-x", "OK", seq=1)]
    summaries = summarize_by_node(reports)
    assert summaries[0].max_cpu1_tail is None
    assert summaries[0].min_mem_available_pct_tail is None
    assert summaries[0].min_disk_free_pct_tail is None


def test_health_transitions_count() -> None:
    """health_transitions_tail counts consecutive health-state changes."""
    reports = [
        _make_report("node-x", "OK", seq=1),
        _make_report("node-x", "DEGRADED", seq=2),
        _make_report("node-x", "UNHEALTHY", seq=3),
        _make_report("node-x", "OK", seq=4),
    ]
    summaries = summarize_by_node(reports)
    # OK→DEGRADED, DEGRADED→UNHEALTHY, UNHEALTHY→OK = 3
    assert summaries[0].health_transitions_tail == 3


def test_health_transitions_zero_when_stable() -> None:
    """health_transitions_tail is 0 when health never changes."""
    reports = [
        _make_report("node-x", "DEGRADED", seq=1),
        _make_report("node-x", "DEGRADED", seq=2),
        _make_report("node-x", "DEGRADED", seq=3),
    ]
    summaries = summarize_by_node(reports)
    assert summaries[0].health_transitions_tail == 0


def test_rolling_stats_appear_in_json_output() -> None:
    """Rolling stats are present in the JSON renderer output."""
    reports = [
        _make_report("node-x", "OK", loadavg_1m=1.5, seq=1),
        _make_report("node-x", "DEGRADED", seq=2),
    ]
    summaries = summarize_by_node(reports)
    meta = {"tail_n": 10, "nodes_seen_tail": 1, "nodes_emitted": 1,
            "reports_parsed": 2, "reports_invalid": 0, "computed_at": "2026-01-01T00:00:00+00:00"}
    payload = render_json(summaries, meta=meta)
    node = payload["nodes"][0]
    assert node["max_cpu1_tail"] == 1.5
    assert node["health_transitions_tail"] == 1


def test_triage_summarize_multi_node_text() -> None:
    """
    Summarize a fixed fixture and compare to expected text output
    """
    fixture_path = Path("fixtures") / "spool_multi.jsonl"
    reports, invalid_count = tail_jsonl_with_stats(fixture_path, 50)

    summaries = summarize_by_node(reports, top_k_reasons=5)
    meta = {
        "spool_path": str(fixture_path),
        "tail_n": 50,
        "nodes_seen_tail": len(summaries),
        "nodes_emitted": len(summaries),
        "reports_parsed": len(reports),
        "reports_invalid": invalid_count,
        "computed_at": "2026-01-02T00:00:00+00:00",
    }

    summary = render_text(summaries, meta=meta)

    expected = "\n".join(
        [
            "nodes_seen_tail: 2",
            "nodes_emitted: 2",
            "",
            "node_id: node-a",
            "current_boot_id: boot-1",
            "latest_health: OK",
            "latest_seq: 3",
            "latest_emitted_at: 2026-01-01T00:00:04+00:00",
            "degraded_count_tail: 1 / 3",
            "unhealthy_count_tail: 0 / 3",
            "top_reasons_tail: collector_failed:cpu:1, collector_failed:memory:1",
            "current_reasons: none",
            "max_cpu1_tail: n/a",
            "min_mem_available_pct_tail: n/a",
            "min_disk_free_pct_tail: n/a",
            "health_transitions_tail: 2",
            "",
            "node_id: node-b",
            "current_boot_id: boot-2",
            "latest_health: DEGRADED",
            "latest_seq: 2",
            "latest_emitted_at: 2026-01-01T00:00:03+00:00",
            "degraded_count_tail: 2 / 2",
            "unhealthy_count_tail: 0 / 2",
            "top_reasons_tail: collector_failed:disk:2, collector_failed:cpu:1",
            "current_reasons: collector_failed:cpu, collector_failed:disk",
            "max_cpu1_tail: n/a",
            "min_mem_available_pct_tail: n/a",
            "min_disk_free_pct_tail: n/a",
            "health_transitions_tail: 0",
        ]
    )

    assert summary == expected


def test_triage_summarize_multi_node_json() -> None:
    """
    Summarize a fixed fixture and compare to expected JSON payload
    """
    fixture_path = Path("fixtures") / "spool_multi.jsonl"
    reports, invalid_count = tail_jsonl_with_stats(fixture_path, 50)

    summaries = summarize_by_node(reports, top_k_reasons=5)
    meta = {
        "spool_path": str(fixture_path),
        "tail_n": 50,
        "nodes_seen_tail": len(summaries),
        "nodes_emitted": len(summaries),
        "reports_parsed": len(reports),
        "reports_invalid": invalid_count,
        "computed_at": "2026-01-02T00:00:00+00:00",
    }

    payload = render_json(summaries, meta=meta)

    expected = {
        "meta": {
            "schema_version": "1",
            "spool_path": str(fixture_path),
            "tail_n": 50,
            "nodes_seen_tail": 2,
            "nodes_emitted": 2,
            "reports_parsed": 5,
            "reports_invalid": 1,
            "computed_at": "2026-01-02T00:00:00+00:00",
        },
        "nodes": [
            {
                "node_id": "node-a",
                "current_boot_id": "boot-1",
                "latest_seq": 3,
                "latest_emitted_at": "2026-01-01T00:00:04+00:00",
                "current_health": "OK",
                "current_reasons": [],
                "reports_seen_tail": 3,
                "degraded_count_tail": 1,
                "unhealthy_count_tail": 0,
                "top_reasons_tail": [
                    {"reason": "collector_failed:cpu", "count": 1},
                    {"reason": "collector_failed:memory", "count": 1},
                ],
                "max_cpu1_tail": None,
                "min_mem_available_pct_tail": None,
                "min_disk_free_pct_tail": None,
                "health_transitions_tail": 2,
                "signal_trends": {},
                "threshold_profile": "default",
                "thresholds_hash": "",
            },
            {
                "node_id": "node-b",
                "current_boot_id": "boot-2",
                "latest_seq": 2,
                "latest_emitted_at": "2026-01-01T00:00:03+00:00",
                "current_health": "DEGRADED",
                "current_reasons": ["collector_failed:cpu", "collector_failed:disk"],
                "reports_seen_tail": 2,
                "degraded_count_tail": 2,
                "unhealthy_count_tail": 0,
                "top_reasons_tail": [
                    {"reason": "collector_failed:disk", "count": 2},
                    {"reason": "collector_failed:cpu", "count": 1},
                ],
                "max_cpu1_tail": None,
                "min_mem_available_pct_tail": None,
                "min_disk_free_pct_tail": None,
                "health_transitions_tail": 0,
                "signal_trends": {},
                "threshold_profile": "default",
                "thresholds_hash": "",
            },
        ],
    }

    assert payload == expected
