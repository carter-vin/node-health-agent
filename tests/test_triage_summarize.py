"""
Contract test for deterministic triage summarization
"""

from pathlib import Path

from triage.read import tail_jsonl
from triage.summarize import summarize_reports


def test_triage_summarize_small_fixture() -> None:
    """
    Summarize a fixed fixture and compare to expected output
    """
    fixture_path = Path("fixtures") / "spool_small.jsonl"
    reports = tail_jsonl(fixture_path, 50)

    summary = summarize_reports(reports)

    expected = "\n".join(
        [
            "node_id: node-a",
            "boot_id: boot-1",
            "latest_seq: 3",
            "latest_emitted_at: 2026-01-01T00:00:02+00:00",
            "latest_health: OK",
            "degraded_count_tail: 1",
            "top_reasons_tail: collector_failed:cpu:1",
        ]
    )

    assert summary == expected
