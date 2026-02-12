"""
triage.render.pretty
AUTHOR: carter-vin

Readable block renderer
"""

from __future__ import annotations

from triage.render.base import Renderer
from triage.render.utils import format_gb, format_load


class PrettyRenderer(Renderer):
    name = "pretty"

    def render(self, summaries, *, meta: dict) -> str:
        blocks: list[str] = []
        for summary in summaries:
            header = f"NODE {summary.node_id}"
            blocks.append(header)
            blocks.append("-" * len(header))
            blocks.append(f"Health: {summary.current_health}")
            blocks.append(f"Seq: {summary.latest_seq or 'unknown'}   Boot: {summary.current_boot_id}")
            blocks.append(f"Emitted: {summary.latest_emitted_at}")
            blocks.append("")

            cpu_line = (
                f"CPU load (1m/5m/15m): {format_load(summary.loadavg_1m)} / "
                f"{format_load(summary.loadavg_5m)} / {format_load(summary.loadavg_15m)}"
            )
            blocks.append(cpu_line)
            blocks.append(f"Disk free: {format_gb(summary.disk_free_bytes)}")
            blocks.append(f"Memory available: {format_gb(summary.mem_available_bytes)}")
            blocks.append("")

            blocks.append(
                f"Degraded (tail): {summary.degraded_count_tail} / {summary.reports_seen_tail}"
            )
            blocks.append(
                f"Unhealthy (tail): {summary.unhealthy_count_tail} / {summary.reports_seen_tail}"
            )

            if summary.top_reasons_tail:
                top_reasons = ", ".join(
                    f"{item['reason']}:{item['count']}" for item in summary.top_reasons_tail
                )
            else:
                top_reasons = "none"

            blocks.append(f"Top reasons: {top_reasons}")
            blocks.append("")

        return "\n".join(blocks).rstrip()
