"""
Contract test for spool rotation behavior
"""

from pathlib import Path

from agent.emit import EmitTargets, emit_report_json


def test_spool_rotation_creates_rotated_files(tmp_path: Path) -> None:
    """
    Spool rotates when max bytes threshold is reached
    """
    spool_path = tmp_path / "node_reports.jsonl"
    spool_path.write_text("x" * 200, encoding="utf-8")

    targets = EmitTargets(
        spool_path=spool_path,
        emit_stdout=False,
        spool_max_bytes=100,
        spool_rotate_count=2,
    )

    emit_report_json("{}", targets)

    rotated = tmp_path / "node_reports.1.jsonl"
    assert rotated.exists()
    assert rotated.read_text(encoding="utf-8") == "x" * 200

    current = spool_path.read_text(encoding="utf-8")
    assert current == "{}\n"
