"""
triage.summarize

Deterministic summarization and filtering for operator triage output.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable


TRIAGE_SCHEMA_VERSION = "1"


def _parse_iso_epoch(ts: str) -> float | None:
    """Parse ISO 8601 timestamp to epoch float. Returns None on failure."""
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _linear_slope(pairs: list[tuple[float, float]]) -> float | None:
    """
    Compute least-squares slope (y per second) from (x_epoch, y) pairs.
    Returns None when fewer than 2 points or denominator is zero.
    """
    n = len(pairs)
    if n < 2:
        return None
    sum_x = sum(x for x, _ in pairs)
    sum_y = sum(y for _, y in pairs)
    sum_xx = sum(x * x for x, _ in pairs)
    sum_xy = sum(x * y for x, y in pairs)
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0.0:
        return None
    return (n * sum_xy - sum_x * sum_y) / denom


def _trend_direction(slope_per_hr: float, stable_threshold: float) -> str:
    if abs(slope_per_hr) < stable_threshold:
        return "stable"
    return "rising" if slope_per_hr > 0 else "declining"


def _trend_label(direction: str, slope_per_hr: float, unit: str) -> str:
    if direction == "stable":
        return "stable"
    sign = "+" if slope_per_hr > 0 else ""
    return f"{direction} ({sign}{slope_per_hr:.2f} {unit})"


def compute_signal_trends(
    ts_cpu1: list[tuple[float, float]],
    ts_mem_avail: list[tuple[float, float]],
    ts_disk_free: list[tuple[float, float]],
) -> dict[str, dict]:
    """
    Compute slope-based trend direction for key signals.

    Each input list is a list of (epoch_seconds, value) pairs in chronological order.
    Returns a dict keyed by signal name with keys: direction, slope_per_hr, label.
    """
    trends: dict[str, dict] = {}

    cpu_slope = _linear_slope(ts_cpu1)
    if cpu_slope is not None:
        slope_per_hr = cpu_slope * 3600.0
        direction = _trend_direction(slope_per_hr, stable_threshold=0.1)
        trends["loadavg_1m"] = {
            "direction": direction,
            "slope_per_hr": round(slope_per_hr, 3),
            "label": _trend_label(direction, slope_per_hr, "load/hr"),
        }

    mem_slope = _linear_slope(ts_mem_avail)
    if mem_slope is not None:
        slope_per_hr_gb = (mem_slope * 3600.0) / (1024 ** 3)
        direction = _trend_direction(slope_per_hr_gb, stable_threshold=0.1)
        trends["mem_available_bytes"] = {
            "direction": direction,
            "slope_per_hr": round(slope_per_hr_gb, 3),
            "label": _trend_label(direction, slope_per_hr_gb, "GB/hr"),
        }

    disk_slope = _linear_slope(ts_disk_free)
    if disk_slope is not None:
        slope_per_hr_gb = (disk_slope * 3600.0) / (1024 ** 3)
        direction = _trend_direction(slope_per_hr_gb, stable_threshold=0.01)
        trends["disk_free_bytes"] = {
            "direction": direction,
            "slope_per_hr": round(slope_per_hr_gb, 3),
            "label": _trend_label(direction, slope_per_hr_gb, "GB/hr"),
        }

    return trends


@dataclass(frozen=True)
class NodeSummary:
    node_id: str
    current_boot_id: str
    latest_seq: int | None
    latest_emitted_at: str
    current_health: str
    current_reasons: list[str]
    reports_seen_tail: int
    degraded_count_tail: int
    unhealthy_count_tail: int
    top_reasons_tail: list[dict[str, int | str]]
    loadavg_1m: float | None
    loadavg_5m: float | None
    loadavg_15m: float | None
    cpu_count_logical: int | None
    mem_total_bytes: int | None
    mem_available_bytes: int | None
    disk_total_bytes: int | None
    disk_free_bytes: int | None
    max_cpu1_tail: float | None = None
    min_mem_available_pct_tail: float | None = None
    min_disk_free_pct_tail: float | None = None
    health_transitions_tail: int = 0
    signal_trends: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "current_boot_id": self.current_boot_id,
            "latest_seq": self.latest_seq,
            "latest_emitted_at": self.latest_emitted_at,
            "current_health": self.current_health,
            "current_reasons": list(self.current_reasons),
            "reports_seen_tail": self.reports_seen_tail,
            "degraded_count_tail": self.degraded_count_tail,
            "unhealthy_count_tail": self.unhealthy_count_tail,
            "top_reasons_tail": list(self.top_reasons_tail),
            "max_cpu1_tail": self.max_cpu1_tail,
            "min_mem_available_pct_tail": self.min_mem_available_pct_tail,
            "min_disk_free_pct_tail": self.min_disk_free_pct_tail,
            "health_transitions_tail": self.health_transitions_tail,
            "signal_trends": dict(self.signal_trends),
        }


def _coerce_int(value: object) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _normalize_reasons(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _node_id_for(report: dict) -> str:
    identity = report.get("identity", {})
    node_id = identity.get("node_id")
    return str(node_id) if node_id else "unknown"


def _ordering_key(report: dict) -> tuple[str, int]:
    timing = report.get("timing", {})
    emitted_at = timing.get("emitted_at") or ""
    seq = _coerce_int(timing.get("seq"))
    return emitted_at, seq or 0


def _display_seq(seq: int | None) -> str:
    return str(seq) if seq is not None else "unknown"


def summarize_by_node(
    reports: Iterable[dict], *, top_k_reasons: int | None = 5
) -> list[NodeSummary]:
    """
    Summarize reports into per-node summaries
    """
    reports_list = list(reports)
    if not reports_list:
        return []

    top_limit = top_k_reasons if top_k_reasons and top_k_reasons > 0 else None

    accumulators: dict[str, dict] = {}

    for report in reports_list:
        node_id = _node_id_for(report)
        # Accumulate counts per node across the tail window
        acc = accumulators.setdefault(
            node_id,
            {
                "reports_seen": 0,
                "degraded": 0,
                "unhealthy": 0,
                "reason_counts": Counter(),
                "latest_report": None,
                "latest_key": None,
                "cpu1_values": [],
                "mem_pct_values": [],
                "disk_pct_values": [],
                "health_sequence": [],
                "ts_cpu1": [],
                "ts_mem_avail": [],
                "ts_disk_free": [],
            },
        )

        acc["reports_seen"] += 1

        assessment = report.get("assessment", {})
        health = assessment.get("health", "unknown")

        if health == "DEGRADED":
            acc["degraded"] += 1
        elif health == "UNHEALTHY":
            acc["unhealthy"] += 1

        acc["health_sequence"].append(health)

        reasons = _normalize_reasons(assessment.get("reasons", []))
        acc["reason_counts"].update(reasons)

        signals = report.get("signals", {})
        loadavg_1m = signals.get("loadavg_1m")
        if isinstance(loadavg_1m, (int, float)):
            acc["cpu1_values"].append(float(loadavg_1m))

        mem_avail = signals.get("mem_available_bytes")
        mem_total = signals.get("mem_total_bytes")
        if isinstance(mem_avail, (int, float)) and isinstance(mem_total, (int, float)) and mem_total > 0:
            acc["mem_pct_values"].append((mem_avail / mem_total) * 100.0)

        disk_free = signals.get("disk_free_bytes")
        disk_total = signals.get("disk_total_bytes")
        if isinstance(disk_free, (int, float)) and isinstance(disk_total, (int, float)) and disk_total > 0:
            acc["disk_pct_values"].append((disk_free / disk_total) * 100.0)

        # Collect time-series data for trend computation
        emitted_at_str = report.get("timing", {}).get("emitted_at") or ""
        epoch = _parse_iso_epoch(emitted_at_str)
        if epoch is not None:
            if isinstance(loadavg_1m, (int, float)):
                acc["ts_cpu1"].append((epoch, float(loadavg_1m)))
            if isinstance(mem_avail, (int, float)):
                acc["ts_mem_avail"].append((epoch, float(mem_avail)))
            if isinstance(disk_free, (int, float)):
                acc["ts_disk_free"].append((epoch, float(disk_free)))

        # Latest report wins by emitted_at then seq
        key = _ordering_key(report)
        if acc["latest_key"] is None or key > acc["latest_key"]:
            acc["latest_key"] = key
            acc["latest_report"] = report

    summaries: list[NodeSummary] = []

    for node_id, acc in accumulators.items():
        latest = acc["latest_report"] or {}
        identity = latest.get("identity", {})
        timing = latest.get("timing", {})
        assessment = latest.get("assessment", {})
        signals = latest.get("signals", {})

        current_boot_id = identity.get("boot_id") or "unknown"
        latest_seq = _coerce_int(timing.get("seq"))
        latest_emitted_at = timing.get("emitted_at") or "unknown"
        current_health = assessment.get("health", "unknown")
        current_reasons = sorted(_normalize_reasons(assessment.get("reasons", [])))

        ordered_reasons = sorted(
            acc["reason_counts"].items(), key=lambda item: (-item[1], item[0])
        )
        if top_limit is not None:
            ordered_reasons = ordered_reasons[:top_limit]

        top_reasons = [
            {"reason": reason, "count": count} for reason, count in ordered_reasons
        ]

        cpu1_vals = acc["cpu1_values"]
        mem_pct_vals = acc["mem_pct_values"]
        disk_pct_vals = acc["disk_pct_values"]
        health_seq = acc["health_sequence"]

        max_cpu1_tail = round(max(cpu1_vals), 2) if cpu1_vals else None
        min_mem_available_pct_tail = round(min(mem_pct_vals), 2) if mem_pct_vals else None
        min_disk_free_pct_tail = round(min(disk_pct_vals), 2) if disk_pct_vals else None
        health_transitions_tail = sum(
            1 for i in range(1, len(health_seq)) if health_seq[i] != health_seq[i - 1]
        )

        signal_trends = compute_signal_trends(
            acc["ts_cpu1"],
            acc["ts_mem_avail"],
            acc["ts_disk_free"],
        )

        summaries.append(
            NodeSummary(
                node_id=node_id,
                current_boot_id=str(current_boot_id) if current_boot_id else "unknown",
                latest_seq=latest_seq,
                latest_emitted_at=str(latest_emitted_at),
                current_health=str(current_health),
                current_reasons=current_reasons,
                reports_seen_tail=acc["reports_seen"],
                degraded_count_tail=acc["degraded"],
                unhealthy_count_tail=acc["unhealthy"],
                top_reasons_tail=top_reasons,
                loadavg_1m=signals.get("loadavg_1m"),
                loadavg_5m=signals.get("loadavg_5m"),
                loadavg_15m=signals.get("loadavg_15m"),
                cpu_count_logical=signals.get("cpu_count_logical"),
                mem_total_bytes=signals.get("mem_total_bytes"),
                mem_available_bytes=signals.get("mem_available_bytes"),
                disk_total_bytes=signals.get("disk_total_bytes"),
                disk_free_bytes=signals.get("disk_free_bytes"),
                max_cpu1_tail=max_cpu1_tail,
                min_mem_available_pct_tail=min_mem_available_pct_tail,
                min_disk_free_pct_tail=min_disk_free_pct_tail,
                health_transitions_tail=health_transitions_tail,
                signal_trends=signal_trends,
            )
        )

    return sorted(summaries, key=lambda summary: summary.node_id)


def render_text(node_summaries: Iterable[NodeSummary], *, meta: dict) -> str:
    """
    Render per-node summaries into deterministic text
    """
    summaries = sorted(list(node_summaries), key=lambda summary: summary.node_id)
    # Header comes first for quick operator scan
    lines: list[str] = [f"nodes_seen_tail: {meta.get('nodes_seen_tail', 0)}"]
    if "nodes_emitted" in meta:
        lines.append(f"nodes_emitted: {meta.get('nodes_emitted', 0)}")
    if "files_seen" in meta:
        lines.append(f"files_seen: {meta.get('files_seen', 0)}")

    fleet_ok = sum(1 for s in summaries if s.current_health == "OK")
    fleet_degraded = sum(1 for s in summaries if s.current_health == "DEGRADED")
    fleet_unhealthy = sum(1 for s in summaries if s.current_health == "UNHEALTHY")
    lines.append(f"fleet_ok: {fleet_ok}")
    lines.append(f"fleet_degraded: {fleet_degraded}")
    lines.append(f"fleet_unhealthy: {fleet_unhealthy}")

    if not summaries:
        return "\n".join(lines)

    for summary in summaries:
        lines.append("")
        lines.append(f"node_id: {summary.node_id}")
        lines.append(f"current_boot_id: {summary.current_boot_id}")
        lines.append(f"latest_health: {summary.current_health}")
        lines.append(f"latest_seq: {_display_seq(summary.latest_seq)}")
        lines.append(f"latest_emitted_at: {summary.latest_emitted_at}")
        lines.append(
            f"degraded_count_tail: {summary.degraded_count_tail} / {summary.reports_seen_tail}"
        )
        lines.append(
            f"unhealthy_count_tail: {summary.unhealthy_count_tail} / {summary.reports_seen_tail}"
        )

        if summary.top_reasons_tail:
            top_reasons = ", ".join(
                f"{item['reason']}:{item['count']}" for item in summary.top_reasons_tail
            )
        else:
            top_reasons = "none"

        lines.append(f"top_reasons_tail: {top_reasons}")

        if summary.current_health in {"DEGRADED", "UNHEALTHY"}:
            if summary.current_reasons:
                current_reasons = ", ".join(summary.current_reasons)
            else:
                current_reasons = "none"
        else:
            current_reasons = "none"

        lines.append(f"current_reasons: {current_reasons}")

        def _fmt_load_stat(v: float | None) -> str:
            return f"{v:.2f}" if v is not None else "n/a"

        def _fmt_pct_stat(v: float | None) -> str:
            return f"{v:.2f}%" if v is not None else "n/a"

        lines.append(f"max_cpu1_tail: {_fmt_load_stat(summary.max_cpu1_tail)}")
        lines.append(f"min_mem_available_pct_tail: {_fmt_pct_stat(summary.min_mem_available_pct_tail)}")
        lines.append(f"min_disk_free_pct_tail: {_fmt_pct_stat(summary.min_disk_free_pct_tail)}")
        lines.append(f"health_transitions_tail: {summary.health_transitions_tail}")

        if summary.signal_trends:
            for sig, trend in sorted(summary.signal_trends.items()):
                lines.append(f"{sig}_trend: {trend['label']}")

    return "\n".join(lines)


def render_json(node_summaries: Iterable[NodeSummary], *, meta: dict) -> dict:
    """
    Render per-node summaries into a deterministic JSON payload
    """
    summaries = sorted(list(node_summaries), key=lambda summary: summary.node_id)

    meta_payload = {
        "schema_version": TRIAGE_SCHEMA_VERSION,
        "tail_n": meta.get("tail_n"),
        "nodes_seen_tail": meta.get("nodes_seen_tail", 0),
        "nodes_emitted": meta.get("nodes_emitted", 0),
        "reports_parsed": meta.get("reports_parsed", 0),
        "reports_invalid": meta.get("reports_invalid", 0),
        "computed_at": meta.get("computed_at"),
    }

    if "spool_path" in meta and meta.get("spool_path") is not None:
        meta_payload["spool_path"] = meta.get("spool_path")

    if "spool_dir" in meta:
        meta_payload["spool_dir"] = meta.get("spool_dir")
    if "files_seen" in meta:
        meta_payload["files_seen"] = meta.get("files_seen")
    if "reports_invalid_total" in meta:
        meta_payload["reports_invalid_total"] = meta.get("reports_invalid_total")

    return {
        "meta": meta_payload,
        "nodes": [summary.to_dict() for summary in summaries],
    }


def apply_filters(
    summaries: list[NodeSummary],
    *,
    node: str | None,
    only_degraded: bool,
    only_unhealthy: bool,
    min_degraded_count: int | None,
    changes_only: bool = False,
) -> list[NodeSummary]:
    """Filter a list of NodeSummary objects by operator-specified criteria."""
    if only_degraded and only_unhealthy:
        raise ValueError("only_degraded and only_unhealthy are mutually exclusive")

    filtered = list(summaries)

    if node:
        filtered = [s for s in filtered if s.node_id == node]
    if only_degraded:
        filtered = [s for s in filtered if s.current_health == "DEGRADED"]
    if only_unhealthy:
        filtered = [s for s in filtered if s.current_health == "UNHEALTHY"]
    if min_degraded_count is not None and min_degraded_count > 0:
        filtered = [s for s in filtered if s.degraded_count_tail >= min_degraded_count]
    if changes_only:
        filtered = [s for s in filtered if s.health_transitions_tail > 0]

    return filtered


def summarize_reports(reports: Iterable[dict]) -> str:
    """
    Legacy single-stream summary (v1 behavior)
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
