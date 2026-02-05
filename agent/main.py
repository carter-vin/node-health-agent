"""
agent.main
------------
AUTHOR: carter-vin

v0.1 PURPOSE:
- Prove the project installs and runs correctly
- Establish a stable CLI entrypoint
- Provide environment visibility for operators and debugging

Key contract:
- `node-health-agent --help` shows a Commands section.
- `node-health-agent version` executes the version subcommand.
"""

from __future__ import annotations

import platform
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import typer

from agent.collectors.heartbeat import collect_heartbeat
from agent.collectors.identity import collect_identity
from agent.emit import EmitTargets, emit_report_json
from agent.model import build_report_from_collectors, report_to_json
from agent.logging import emit_event
from agent.state import commit_seq_after_emit, get_seq_for_boot

# Explicit multi-command CLI
app = typer.Typer(
    add_completion=False,
    help="node-health-agent: node-local health reporting tool",
)

AGENT_VERSION = "0.1.0"

# -----------------------------
# DATA CLASSES
# -----------------------------
@dataclass(frozen=True)
class EnvironmentInfo:
    """
    Snapshot of the runtime environment
    - info partial evidence bundle (future)
    - help correlate issues across hosts and times
    """

    python_version: str
    os: str
    machine: str
    utc_now: str


def collect_environment_info() -> EnvironmentInfo:
    """
    Collect env details (deterministicly)

    Note:
    - utc_now intentionally dynamic to reflect current time
    - other fields intended stable per host/runtime
    """
    return EnvironmentInfo(
        python_version=sys.version.split()[0],
        os=f"{platform.system()} {platform.release()}",
        machine=platform.machine(),
        utc_now=datetime.now(timezone.utc).isoformat(),
    )

# -----------------------------
# ROOT COMMAND BEHAVIOR
# -----------------------------
@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """
    Root command behavior.

    If no subcommand is provided:
    - print a short hint
    - exit with code 0 (or 2 if you prefer strict usage enforcement)

    This makes the CLI feel intentional and avoids "nothing happens" confusion.
    """
    if ctx.invoked_subcommand is None:
        typer.echo("No command provided. Try: node-health-agent --help")


# -----------------------------
# CLI COMMANDS
# -----------------------------
@app.command()
def version() -> None:
    """
    Print agent version & runtime env
    """
    env = collect_environment_info() 

    #set/print version & env details
    typer.echo(f"node-health-agent v{AGENT_VERSION}")
    typer.echo(f"python={env.python_version}")
    typer.echo(f"os={env.os}")
    typer.echo(f"machine={env.machine}")
    typer.echo(f"utc_now={env.utc_now}")


@app.command("oneshot")
def oneshot(
    interval: int = typer.Option(
        0,
        help="Unused in oneshot (reserved for parity with daemon mode).",
    ),
    spool_path: str = typer.Option(
        "spool/node_reports.jsonl",
        help="Path to JSONL spool file for report emission.",
    ),
    no_stdout: bool = typer.Option(
        False,
        "--no-stdout",
        help="Disable printing the report JSON to stdout.",
    ),
) -> None:
    """
    Emit single report and exit

    This is a deterministic harness for validating:
    - collectors work
    - schema assembly works
    - JSON serialization works
    - emission to spool works

    Failure semantics:
    - if emission fails, Typer will raise and exit non-zero (good for ops scripts)
    """

    emit_event(
        "agent_start",
        agent_version=AGENT_VERSION,
        mode="oneshot",
        spool_path=spool_path,
    )

    try:
        # Collect signals (Phase 1B)
        ident = collect_identity()
        seq = get_seq_for_boot(ident.boot_id)
        hb = collect_heartbeat()

        from agent.model import utc_now_iso  # local import avoids circular patterns

        report = build_report_from_collectors(
            ident,
            hb,
            emitted_at=utc_now_iso(),
            seq=seq,
            agent_version=AGENT_VERSION,
        )

        report_json = report_to_json(report)

        targets = EmitTargets(
            spool_path=Path(spool_path),
            emit_stdout=not no_stdout,
        )

        emit_report_json(report_json, targets)
        commit_seq_after_emit(ident.boot_id, seq)

        emit_event(
            "health_report_emitted",
            agent_version=AGENT_VERSION,
            mode="oneshot",
            seq=seq,
            spool_path=str(targets.spool_path),
            bytes=len(report_json),
        )

    except Exception as e:
        # Collector vs spool distinction can be improved later.
        # For now, surface the failure explicitly in a stable event.
        emit_event(
            "collector_failed",
            agent_version=AGENT_VERSION,
            mode="oneshot",
            error_type=type(e).__name__,
            message=str(e),
        )
        raise

    finally:
        emit_event(
            "agent_shutdown",
            agent_version=AGENT_VERSION,
            mode="oneshot",
        )
     
# run command if invoked directly
@app.command("run")
def run(
    interval: int = typer.Option(
        2,
        help="Emit health reports at a fixed interval (seconds).",
        min=1,
    ),
    spool_path: str = typer.Option(
        "spool/node_reports.jsonl",
        help="Path to JSONL spool file for report emission.",
    ),
    no_stdout: bool = typer.Option(
        False,
        "--no-stdout",
        help="Disable printing the report JSON to stdout.",
    ),
) -> None:
    """
    Run continuous agent loop.
    """
    emit_event(
        "agent_start",
        agent_version=AGENT_VERSION,
        mode="run",
        interval_s=interval,
        spool_path=spool_path,
    )

    targets = EmitTargets(
        spool_path=Path(spool_path),
        emit_stdout=not no_stdout,
    )

    try:
        while True:
            start = time.monotonic()

            try:
                ident = collect_identity()
                seq = get_seq_for_boot(ident.boot_id)
                hb = collect_heartbeat()

                from agent.model import utc_now_iso

                report = build_report_from_collectors(
                    ident,
                    hb,
                    emitted_at=utc_now_iso(),
                    seq=seq,
                    agent_version=AGENT_VERSION,
                )

                report_json = report_to_json(report)
                emit_report_json(report_json, targets)

                emit_event(
                    "health_report_emitted",
                    agent_version=AGENT_VERSION,
                    mode="run",
                    seq=seq,
                    spool_path=str(targets.spool_path),
                    bytes=len(report_json),
                )

                commit_seq_after_emit(ident.boot_id, seq)

            except Exception as e:
                emit_event(
                    "collector_failed",
                    agent_version=AGENT_VERSION,
                    mode="run",
                    error_type=type(e).__name__,
                    message=str(e),
                )
                # Keep running; failure visibility is the goal.

            elapsed = time.monotonic() - start
            sleep_s = max(0.0, interval - elapsed)
            time.sleep(sleep_s)

    except KeyboardInterrupt:
        # Graceful shutdown on Ctrl+C
        pass

    finally:
        emit_event(
            "agent_shutdown",
            agent_version=AGENT_VERSION,
            mode="run",
        )



if __name__ == "__main__":
    app()