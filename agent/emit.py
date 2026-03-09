"""
agent.emit

Append-only JSONL spool writer with optional rotation.

Creates spool directory on first write. Flushes after each line so
tailing consumers see updates immediately.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


DEFAULT_SPOOL_DIR = Path("spool")
DEFAULT_SPOOL_FILE = DEFAULT_SPOOL_DIR / "node_reports.jsonl"


@dataclass(frozen=True)
class EmitTargets:
    spool_path: Path = DEFAULT_SPOOL_FILE
    emit_stdout: bool = False
    spool_max_bytes: int | None = None
    spool_rotate_count: int = 3


def _rotation_path(spool_path: Path, index: int) -> Path:
    return spool_path.with_name(f"{spool_path.stem}.{index}{spool_path.suffix}")


def maybe_rotate_spool(targets: EmitTargets) -> dict[str, object] | None:
    """Rotate the spool when it exceeds spool_max_bytes. Returns rotation info or None."""
    if targets.spool_max_bytes is None or targets.spool_max_bytes <= 0:
        return None

    if targets.spool_rotate_count < 1:
        return None

    if not targets.spool_path.exists():
        return None

    if targets.spool_path.stat().st_size < targets.spool_max_bytes:
        return None

    # Rotate oldest first to keep shifts deterministic
    for index in range(targets.spool_rotate_count, 1, -1):
        src = _rotation_path(targets.spool_path, index - 1)
        dst = _rotation_path(targets.spool_path, index)
        if dst.exists():
            dst.unlink()
        if src.exists():
            src.rename(dst)

    prior_size_bytes = targets.spool_path.stat().st_size
    first = _rotation_path(targets.spool_path, 1)
    if first.exists():
        first.unlink()
    targets.spool_path.rename(first)
    return {
        "spool_path": str(targets.spool_path),
        "rotated_to": str(first),
        "prior_size_bytes": prior_size_bytes,
    }


def append_jsonl_line(spool_path: Path, line: str) -> None:
    """Append one JSON line to the spool. Raises on IO errors."""
    spool_path.parent.mkdir(parents=True, exist_ok=True)
    with spool_path.open(mode="a", encoding="utf-8", newline="\n") as f:
        f.write(line)
        f.write("\n")
        f.flush()


def emit_report_json(
    report_json: str,
    targets: EmitTargets,
    *,
    on_spool_error: Optional[Callable[[Exception, Path], None]] = None,
) -> dict[str, object] | None:
    """Emit report JSON to configured targets. Returns rotation info if rotation occurred."""
    if targets.emit_stdout:
        print(report_json)

    try:
        rotation_info = maybe_rotate_spool(targets)
        append_jsonl_line(targets.spool_path, report_json)
        return rotation_info
    except Exception as e:
        if on_spool_error is not None:
            on_spool_error(e, targets.spool_path)
        raise
