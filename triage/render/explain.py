"""
triage.render.explain
AUTHOR: carter-vin

Human explanation renderer
"""

from __future__ import annotations

from agent.evaluate import (
    CPU_DEGRADED_FACTOR,
    CPU_UNHEALTHY_FACTOR,
    DISK_DEGRADED_PCT,
    DISK_UNHEALTHY_PCT,
    MEM_DEGRADED_PCT,
    MEM_UNHEALTHY_PCT,
)
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
        threshold = summary.cpu_count_logical * CPU_DEGRADED_FACTOR
        return f"{label} ({format_load(summary.loadavg_1m)} > {threshold:.2f})"
    if reason == "signal:cpu_critical" and summary.cpu_count_logical and summary.loadavg_1m is not None:
        threshold = summary.cpu_count_logical * CPU_UNHEALTHY_FACTOR
        return f"{label} ({format_load(summary.loadavg_1m)} > {threshold:.2f})"
    if reason == "signal:disk_free_low" and summary.disk_free_bytes and summary.disk_total_bytes:
        return f"{label} ({DISK_DEGRADED_PCT:.0f}% threshold)"
    if reason == "signal:disk_free_critical" and summary.disk_free_bytes and summary.disk_total_bytes:
        return f"{label} ({DISK_UNHEALTHY_PCT:.0f}% threshold)"
    if reason == "signal:mem_available_low" and summary.mem_available_bytes and summary.mem_total_bytes:
        return f"{label} ({MEM_DEGRADED_PCT:.0f}% threshold)"
    if reason == "signal:mem_available_critical" and summary.mem_available_bytes and summary.mem_total_bytes:
        return f"{label} ({MEM_UNHEALTHY_PCT:.0f}% threshold)"
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

            if summary.top_reasons_tail:
                most_common = summary.top_reasons_tail[0]["reason"]
                blocks.append(f"- Most frequent issue: {most_common}")
            else:
                blocks.append("- Most frequent issue: none")

            blocks.append("")

        return "\n".join(blocks).rstrip()
