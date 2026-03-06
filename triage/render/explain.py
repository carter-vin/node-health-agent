"""
triage.render.explain
AUTHOR: carter-vin

Human explanation renderer
"""

from __future__ import annotations

from triage.render.base import Renderer
from triage.render.utils import format_load


_REASON_LABELS = {
    "signal:cpu_high": "CPU load high",
    "signal:cpu_critical": "CPU load critical",
    "signal:disk_free_low": "Disk free low",
    "signal:disk_free_critical": "Disk free critical",
    "signal:mem_available_low": "Memory available low",
    "signal:mem_available_critical": "Memory available critical",
}


def _reason_message(summary, reason: str) -> str:
    label = _REASON_LABELS.get(reason, reason)
    if reason == "signal:cpu_high" and summary.cpu_count_logical and summary.loadavg_1m is not None:
        return f"{label} (loadavg_1m={format_load(summary.loadavg_1m)})"
    if reason == "signal:cpu_critical" and summary.cpu_count_logical and summary.loadavg_1m is not None:
        return f"{label} (loadavg_1m={format_load(summary.loadavg_1m)})"
    return label


class ExplainRenderer(Renderer):
    name = "explain"

    def render(self, summaries, *, meta: dict) -> str:
        blocks: list[str] = []
        for summary in summaries:
            blocks.append(f"Node: {summary.node_id}")
            blocks.append(f"Status: {summary.current_health}")
            blocks.append("")
            blocks.append("Reasons:")

            if summary.current_reasons:
                for reason in summary.current_reasons:
                    blocks.append(f"- {_reason_message(summary, reason)}")
            else:
                blocks.append("- none")

            blocks.append("")
            blocks.append("Tail Summary:")
            blocks.append(
                f"- Degraded: {summary.degraded_count_tail} / {summary.reports_seen_tail}"
            )
            blocks.append(
                f"- Unhealthy: {summary.unhealthy_count_tail} / {summary.reports_seen_tail}"
            )
            blocks.append(f"- Health transitions: {summary.health_transitions_tail}")

            if summary.max_cpu1_tail is not None:
                blocks.append(f"- Max CPU load (1m): {summary.max_cpu1_tail:.2f}")
            if summary.min_mem_available_pct_tail is not None:
                blocks.append(f"- Min memory available: {summary.min_mem_available_pct_tail:.2f}%")
            if summary.min_disk_free_pct_tail is not None:
                blocks.append(f"- Min disk free: {summary.min_disk_free_pct_tail:.2f}%")

            if summary.top_reasons_tail:
                most_common = summary.top_reasons_tail[0]["reason"]
                blocks.append(f"- Most frequent issue: {most_common}")
            else:
                blocks.append("- Most frequent issue: none")

            if summary.signal_trends:
                blocks.append("")
                blocks.append("Trends:")
                for sig, trend in sorted(summary.signal_trends.items()):
                    blocks.append(f"- {sig}: {trend['label']}")

            blocks.append("")
            blocks.append("Config Context:")
            blocks.append(f"- threshold_profile: {summary.threshold_profile}")
            if summary.thresholds_hash:
                blocks.append(f"- thresholds_hash: {summary.thresholds_hash}")
            else:
                blocks.append("- thresholds_hash: (unavailable)")
            blocks.append("- (exact threshold values require original config source)")

            blocks.append("")

        return "\n".join(blocks).rstrip()
