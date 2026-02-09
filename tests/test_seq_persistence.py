"""
Contract test for sequence persistence across runs
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from agent.main import app


def _read_seqs(spool_path: Path) -> list[int]:
    lines = spool_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line)["timing"]["seq"] for line in lines]


def test_two_oneshots_increment_seq() -> None:
    """
    Two oneshots should produce seq values [1, 2]
    """
    runner = CliRunner()

    with runner.isolated_filesystem():
        result_one = runner.invoke(app, ["oneshot"])
        result_two = runner.invoke(app, ["oneshot"])

        assert result_one.exit_code == 0
        assert result_two.exit_code == 0

        spool_path = Path("spool") / "node_reports.jsonl"
        assert _read_seqs(spool_path) == [1, 2]
