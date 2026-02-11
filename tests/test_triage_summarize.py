"""
Contract test for deterministic triage summarization
"""

from pathlib import Path

from triage.read import tail_jsonl_with_stats
from triage.summarize import render_json, render_text, summarize_by_node


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
            },
        ],
    }

    assert payload == expected
