"""
triage.cli
AUTHOR: carter-vin

Minimal triage CLI for local operator workflows
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import typer

from triage.read import last_valid_report, tail_jsonl, tail_jsonl_with_stats
from triage.render import get_renderer
from triage.summarize import detect_mixed_thresholds, summarize_by_node, summarize_reports


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


@app.command("status")
def status(
    spool: str = typer.Option(
        "spool/node_reports.jsonl",
        help="Path to JSONL spool file.",
    ),
    tail: int = typer.Option(
        200,
        "--tail",
        help="Number of reports to search from the end.",
    ),
    output_format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text or json.",
    ),
) -> None:
    """
    Print the current status from the last valid report in the spool.

    Exit code is always 0. Use summarize with --only-degraded / --only-unhealthy for filtering.
    """
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("--format must be text or json")

    path = Path(spool)
    if not path.exists():
        typer.echo(f"error: spool not found: {spool}", err=True)
        raise typer.Exit(code=1)

    report = last_valid_report(path, tail)
    if report is None:
        typer.echo(f"error: no valid reports found in last {tail} lines of {spool}", err=True)
        raise typer.Exit(code=1)

    node_id = report["identity"]["node_id"]
    health = report["assessment"]["health"]
    seq = report["timing"]["seq"]
    emitted_at = report["timing"]["emitted_at"]
    reasons_list = report.get("assessment", {}).get("reasons", [])
    reasons_str = ",".join(reasons_list) if reasons_list else "none"

    if output_format == "json":
        import json as _json
        typer.echo(_json.dumps({
            "node_id": node_id,
            "health": health,
            "seq": seq,
            "emitted_at": emitted_at,
            "reasons": reasons_list,
        }, sort_keys=True, separators=(",", ":")))
    else:
        typer.echo(
            f"node_id={node_id} health={health} seq={seq}"
            f" emitted_at={emitted_at} reasons={reasons_str}"
        )


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
    last_health = None
    if reports:
        last_seq = reports[-1].get("timing", {}).get("seq")
        last_health = reports[-1].get("assessment", {}).get("health")

    typer.echo(f"reports_parsed: {len(reports)}")
    typer.echo(f"last_seq: {last_seq if last_seq is not None else 'unknown'}")
    typer.echo(f"last_health: {last_health if last_health is not None else 'unknown'}")


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
    dual: bool = typer.Option(
        False,
        "--dual/--no-dual",
        help="Print human output followed by JSON.",
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
    if output_format not in {"text", "json", "pretty", "table", "explain"}:
        raise typer.BadParameter("--format must be json, text, pretty, table, or explain")

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

    if dual:
        human_format = output_format if output_format != "json" else "pretty"
        human_output = get_renderer(human_format).render(summaries, meta=meta)
        json_output = get_renderer("json").render(summaries, meta=meta)
        typer.echo(human_output)
        typer.echo("")
        typer.echo(json_output)
    else:
        renderer = get_renderer(output_format)
        typer.echo(renderer.render(summaries, meta=meta))

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
    dual: bool = typer.Option(
        False,
        "--dual/--no-dual",
        help="Print human output followed by JSON.",
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
    warn_mixed_thresholds: bool = typer.Option(
        False,
        "--warn-mixed-thresholds",
        help="Warn when nodes report different thresholds_hash values.",
    ),
) -> None:
    """
    Summarize a directory of spools with deterministic per-node output
    """
    if output_format not in {"text", "json", "pretty", "table", "explain"}:
        raise typer.BadParameter("--format must be json, text, pretty, table, or explain")

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

    mixed_warning: str | None = None
    if warn_mixed_thresholds:
        mixed, hashes = detect_mixed_thresholds(all_summaries)
        meta["mixed_thresholds"] = mixed
        meta["thresholds_hashes_seen"] = hashes
        if mixed:
            mixed_warning = f"WARNING: mixed thresholds detected across fleet: {hashes}"

    if dual:
        human_format = output_format if output_format != "json" else "pretty"
        human_output = get_renderer(human_format).render(summaries, meta=meta)
        json_output = get_renderer("json").render(summaries, meta=meta)
        if mixed_warning and human_format != "json":
            typer.echo(mixed_warning)
        typer.echo(human_output)
        typer.echo("")
        typer.echo(json_output)
    else:
        renderer = get_renderer(output_format)
        if mixed_warning and output_format != "json":
            typer.echo(mixed_warning)
        typer.echo(renderer.render(summaries, meta=meta))

    _maybe_exit_by_health(
        summaries=summaries,
        only_degraded=only_degraded,
        only_unhealthy=only_unhealthy,
    )


@app.command("watch")
def watch(
    spool: str | None = typer.Option(
        None,
        "--spool",
        help="Path to JSONL spool file (single node).",
    ),
    dir_path: str | None = typer.Option(
        None,
        "--dir",
        help="Directory containing spool files (fleet).",
    ),
    glob: str = typer.Option(
        "*.jsonl",
        "--glob",
        help="Glob pattern for spool files (used with --dir).",
    ),
    output_format: str = typer.Option(
        "pretty",
        "--format",
        help="Output format: text, pretty, table, or explain.",
    ),
    interval: int = typer.Option(
        5,
        "--interval",
        help="Refresh interval in seconds.",
        min=1,
    ),
    tail: int = typer.Option(
        200,
        "--tail",
        help="Number of reports to summarize from the end.",
    ),
    top_k_reasons: int = typer.Option(
        5,
        "--top-k-reasons",
        help="Maximum number of reasons to display per node.",
    ),
) -> None:
    """
    Live-refreshing terminal view of node or fleet health.

    Clears and repaints the terminal at a fixed interval using ANSI
    escape sequences. Press Ctrl+C to exit.
    """
    if output_format not in {"text", "pretty", "table", "explain"}:
        raise typer.BadParameter("--format must be text, pretty, table, or explain")

    if spool is None and dir_path is None:
        raise typer.BadParameter("Provide --spool or --dir")

    if spool and dir_path:
        raise typer.BadParameter("--spool and --dir are mutually exclusive")

    renderer = get_renderer(output_format)

    def _build_output() -> str:
        if spool:
            path = Path(spool)
            reports, invalid_count = tail_jsonl_with_stats(path, tail)
            all_summaries = summarize_by_node(reports, top_k_reasons=top_k_reasons)
            meta = {
                "spool_path": str(path),
                "tail_n": tail,
                "nodes_seen_tail": len(all_summaries),
                "nodes_emitted": len(all_summaries),
                "reports_parsed": len(reports),
                "reports_invalid": invalid_count,
                "computed_at": datetime.now(timezone.utc).isoformat(),
            }
            return renderer.render(all_summaries, meta=meta)
        else:
            root = Path(dir_path)  # type: ignore[arg-type]
            files = sorted(root.glob(glob))
            reports: list[dict] = []
            reports_invalid_total = 0
            for fp in files:
                file_reports, invalid_count = tail_jsonl_with_stats(fp, tail)
                reports.extend(file_reports)
                reports_invalid_total += invalid_count
            all_summaries = summarize_by_node(reports, top_k_reasons=top_k_reasons)
            meta = {
                "spool_dir": str(root),
                "tail_n": tail,
                "files_seen": len(files),
                "nodes_seen_tail": len(all_summaries),
                "nodes_emitted": len(all_summaries),
                "reports_parsed": len(reports),
                "reports_invalid": reports_invalid_total,
                "computed_at": datetime.now(timezone.utc).isoformat(),
            }
            return renderer.render(all_summaries, meta=meta)

    try:
        while True:
            # ANSI: clear screen + move cursor to top-left
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
            output = _build_output()
            typer.echo(output)
            typer.echo(f"\n[Refreshing every {interval}s — Ctrl+C to exit]")
            time.sleep(interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    app()
