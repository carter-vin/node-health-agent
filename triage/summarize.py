"""
triage.summarize
AUTHOR: carter-vin

Deterministic summarization for operator-friendly output
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable


TRIAGE_SCHEMA_VERSION = "1"


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
            },
        )

        acc["reports_seen"] += 1

        assessment = report.get("assessment", {})
        health = assessment.get("health", "unknown")

        if health == "DEGRADED":
            acc["degraded"] += 1
        elif health == "UNHEALTHY":
            acc["unhealthy"] += 1

        reasons = _normalize_reasons(assessment.get("reasons", []))
        acc["reason_counts"].update(reasons)

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

    return "\n".join(lines)


def render_json(node_summaries: Iterable[NodeSummary], *, meta: dict) -> dict:
    """
    Render per-node summaries into a deterministic JSON payload
    """
    summaries = sorted(list(node_summaries), key=lambda summary: summary.node_id)

    meta_payload = {
        "schema_version": TRIAGE_SCHEMA_VERSION,
        "spool_path": meta.get("spool_path"),
        "tail_n": meta.get("tail_n"),
        "nodes_seen_tail": meta.get("nodes_seen_tail", 0),
        "nodes_emitted": meta.get("nodes_emitted", 0),
        "reports_parsed": meta.get("reports_parsed", 0),
        "reports_invalid": meta.get("reports_invalid", 0),
        "computed_at": meta.get("computed_at"),
    }

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
