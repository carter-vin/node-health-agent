"""
agent.main

CLI entrypoint for node-health-agent.

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
from typing import Any

import typer

from agent.config import compute_config_hash, load_config
from agent.emit import EmitTargets, emit_report_json
from agent.logging import emit_event
from agent.runtime import (
    CollectorResults,
    build_report_json,
    collect_all,
    collect_all_timed,
    emit_failure_events,
)
from agent.state import commit_seq_after_emit, get_seq_for_boot

app = typer.Typer(
    add_completion=False,
    help="node-health-agent: node-local health reporting tool",
)

AGENT_VERSION = "0.1.0"


@dataclass(frozen=True)
class EnvironmentInfo:
    python_version: str
    os: str
    machine: str
    utc_now: str


def collect_environment_info() -> EnvironmentInfo:
    return EnvironmentInfo(
        python_version=sys.version.split()[0],
        os=f"{platform.system()} {platform.release()}",
        machine=platform.machine(),
        utc_now=datetime.now(timezone.utc).isoformat(),
    )


def _debug_sleep_ms() -> int:
    value = os.getenv("NODE_AGENT_DEBUG_SLEEP_MS")
    if not value:
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        return 0


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo("No command provided. Try: node-health-agent --help")


@app.command()
def version() -> None:
    """Print agent version & runtime env."""
    env = collect_environment_info()
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
    """Emit single report and exit."""
    cfg = load_config(config_path)
    cfg_hash = compute_config_hash(cfg)
    cfg_profile = cfg.get("evaluation", {}).get("profile_name", "default")

    emit_event(
        "agent_start",
        agent_version=AGENT_VERSION,
        mode="oneshot",
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
        results = collect_all()
        reasons = emit_failure_events("oneshot", results, agent_version=AGENT_VERSION)

        # Network is best-effort: emit event only, no reason appended.
        if not results.network.ok:
            emit_event(
                "collector_failed",
                agent_version=AGENT_VERSION,
                mode="oneshot",
                collector="network",
                error_type=results.network.error_type,
                message=results.network.error_message,
            )

        # Identity failure is fatal in oneshot: node_id unavailable.
        if not results.ident.ok:
            emit_event(
                "collector_failed",
                agent_version=AGENT_VERSION,
                mode="oneshot",
                collector="identity",
                error_type=results.ident.error_type,
                message=results.ident.error_message,
            )
            handled_failure = True
            raise RuntimeError("identity collector failed; cannot emit report")
        elif results.ident.value.boot_id is None:
            emit_event(
                "collector_failed",
                agent_version=AGENT_VERSION,
                mode="oneshot",
                collector="identity",
                error_type="RuntimeError",
                message="boot_id unavailable",
            )
            reasons.append("collector_failed:identity")

        seq = get_seq_for_boot(results.ident.value.boot_id or "")
        report_json = build_report_json(
            results.ident.value,
            seq,
            results,
            reasons,
            cfg=cfg,
            cfg_profile=cfg_profile,
            cfg_hash=cfg_hash,
            agent_version=AGENT_VERSION,
        )

        targets = EmitTargets(
            spool_path=Path(spool_path),
            emit_stdout=print_report,
            spool_max_bytes=spool_max_bytes,
            spool_rotate_count=spool_rotate_count,
        )

        rotation_info = emit_report_json(report_json, targets, on_spool_error=_on_spool_error)
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
        commit_seq_after_emit(results.ident.value.boot_id or "", seq)
        emit_event(
            "health_report_emitted",
            agent_version=AGENT_VERSION,
            mode="oneshot",
            seq=seq,
            spool_path=str(targets.spool_path),
            bytes=len(report_json),
        )

    except Exception as e:
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
        emit_event("agent_shutdown", agent_version=AGENT_VERSION, mode="oneshot")


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
) -> None:
    """Run continuous agent loop."""
    cfg = load_config(config_path)
    cfg_hash = compute_config_hash(cfg)
    cfg_profile = cfg.get("evaluation", {}).get("profile_name", "default")

    emit_event(
        "agent_start",
        agent_version=AGENT_VERSION,
        mode="run",
        interval_s=interval,
        spool_path=spool_path,
        spool_max_bytes=spool_max_bytes,
        spool_rotate_count=spool_rotate_count,
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
        while True:
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

            try:
                results, collector_durations = collect_all_timed()
                reasons = emit_failure_events("run", results, agent_version=AGENT_VERSION)

                # Identity failure in run: skip this tick, keep running.
                if not results.ident.ok:
                    emit_event(
                        "collector_failed",
                        agent_version=AGENT_VERSION,
                        mode="run",
                        collector="identity",
                        error_type=results.ident.error_type,
                        message=results.ident.error_message,
                    )
                    skip_emit = True
                else:
                    node_id = results.ident.value.node_id
                    if results.ident.value.boot_id is None:
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
                    seq = get_seq_for_boot(results.ident.value.boot_id or "")
                    report_json = build_report_json(
                        results.ident.value,
                        seq,
                        results,
                        reasons,
                        cfg=cfg,
                        cfg_profile=cfg_profile,
                        cfg_hash=cfg_hash,
                        agent_version=AGENT_VERSION,
                    )
                    t_build_done = time.monotonic()

                    emit_ok = True
                    rotation_info = None
                    try:
                        rotation_info = emit_report_json(
                            report_json, targets, on_spool_error=_on_spool_error
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
                        commit_seq_after_emit(results.ident.value.boot_id or "", seq)

            except Exception as e:
                emit_event(
                    "collector_failed",
                    agent_version=AGENT_VERSION,
                    mode="run",
                    error_type=type(e).__name__,
                    message=str(e),
                )

            if t_collect_done is None:
                t_collect_done = time.monotonic()

            if debug_sleep_ms:
                time.sleep(debug_sleep_ms / 1000)

            tick_elapsed = time.monotonic() - tick_start
            overrun = tick_elapsed > interval
            sleep_s = max(0.0, interval - tick_elapsed)
            sleep_ms = max(0, int(round(sleep_s * 1000)))

            collect_elapsed_ms = int((t_collect_done - tick_start) * 1000)
            build_elapsed_ms = (
                int((t_build_done - t_collect_done) * 1000)
                if t_build_done is not None and t_collect_done is not None
                else None
            )
            emit_elapsed_ms = (
                int((t_emit_done - t_build_done) * 1000)
                if t_emit_done is not None and t_build_done is not None
                else None
            )

            tick_event: dict[str, Any] = {
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

            emit_event("agent_tick", agent_version=AGENT_VERSION, mode="run", **tick_event)

            collector_total_ms = sum(collector_durations.values())
            slowest = max(collector_durations, key=collector_durations.get)  # type: ignore[arg-type]
            metrics_event: dict[str, Any] = {
                "interval_s": interval,
                "tick_duration_ms": int(tick_elapsed * 1000),
                "sleep_drift_ms": sleep_drift_ms,
                "overrun": overrun,
                "collector_total_ms": collector_total_ms,
                "slowest_collector_name": slowest,
                "slowest_collector_ms": collector_durations[slowest],
            }
            emit_event(
                "agent_tick_metrics", agent_version=AGENT_VERSION, mode="run", **metrics_event
            )

            last_tick_start = tick_start
            if sleep_ms:
                time.sleep(sleep_ms / 1000)

    except KeyboardInterrupt:
        pass

    finally:
        emit_event("agent_shutdown", agent_version=AGENT_VERSION, mode="run")


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
    """Print the fully-resolved effective configuration."""
    import json as _json

    if output_format not in {"text", "json"}:
        raise typer.BadParameter("--format must be text or json")

    from agent.config import _DEFAULTS, _ENV_OVERRIDES

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

    cfg = load_config(config_path)
    cfg_hash = compute_config_hash(cfg)

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
