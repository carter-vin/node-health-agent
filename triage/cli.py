"""
triage.cli
AUTHOR: carter-vin

Minimal triage CLI for local operator workflows
"""

from __future__ import annotations

from pathlib import Path

import typer

from triage.read import tail_jsonl
from triage.summarize import summarize_reports


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
) -> None:
    """
    Summarize the spool in a deterministic, plain-text format
    """
    path = Path(spool)
    reports = tail_jsonl(path, tail)
    typer.echo(summarize_reports(reports))


if __name__ == "__main__":
    app()
