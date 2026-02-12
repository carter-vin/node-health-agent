"""
triage.render.table
AUTHOR: carter-vin

Compact table renderer
"""

from __future__ import annotations

from triage.render.base import Renderer
from triage.render.utils import format_gb_compact, format_load


class TableRenderer(Renderer):
    name = "table"

    def render(self, summaries, *, meta: dict) -> str:
        headers = [
            "NODE",
            "HEALTH",
            "CPU1",
            "MEM_FREE",
            "DISK_FREE",
            "DEG",
            "UNH",
        ]

        rows = [headers]
        for summary in summaries:
            rows.append(
                [
                    summary.node_id,
                    summary.current_health,
                    format_load(summary.loadavg_1m),
                    format_gb_compact(summary.mem_available_bytes),
                    format_gb_compact(summary.disk_free_bytes),
                    str(summary.degraded_count_tail),
                    str(summary.unhealthy_count_tail),
                ]
            )

        widths = [max(len(row[i]) for row in rows) for i in range(len(headers))]
        lines: list[str] = []

        for row in rows:
            padded = [row[i].ljust(widths[i]) for i in range(len(headers))]
            lines.append("  ".join(padded))

        return "\n".join(lines)
