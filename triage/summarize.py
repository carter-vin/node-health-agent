"""
triage.summarize
AUTHOR: carter-vin

Deterministic summarization for operator-friendly output
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable


def summarize_reports(reports: Iterable[dict]) -> str:
    """
    Summarize reports into a stable, plain-text output
    """
    reports_list = list(reports)

    if not reports_list:
        return "\n".join(
            [
                "node_id: unknown",
                "boot_id: unknown",
                "latest_seq: unknown",
                "latest_emitted_at: unknown",
                "latest_health: unknown",
                "degraded_count_tail: 0",
                "top_reasons_tail: none",
            ]
        )

    latest = reports_list[-1]
    identity = latest.get("identity", {})
    timing = latest.get("timing", {})
    assessment = latest.get("assessment", {})

    node_id = identity.get("node_id", "unknown")
    boot_id = identity.get("boot_id", "unknown")
    latest_seq = timing.get("seq", "unknown")
    latest_emitted_at = timing.get("emitted_at", "unknown")
    latest_health = assessment.get("health", "unknown")

    degraded_count = sum(
        1 for report in reports_list if report.get("assessment", {}).get("health") == "DEGRADED"
    )

    reason_counts: Counter[str] = Counter()
    for report in reports_list:
        reasons = report.get("assessment", {}).get("reasons", [])
        reason_counts.update(reasons)

    if reason_counts:
        ordered_reasons = sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
        top_reasons = ", ".join(f"{reason}:{count}" for reason, count in ordered_reasons)
    else:
        top_reasons = "none"

    return "\n".join(
        [
            f"node_id: {node_id}",
            f"boot_id: {boot_id}",
            f"latest_seq: {latest_seq}",
            f"latest_emitted_at: {latest_emitted_at}",
            f"latest_health: {latest_health}",
            f"degraded_count_tail: {degraded_count}",
            f"top_reasons_tail: {top_reasons}",
        ]
    )
