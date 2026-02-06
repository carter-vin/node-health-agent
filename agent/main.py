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

from agent.collectors.heartbeat import HeartbeatResult, collect_heartbeat
from agent.collectors.identity import collect_identity
from agent.emit import EmitTargets, emit_report_json
from agent.model import build_report_from_collectors, report_to_json
from agent.logging import emit_event
from agent.state import commit_seq_after_emit, get_seq_for_boot
from agent.collectors.base import run_collector

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

    spool_failed = False

    def _on_spool_error(e: Exception, path: Path) -> None:
        nonlocal spool_failed
        spool_failed = True
        emit_event(
            "spool_write_failed",
            agent_version=AGENT_VERSION,
            mode="oneshot",
            spool_path=str(path),
            error_type=type(e).__name__,
            message=str(e),
        )

    try:
        # Collect signals with normalization; reasons drive assessment.
        ident_out = run_collector("identity", collect_identity)
        hb_out = run_collector("heartbeat", collect_heartbeat)

        reasons: list[str] = []

        if not hb_out.ok:
            emit_event(
                "collector_failed",
                agent_version=AGENT_VERSION,
                mode="oneshot",
                collector="heartbeat",
                error_type=hb_out.error_type,
                message=hb_out.error_message,
            )
            reasons.append("collector_failed:heartbeat")

        if not ident_out.ok:
            emit_event(
                "collector_failed",
                agent_version=AGENT_VERSION,
                mode="oneshot",
                collector="identity",
                error_type=ident_out.error_type,
                message=ident_out.error_message,
            )
            # Identity is required for the current report schema.
            raise RuntimeError("identity collector failed; cannot emit report")

        seq = get_seq_for_boot(ident_out.value.boot_id)

        from agent.model import utc_now_iso  # local import avoids circular patterns

        health = "DEGRADED" if reasons else "OK"

        report = build_report_from_collectors(
            ident_out.value,
            hb_out.value if hb_out.ok else HeartbeatResult(heartbeat_ok=False),
            emitted_at=utc_now_iso(),
            seq=seq,
            agent_version=AGENT_VERSION,
            health=health,
            reasons=reasons,
        )

        report_json = report_to_json(report)

        targets = EmitTargets(
            spool_path=Path(spool_path),
            emit_stdout=not no_stdout,
        )

        emit_report_json(report_json, targets, on_spool_error=_on_spool_error)
        commit_seq_after_emit(ident_out.value.boot_id, seq)

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
        if spool_failed:
            raise
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

    def _on_spool_error(e: Exception, path: Path) -> None:
        emit_event(
            "spool_write_failed",
            agent_version=AGENT_VERSION,
            mode="run",
            spool_path=str(path),
            error_type=type(e).__name__,
            message=str(e),
        )

    try:
        while True:
            start = time.monotonic()

            try:
                # Collect signals with normalization; reasons drive assessment.
                ident_out = run_collector("identity", collect_identity)
                hb_out = run_collector("heartbeat", collect_heartbeat)

                reasons: list[str] = []

                if not hb_out.ok:
                    emit_event(
                        "collector_failed",
                        agent_version=AGENT_VERSION,
                        mode="run",
                        collector="heartbeat",
                        error_type=hb_out.error_type,
                        message=hb_out.error_message,
                    )
                    reasons.append("collector_failed:heartbeat")

                if not ident_out.ok:
                    emit_event(
                        "collector_failed",
                        agent_version=AGENT_VERSION,
                        mode="run",
                        collector="identity",
                        error_type=ident_out.error_type,
                        message=ident_out.error_message,
                    )
                    # Identity is required; skip emission and continue.
                    raise RuntimeError("identity collector failed; skipping emit")

                seq = get_seq_for_boot(ident_out.value.boot_id)

                from agent.model import utc_now_iso

                health = "DEGRADED" if reasons else "OK"

                report = build_report_from_collectors(
                    ident_out.value,
                    hb_out.value if hb_out.ok else HeartbeatResult(heartbeat_ok=False),
                    emitted_at=utc_now_iso(),
                    seq=seq,
                    agent_version=AGENT_VERSION,
                    health=health,
                    reasons=reasons,
                )

                report_json = report_to_json(report)

                emit_ok = True
                try:
                    emit_report_json(report_json, targets, on_spool_error=_on_spool_error)
                except Exception:
                    emit_ok = False

                if emit_ok:
                    emit_event(
                        "health_report_emitted",
                        agent_version=AGENT_VERSION,
                        mode="run",
                        seq=seq,
                        spool_path=str(targets.spool_path),
                        bytes=len(report_json),
                    )

                    commit_seq_after_emit(ident_out.value.boot_id, seq)

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