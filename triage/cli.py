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
    summaries = list(all_summaries)

    if node:
        # Filter is applied after summarization to keep core logic pure
        summaries = [summary for summary in summaries if summary.node_id == node]

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
        return

    typer.echo(render_text(summaries, meta=meta))


if __name__ == "__main__":
    app()
