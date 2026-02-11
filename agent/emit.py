"""
agent.emit

AUTHOR: carter-vin

OUTPUT:
- JSON Lines spool file
- one JSON object per line
- append-only

Design goals:
- Create spool directory if missing
- Append one line per report
- Flush per write so tail/ingest can see updates immediately
- Provide explicit error surfaces (do not silently drop data)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


DEFAULT_SPOOL_DIR = Path("spool")
DEFAULT_SPOOL_FILE = DEFAULT_SPOOL_DIR / "node_reports.jsonl"


@dataclass(frozen=True)
class EmitTargets:
    """
    Emission destination configuration.

    We keep this as a dataclass so:
    - it's explicit in call sites
    - it becomes easy to extend later (rotations, per-node files, etc.)
    """

    spool_path: Path = DEFAULT_SPOOL_FILE
    emit_stdout: bool = True
    spool_max_bytes: int | None = None
    spool_rotate_count: int = 3


def _rotation_path(spool_path: Path, index: int) -> Path:
    """
    Build rotation path with numeric suffix
    """
    return spool_path.with_name(f"{spool_path.stem}.{index}{spool_path.suffix}")


def maybe_rotate_spool(targets: EmitTargets) -> None:
    """
    Rotate spool file when it exceeds max size
    """
    if targets.spool_max_bytes is None or targets.spool_max_bytes <= 0:
        return

    if targets.spool_rotate_count < 1:
        return

    if not targets.spool_path.exists():
        return

    if targets.spool_path.stat().st_size < targets.spool_max_bytes:
        return

    # Rotate oldest first to keep shifts deterministic
    for index in range(targets.spool_rotate_count, 1, -1):
        src = _rotation_path(targets.spool_path, index - 1)
        dst = _rotation_path(targets.spool_path, index)
        if dst.exists():
            dst.unlink()
        if src.exists():
            src.rename(dst)

    first = _rotation_path(targets.spool_path, 1)
    if first.exists():
        first.unlink()
    targets.spool_path.rename(first)


def append_jsonl_line(spool_path: Path, line: str) -> None:
    """
    Append a single JSON string as one JSONL line.

    Contract:
    - 'line' must already be valid JSON (single object)
    - this function adds exactly one trailing newline

    Failure semantics:
    - raises on IO errors; caller decides how to handle (oneshot exits non-zero)
    """
    spool_path.parent.mkdir(parents=True, exist_ok=True)

    # Open in append mode; create if missing
    with spool_path.open(mode="a", encoding="utf-8", newline="\n") as f:
        f.write(line)
        f.write("\n")
        f.flush()


def emit_report_json(
    report_json: str,
    targets: EmitTargets,
    *,
    on_spool_error: Optional[Callable[[Exception, Path], None]] = None,
) -> None:
    """
    Emit a report JSON string to configured targets.

    Why this exists:
    - Ensures stdout and spool behavior stays consistent across modes
    - Centralizes "where do reports go?" logic

    report_json:
    - must be a single JSON object string (no trailing newline)
    """
    if targets.emit_stdout:
        # Stdout emission is primarily for local debugging and demos
        print(report_json)

    try:
        maybe_rotate_spool(targets)
        append_jsonl_line(targets.spool_path, report_json)
    except Exception as e:
        # Callback allows the caller to surface spool errors without coupling modules
        if on_spool_error is not None:
            on_spool_error(e, targets.spool_path)
        raise
