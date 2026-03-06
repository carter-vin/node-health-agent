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

import os
import platform
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import typer

from agent.collectors.cpu import collect_cpu
from agent.collectors.disk import collect_disk
from agent.collectors.heartbeat import collect_heartbeat
from agent.collectors.identity import collect_identity
from agent.collectors.memory import collect_memory
from agent.collectors.network import collect_network
from agent.config import compute_config_hash, load_config
from agent.emit import EmitTargets, emit_report_json
from agent.evaluate import evaluate_health
from agent.model import build_report_from_collectors, report_to_json, utc_now_iso
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
    Collect env details deterministically

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


def _debug_sleep_ms() -> int:
    """
    Optional debug sleep to force overruns during tests
    """
    value = os.getenv("NODE_AGENT_DEBUG_SLEEP_MS")
    if not value:
        return 0
    try:
        delay_ms = int(value)
    except ValueError:
        return 0
    return max(0, delay_ms)


# -----------------------------
# ROOT COMMAND BEHAVIOR
# -----------------------------
@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """
    Root command behavior

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

    # Set version and runtime details
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
    spool_max_bytes: int | None = typer.Option(
        None,
        "--spool-max-bytes",
        help="Rotate spool when it reaches this size in bytes.",
        min=1,
    ),
    spool_rotate_count: int = typer.Option(
        3,
        "--spool-rotate-count",
        help="Number of rotated spool files to keep.",
        min=1,
    ),
    print_report: bool = typer.Option(
        False,
        "--print-report/--no-print-report",
        help="Print report JSON to stdout for debugging.",
    ),
    config_path: str | None = typer.Option(
        None,
        "--config",
        help="Path to JSON config file for threshold overrides.",
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
    - Emission failures raise and exit non-zero
    """

    cfg = load_config(config_path)
    cfg_hash = compute_config_hash(cfg)
    cfg_profile = cfg.get("evaluation", {}).get("profile_name", "default")

    emit_event(
        "agent_start",
        agent_version=AGENT_VERSION,
        mode="oneshot",
        threshold_profile=cfg_profile,
        thresholds_hash=cfg_hash,
        spool_path=spool_path,
        spool_max_bytes=spool_max_bytes,
        spool_rotate_count=spool_rotate_count,
    )

    handled_failure = False
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
        # Collect signals with normalization; reasons drive assessment
        ident_out = run_collector("identity", collect_identity)
        hb_out = run_collector("heartbeat", collect_heartbeat)
        cpu_out = run_collector("cpu", collect_cpu)
        mem_out = run_collector("memory", collect_memory)
        disk_out = run_collector("disk", collect_disk)
        net_out = run_collector("network", collect_network)

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

        if not cpu_out.ok:
            emit_event(
                "collector_failed",
                agent_version=AGENT_VERSION,
                mode="oneshot",
                collector="cpu",
                error_type=cpu_out.error_type,
                message=cpu_out.error_message,
            )
            reasons.append("collector_failed:cpu")

        if not mem_out.ok:
            emit_event(
                "collector_failed",
                agent_version=AGENT_VERSION,
                mode="oneshot",
                collector="memory",
                error_type=mem_out.error_type,
                message=mem_out.error_message,
            )
            reasons.append("collector_failed:memory")

        if not disk_out.ok:
            emit_event(
                "collector_failed",
                agent_version=AGENT_VERSION,
                mode="oneshot",
                collector="disk",
                error_type=disk_out.error_type,
                message=disk_out.error_message,
            )
            reasons.append("collector_failed:disk")

        if not net_out.ok:
            emit_event(
                "collector_failed",
                agent_version=AGENT_VERSION,
                mode="oneshot",
                collector="network",
                error_type=net_out.error_type,
                message=net_out.error_message,
            )
            # network is best-effort; failure does not degrade health

        if not ident_out.ok:
            emit_event(
                "collector_failed",
                agent_version=AGENT_VERSION,
                mode="oneshot",
                collector="identity",
                error_type=ident_out.error_type,
                message=ident_out.error_message,
            )
            handled_failure = True
            # node_id unavailable — cannot emit report
            raise RuntimeError("identity collector failed; cannot emit report")
        elif ident_out.value.boot_id is None:
            emit_event(
                "collector_failed",
                agent_version=AGENT_VERSION,
                mode="oneshot",
                collector="identity",
                error_type="RuntimeError",
                message="boot_id unavailable",
            )
            reasons.append("collector_failed:identity")

        seq = get_seq_for_boot(ident_out.value.boot_id or "")

        health, reasons = evaluate_health(
            cpu_out.value if cpu_out.ok else None,
            mem_out.value if mem_out.ok else None,
            disk_out.value if disk_out.ok else None,
            reasons,
            config=cfg,
        )

        report = build_report_from_collectors(
            ident_out.value,
            emitted_at=utc_now_iso(),
            seq=seq,
            agent_version=AGENT_VERSION,
            heartbeat=hb_out.value if hb_out.ok else None,
            cpu=cpu_out.value if cpu_out.ok else None,
            memory=mem_out.value if mem_out.ok else None,
            disk=disk_out.value if disk_out.ok else None,
            network=net_out.value if net_out.ok else None,
            health=health,
            reasons=reasons,
            threshold_profile=cfg_profile,
            thresholds_hash=cfg_hash,
        )

        report_json = report_to_json(report)

        targets = EmitTargets(
            spool_path=Path(spool_path),
            emit_stdout=print_report,
            spool_max_bytes=spool_max_bytes,
            spool_rotate_count=spool_rotate_count,
        )

        rotation_info = emit_report_json(
            report_json,
            targets,
            on_spool_error=_on_spool_error,
        )
        if rotation_info is not None:
            emit_event(
                "spool_rotated",
                agent_version=AGENT_VERSION,
                mode="oneshot",
                spool_path=rotation_info["spool_path"],
                rotated_to=rotation_info["rotated_to"],
                prior_size_bytes=rotation_info["prior_size_bytes"],
                spool_max_bytes=spool_max_bytes,
                spool_rotate_count=spool_rotate_count,
            )
        commit_seq_after_emit(ident_out.value.boot_id or "", seq)

        emit_event(
            "health_report_emitted",
            agent_version=AGENT_VERSION,
            mode="oneshot",
            seq=seq,
            spool_path=str(targets.spool_path),
            bytes=len(report_json),
        )

    except Exception as e:
        # Avoid double-emitting collector failures for known paths
        if spool_failed or handled_failure:
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
    spool_max_bytes: int | None = typer.Option(
        None,
        "--spool-max-bytes",
        help="Rotate spool when it reaches this size in bytes.",
        min=1,
    ),
    spool_rotate_count: int = typer.Option(
        3,
        "--spool-rotate-count",
        help="Number of rotated spool files to keep.",
        min=1,
    ),
    print_report: bool = typer.Option(
        False,
        "--print-report/--no-print-report",
        help="Print report JSON to stdout for debugging.",
    ),
    config_path: str | None = typer.Option(
        None,
        "--config",
        help="Path to JSON config file for threshold overrides.",
    ),
    max_iterations: int = typer.Option(
        0,
        "--max-iterations",
        help="Stop after N iterations (0 = unlimited).",
        min=0,
    ),
) -> None:
    """
    Run continuous agent loop
    """
    cfg = load_config(config_path)
    cfg_hash = compute_config_hash(cfg)
    cfg_profile = cfg.get("evaluation", {}).get("profile_name", "default")

    _start_fields: dict = dict(
        threshold_profile=cfg_profile,
        thresholds_hash=cfg_hash,
        interval_s=interval,
        spool_path=spool_path,
        spool_max_bytes=spool_max_bytes,
        spool_rotate_count=spool_rotate_count,
    )
    if max_iterations > 0:
        _start_fields["max_iterations"] = max_iterations
    emit_event(
        "agent_start",
        agent_version=AGENT_VERSION,
        mode="run",
        **_start_fields,
    )

    debug_sleep_ms = _debug_sleep_ms()

    targets = EmitTargets(
        spool_path=Path(spool_path),
        emit_stdout=print_report,
        spool_max_bytes=spool_max_bytes,
        spool_rotate_count=spool_rotate_count,
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
        last_tick_start = None
        _iteration = 0
        while True:
            if max_iterations > 0 and _iteration >= max_iterations:
                break
            _iteration += 1
            tick_start = time.monotonic()
            if last_tick_start is None:
                sleep_drift_ms = 0
            else:
                expected = last_tick_start + interval
                sleep_drift_ms = max(0, int((tick_start - expected) * 1000))
            t_collect_done = None
            t_build_done = None
            t_emit_done = None
            seq = None
            node_id = None
            skip_emit = False
            reports_emitted = 0
            collector_durations: dict[str, int] = {}

            try:
                # Collect signals with normalization; reasons drive assessment
                collector_start = time.monotonic()
                ident_out = run_collector("identity", collect_identity)
                collector_durations["identity"] = int((time.monotonic() - collector_start) * 1000)

                collector_start = time.monotonic()
                hb_out = run_collector("heartbeat", collect_heartbeat)
                collector_durations["heartbeat"] = int((time.monotonic() - collector_start) * 1000)

                collector_start = time.monotonic()
                cpu_out = run_collector("cpu", collect_cpu)
                collector_durations["cpu"] = int((time.monotonic() - collector_start) * 1000)

                collector_start = time.monotonic()
                mem_out = run_collector("memory", collect_memory)
                collector_durations["memory"] = int((time.monotonic() - collector_start) * 1000)

                collector_start = time.monotonic()
                disk_out = run_collector("disk", collect_disk)
                collector_durations["disk"] = int((time.monotonic() - collector_start) * 1000)

                collector_start = time.monotonic()
                net_out = run_collector("network", collect_network)
                collector_durations["network"] = int((time.monotonic() - collector_start) * 1000)

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

                if not cpu_out.ok:
                    emit_event(
                        "collector_failed",
                        agent_version=AGENT_VERSION,
                        mode="run",
                        collector="cpu",
                        error_type=cpu_out.error_type,
                        message=cpu_out.error_message,
                    )
                    reasons.append("collector_failed:cpu")

                if not mem_out.ok:
                    emit_event(
                        "collector_failed",
                        agent_version=AGENT_VERSION,
                        mode="run",
                        collector="memory",
                        error_type=mem_out.error_type,
                        message=mem_out.error_message,
                    )
                    reasons.append("collector_failed:memory")

                if not disk_out.ok:
                    emit_event(
                        "collector_failed",
                        agent_version=AGENT_VERSION,
                        mode="run",
                        collector="disk",
                        error_type=disk_out.error_type,
                        message=disk_out.error_message,
                    )
                    reasons.append("collector_failed:disk")

                if not ident_out.ok:
                    emit_event(
                        "collector_failed",
                        agent_version=AGENT_VERSION,
                        mode="run",
                        collector="identity",
                        error_type=ident_out.error_type,
                        message=ident_out.error_message,
                    )
                    # node_id unavailable; skip this tick but keep running
                    skip_emit = True
                else:
                    node_id = ident_out.value.node_id
                    if ident_out.value.boot_id is None:
                        emit_event(
                            "collector_failed",
                            agent_version=AGENT_VERSION,
                            mode="run",
                            collector="identity",
                            error_type="RuntimeError",
                            message="boot_id unavailable",
                        )
                        reasons.append("collector_failed:identity")
                    skip_emit = False

                t_collect_done = time.monotonic()

                if not skip_emit:
                    seq = get_seq_for_boot(ident_out.value.boot_id or "")

                    health, reasons = evaluate_health(
                        cpu_out.value if cpu_out.ok else None,
                        mem_out.value if mem_out.ok else None,
                        disk_out.value if disk_out.ok else None,
                        reasons,
                        config=cfg,
                    )

                    report = build_report_from_collectors(
                        ident_out.value,
                        emitted_at=utc_now_iso(),
                        seq=seq,
                        agent_version=AGENT_VERSION,
                        heartbeat=hb_out.value if hb_out.ok else None,
                        cpu=cpu_out.value if cpu_out.ok else None,
                        memory=mem_out.value if mem_out.ok else None,
                        disk=disk_out.value if disk_out.ok else None,
                        network=net_out.value if net_out.ok else None,
                        health=health,
                        reasons=reasons,
                        threshold_profile=cfg_profile,
                        thresholds_hash=cfg_hash,
                    )

                    report_json = report_to_json(report)
                    t_build_done = time.monotonic()

                    emit_ok = True
                    rotation_info = None
                    try:
                        rotation_info = emit_report_json(
                            report_json,
                            targets,
                            on_spool_error=_on_spool_error,
                        )
                    except Exception:
                        emit_ok = False
                    t_emit_done = time.monotonic()

                    if emit_ok:
                        if rotation_info is not None:
                            emit_event(
                                "spool_rotated",
                                agent_version=AGENT_VERSION,
                                mode="run",
                                spool_path=rotation_info["spool_path"],
                                rotated_to=rotation_info["rotated_to"],
                                prior_size_bytes=rotation_info["prior_size_bytes"],
                                spool_max_bytes=spool_max_bytes,
                                spool_rotate_count=spool_rotate_count,
                            )
                        reports_emitted = 1
                        emit_event(
                            "health_report_emitted",
                            agent_version=AGENT_VERSION,
                            mode="run",
                            seq=seq,
                            spool_path=str(targets.spool_path),
                            bytes=len(report_json),
                        )

                        commit_seq_after_emit(ident_out.value.boot_id or "", seq)

            except Exception as e:
                emit_event(
                    "collector_failed",
                    agent_version=AGENT_VERSION,
                    mode="run",
                    error_type=type(e).__name__,
                    message=str(e),
                )
                # Keep running; failure visibility is the goal

            if t_collect_done is None:
                # Fallback if collectors threw before timing capture
                t_collect_done = time.monotonic()

            if debug_sleep_ms:
                # Debug hook to force overruns in tests
                time.sleep(debug_sleep_ms / 1000)

            tick_elapsed = time.monotonic() - tick_start
            overrun = tick_elapsed > interval
            sleep_s = max(0.0, interval - tick_elapsed)
            sleep_ms = max(0, int(round(sleep_s * 1000)))

            collect_elapsed_ms = None
            build_elapsed_ms = None
            emit_elapsed_ms = None

            if t_collect_done is not None:
                collect_elapsed_ms = int((t_collect_done - tick_start) * 1000)
            else:
                collect_elapsed_ms = 0

            if t_build_done is not None and t_collect_done is not None:
                build_elapsed_ms = int((t_build_done - t_collect_done) * 1000)

            if t_emit_done is not None and t_build_done is not None:
                emit_elapsed_ms = int((t_emit_done - t_build_done) * 1000)

            tick_event = {
                "interval_s": interval,
                "tick_elapsed_ms": int(tick_elapsed * 1000),
                "collect_elapsed_ms": collect_elapsed_ms,
                "sleep_ms": sleep_ms,
                "overrun": overrun,
                "reports_emitted": reports_emitted,
            }

            if build_elapsed_ms is not None:
                tick_event["build_elapsed_ms"] = build_elapsed_ms

            if emit_elapsed_ms is not None:
                tick_event["emit_elapsed_ms"] = emit_elapsed_ms

            if seq is not None:
                tick_event["seq"] = seq

            if node_id is not None:
                tick_event["node_id"] = node_id

            if skip_emit:
                tick_event["skip_emit"] = True

            emit_event(
                "agent_tick",
                agent_version=AGENT_VERSION,
                mode="run",
                **tick_event,
            )

            collector_total_ms = sum(collector_durations.values())
            slowest_collector_name = None
            slowest_collector_ms = None
            if collector_durations:
                slowest_collector_name = max(collector_durations, key=collector_durations.get)
                slowest_collector_ms = collector_durations[slowest_collector_name]

            metrics_event = {
                "interval_s": interval,
                "tick_duration_ms": int(tick_elapsed * 1000),
                "sleep_drift_ms": sleep_drift_ms,
                "overrun": overrun,
                "collector_total_ms": collector_total_ms,
            }

            if slowest_collector_name is not None:
                metrics_event["slowest_collector_name"] = slowest_collector_name
            if slowest_collector_ms is not None:
                metrics_event["slowest_collector_ms"] = slowest_collector_ms

            emit_event(
                "agent_tick_metrics",
                agent_version=AGENT_VERSION,
                mode="run",
                **metrics_event,
            )

            last_tick_start = tick_start

            if sleep_ms:
                time.sleep(sleep_ms / 1000)

    except KeyboardInterrupt:
        # Graceful shutdown on Ctrl+C
        pass

    finally:
        emit_event(
            "agent_shutdown",
            agent_version=AGENT_VERSION,
            mode="run",
        )


@app.command("config")
def config_cmd(
    config_path: str | None = typer.Option(
        None,
        "--config",
        help="Path to JSON config file for threshold overrides.",
    ),
    output_format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text or json.",
    ),
) -> None:
    """
    Print the fully-resolved effective configuration.

    Shows each threshold value with its source (default, env, or file)
    and validates that threshold coherence is maintained.
    """
    import json as _json

    if output_format not in {"text", "json"}:
        raise typer.BadParameter("--format must be text or json")

    from agent.config import _DEFAULTS, _ENV_OVERRIDES

    # Load with defaults only (no file, no env) to identify defaults
    defaults_cfg = _DEFAULTS

    # Load with file but no env to identify file overrides
    file_cfg: dict[str, Any] = {}
    if config_path:
        try:
            from agent.config import normalize_config as _normalize
            import json as _j
            payload = _j.loads(Path(config_path).read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                file_cfg = _normalize(payload)
        except Exception:
            pass

    # Final resolved config (defaults → file → env)
    cfg = load_config(config_path)
    cfg_hash = compute_config_hash(cfg)

    # Determine source for each key
    def _source(section: str, key: str) -> str:
        env_var = next(
            (e for e, (s, k, _) in _ENV_OVERRIDES.items() if s == section and k == key),
            None,
        )
        if env_var and os.getenv(env_var) is not None:
            return f"env: {env_var}"
        if file_cfg and file_cfg.get(section, {}).get(key) != _DEFAULTS.get(section, {}).get(key):
            return f"file: {config_path}"
        return "default"

    if output_format == "json":
        payload: dict[str, Any] = {
            "config_hash": cfg_hash,
            "config_path": config_path,
            "thresholds": {},
        }
        for section in ("cpu", "mem", "disk"):
            for key, value in cfg[section].items():
                fq_key = f"{section}.{key}"
                payload["thresholds"][fq_key] = {
                    "value": value,
                    "source": _source(section, key),
                }
        payload["validation"] = "OK"
        typer.echo(_json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return

    # Text output
    lines: list[str] = [
        f"config_hash: {cfg_hash}",
        f"config_path: {config_path or 'none'}",
        "",
    ]

    for section in ("cpu", "mem", "disk"):
        for key, value in sorted(cfg[section].items()):
            src = _source(section, key)
            src_tag = f"  ({src})" if src != "default" else ""
            lines.append(f"{section}.{key}: {value}{src_tag}")

    lines.append("")
    lines.append("validation: OK")
    typer.echo("\n".join(lines))


if __name__ == "__main__":
    app()
