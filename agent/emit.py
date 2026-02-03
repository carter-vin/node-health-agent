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

    # Open in append mode; create if missing.
    with spool_path.open(mode="a", encoding="utf-8", newline="\n") as f:
        f.write(line)
        f.write("\n")
        f.flush()  

def emit_report_json(report_json: str, targets: EmitTargets) -> None:
    """
    Emit a report JSON string to configured targets.

    Why this exists:
    - Ensures stdout and spool behavior stays consistent across modes
    - Centralizes "where do reports go?" logic

    report_json:
    - must be a single JSON object string (no trailing newline)
    """
    if targets.emit_stdout:
        # stdout emission is primarily for local debugging and demos.
        print(report_json)

    append_jsonl_line(targets.spool_path, report_json)
