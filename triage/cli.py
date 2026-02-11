"""
triage.cli
AUTHOR: carter-vin

Minimal triage CLI for local operator workflows
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import json
import typer

from triage.read import tail_jsonl, tail_jsonl_with_stats
from triage.summarize import render_json, render_text, summarize_by_node, summarize_reports


app = typer.Typer(add_completion=False, help="node-health-triage: local triage tools")


def _apply_filters(
    summaries,
    *,
    node: str | None,
    only_degraded: bool,
    only_unhealthy: bool,
    min_degraded_count: int | None,
):
    if only_degraded and only_unhealthy:
        raise typer.BadParameter("--only-degraded and --only-unhealthy are mutually exclusive")

    filtered = list(summaries)

    if node:
        filtered = [summary for summary in filtered if summary.node_id == node]

    if only_degraded:
        filtered = [summary for summary in filtered if summary.current_health == "DEGRADED"]

    if only_unhealthy:
        filtered = [summary for summary in filtered if summary.current_health == "UNHEALTHY"]

    if min_degraded_count is not None and min_degraded_count > 0:
        filtered = [
            summary
            for summary in filtered
            if summary.degraded_count_tail >= min_degraded_count
        ]

    return filtered


def _maybe_exit_by_health(*, summaries, only_degraded: bool, only_unhealthy: bool) -> None:
    if not (only_degraded or only_unhealthy):
        return

    has_unhealthy = any(summary.current_health == "UNHEALTHY" for summary in summaries)
    has_degraded = any(summary.current_health == "DEGRADED" for summary in summaries)

    if has_unhealthy:
        raise typer.Exit(code=3)
    if has_degraded:
        raise typer.Exit(code=2)
    raise typer.Exit(code=0)


@app.command("tail")
def tail(
    spool: str = typer.Option(
        "spool/node_reports.jsonl",
        help="Path to JSONL spool file.",
    ),
    n: int = typer.Option(
        50,
        "--n",
        help="Number of reports to read from the end.",
    ),
) -> None:
    """
    Print the parsed count and last seq from the tail of the spool
    """
    path = Path(spool)
    reports = tail_jsonl(path, n)

    last_seq = None
    if reports:
        last_seq = reports[-1].get("timing", {}).get("seq")

    typer.echo(f"reports_parsed: {len(reports)}")
    typer.echo(f"last_seq: {last_seq if last_seq is not None else 'unknown'}")


@app.command("summarize")
def summarize(
    spool: str = typer.Option(
        "spool/node_reports.jsonl",
        help="Path to JSONL spool file.",
    ),
    tail: int = typer.Option(
        200,
        "--tail",
        help="Number of reports to summarize from the end.",
    ),
    by_node: bool = typer.Option(
        True,
        "--by-node/--no-by-node",
        help="Summarize per node (v2 mode).",
    ),
    output_format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text or json.",
    ),
    node: str | None = typer.Option(
        None,
        "--node",
        help="Filter to a specific node_id.",
    ),
    only_degraded: bool = typer.Option(
        False,
        "--only-degraded",
        help="Show only nodes currently DEGRADED.",
    ),
    only_unhealthy: bool = typer.Option(
        False,
        "--only-unhealthy",
        help="Show only nodes currently UNHEALTHY.",
    ),
    min_degraded_count: int | None = typer.Option(
        None,
        "--min-degraded-count",
        help="Filter nodes by degraded_count_tail threshold.",
        min=1,
    ),
    top_k_reasons: int = typer.Option(
        5,
        "--top-k-reasons",
        help="Maximum number of reasons to display per node.",
    ),
) -> None:
    """
    Summarize the spool with deterministic per-node output
    """
    path = Path(spool)
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("--format must be 'text' or 'json'")

    reports, invalid_count = tail_jsonl_with_stats(path, tail)

    if not by_node:
        if output_format == "json":
            raise typer.BadParameter("--no-by-node is only supported with --format text")
        typer.echo(summarize_reports(reports))
        return

    # Build full per-node summaries before filtering
    all_summaries = summarize_by_node(reports, top_k_reasons=top_k_reasons)
    summaries = _apply_filters(
        all_summaries,
        node=node,
        only_degraded=only_degraded,
        only_unhealthy=only_unhealthy,
        min_degraded_count=min_degraded_count,
    )

    meta = {
        "spool_path": str(path),
        "tail_n": tail,
        "nodes_seen_tail": len(all_summaries),
        "nodes_emitted": len(summaries),
        "reports_parsed": len(reports),
        "reports_invalid": invalid_count,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    if output_format == "json":
        payload = render_json(summaries, meta=meta)
        typer.echo(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    else:
        typer.echo(render_text(summaries, meta=meta))

    _maybe_exit_by_health(
        summaries=summaries,
        only_degraded=only_degraded,
        only_unhealthy=only_unhealthy,
    )


@app.command("summarize-dir")
def summarize_dir(
    dir_path: str = typer.Option(
        "spool",
        "--dir",
        help="Directory containing spool files.",
    ),
    glob: str = typer.Option(
        "*.jsonl",
        "--glob",
        help="Glob pattern for spool files.",
    ),
    tail: int = typer.Option(
        200,
        "--tail",
        help="Number of reports to summarize from the end.",
    ),
    output_format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text or json.",
    ),
    node: str | None = typer.Option(
        None,
        "--node",
        help="Filter to a specific node_id.",
    ),
    only_degraded: bool = typer.Option(
        False,
        "--only-degraded",
        help="Show only nodes currently DEGRADED.",
    ),
    only_unhealthy: bool = typer.Option(
        False,
        "--only-unhealthy",
        help="Show only nodes currently UNHEALTHY.",
    ),
    min_degraded_count: int | None = typer.Option(
        None,
        "--min-degraded-count",
        help="Filter nodes by degraded_count_tail threshold.",
        min=1,
    ),
    top_k_reasons: int = typer.Option(
        5,
        "--top-k-reasons",
        help="Maximum number of reasons to display per node.",
    ),
) -> None:
    """
    Summarize a directory of spools with deterministic per-node output
    """
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("--format must be 'text' or 'json'")

    root = Path(dir_path)
    files = sorted(root.glob(glob))

    reports: list[dict] = []
    reports_invalid_total = 0

    for path in files:
        file_reports, invalid_count = tail_jsonl_with_stats(path, tail)
        node_ids = {
            report.get("identity", {}).get("node_id")
            for report in file_reports
            if report.get("identity", {}).get("node_id")
        }
        if len(node_ids) > 1:
            raise typer.BadParameter("spool file contains multiple node_id values")
        reports.extend(file_reports)
        reports_invalid_total += invalid_count

    all_summaries = summarize_by_node(reports, top_k_reasons=top_k_reasons)
    summaries = _apply_filters(
        all_summaries,
        node=node,
        only_degraded=only_degraded,
        only_unhealthy=only_unhealthy,
        min_degraded_count=min_degraded_count,
    )

    meta = {
        "spool_dir": str(root),
        "tail_n": tail,
        "files_seen": len(files),
        "nodes_seen_tail": len(all_summaries),
        "nodes_emitted": len(summaries),
        "reports_parsed": len(reports),
        "reports_invalid": reports_invalid_total,
        "reports_invalid_total": reports_invalid_total,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    if output_format == "json":
        payload = render_json(summaries, meta=meta)
        typer.echo(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    else:
        typer.echo(render_text(summaries, meta=meta))

    _maybe_exit_by_health(
        summaries=summaries,
        only_degraded=only_degraded,
        only_unhealthy=only_unhealthy,
    )


if __name__ == "__main__":
    app()
