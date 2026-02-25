"""
Contract tests for scripts/validate_spool.py.

Rules:
- Valid v1 reports pass with no errors
- Invalid reports produce clear per-field error messages
- Missing spool raises FileNotFoundError
- Validates all required v1 fields: keys, health enum, schema_version, timestamp, seq, node_id
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the script module without installing it as a package
# ---------------------------------------------------------------------------

def _load_validate_module():
    spec = importlib.util.spec_from_file_location(
        "validate_spool",
        Path(__file__).parent.parent / "scripts" / "validate_spool.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_validate_module()
validate_report = _mod.validate_report
validate_spool = _mod.validate_spool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_REPORT: dict = {
    "assessment": {"health": "OK", "reasons": []},
    "identity": {"node_id": "test-node", "boot_id": "boot-abc"},
    "meta": {"agent_version": "0.1.0", "schema_version": "1"},
    "signals": {"heartbeat_ok": True},
    "timing": {"emitted_at": "2026-01-01T00:00:00+00:00", "seq": 1},
}


def _patch(base: dict, **overrides) -> dict:
    """Deep-copy a base dict with nested key overrides using dot notation."""
    import copy
    result = copy.deepcopy(base)
    for dotted_key, value in overrides.items():
        parts = dotted_key.split(".", 1)
        if len(parts) == 2:
            section, key = parts
            result[section][key] = value
        else:
            result[dotted_key] = value
    return result


def _drop(base: dict, dotted_key: str) -> dict:
    """Deep-copy base dict with a key removed."""
    import copy
    result = copy.deepcopy(base)
    parts = dotted_key.split(".", 1)
    if len(parts) == 2:
        section, key = parts
        result[section].pop(key, None)
    else:
        result.pop(dotted_key, None)
    return result


# ---------------------------------------------------------------------------
# validate_report — valid
# ---------------------------------------------------------------------------

def test_valid_report_produces_no_errors() -> None:
    errors = validate_report(VALID_REPORT, 1)
    assert errors == [], f"Unexpected errors: {errors}"


def test_valid_report_degraded() -> None:
    report = _patch(VALID_REPORT,
                    **{"assessment.health": "DEGRADED",
                       "assessment.reasons": ["collector_failed:heartbeat"]})
    errors = validate_report(report, 1)
    assert errors == []


def test_valid_report_without_boot_id() -> None:
    """boot_id is optional (best-effort)."""
    report = _drop(VALID_REPORT, "identity.boot_id")
    errors = validate_report(report, 1)
    assert errors == []


# ---------------------------------------------------------------------------
# validate_report — invalid
# ---------------------------------------------------------------------------

def test_missing_top_level_key_produces_error() -> None:
    report = _drop(VALID_REPORT, "assessment")
    errors = validate_report(report, 1)
    assert len(errors) == 1
    assert "missing required keys" in str(errors[0])
    assert "assessment" in str(errors[0])


def test_invalid_health_value_produces_error() -> None:
    report = _patch(VALID_REPORT, **{"assessment.health": "UNKNOWN"})
    errors = validate_report(report, 1)
    assert any("assessment.health" in str(e) for e in errors)


def test_wrong_schema_version_produces_error() -> None:
    report = _patch(VALID_REPORT, **{"meta.schema_version": "2"})
    errors = validate_report(report, 1)
    assert any("schema_version" in str(e) for e in errors)


def test_invalid_timestamp_produces_error() -> None:
    report = _patch(VALID_REPORT, **{"timing.emitted_at": "not-a-timestamp"})
    errors = validate_report(report, 1)
    assert any("emitted_at" in str(e) for e in errors)


def test_seq_below_one_produces_error() -> None:
    report = _patch(VALID_REPORT, **{"timing.seq": 0})
    errors = validate_report(report, 1)
    assert any("seq" in str(e) for e in errors)


def test_empty_node_id_produces_error() -> None:
    report = _patch(VALID_REPORT, **{"identity.node_id": ""})
    errors = validate_report(report, 1)
    assert any("node_id" in str(e) for e in errors)


def test_error_includes_line_number() -> None:
    report = _patch(VALID_REPORT, **{"assessment.health": "BAD"})
    errors = validate_report(report, 42)
    assert all(e.line == 42 for e in errors)


# ---------------------------------------------------------------------------
# validate_spool — integration with real files
# ---------------------------------------------------------------------------

def test_valid_fixture_spool_passes(tmp_path: Path) -> None:
    """A spool with only valid reports returns 0 invalid, 0 errors."""
    spool = tmp_path / "valid.jsonl"
    spool.write_text(json.dumps(VALID_REPORT) + "\n")

    valid, invalid, errors = validate_spool(str(spool), n=200)
    assert invalid == 0
    assert errors == []
    assert valid == 1


def test_existing_fixture_spool_passes() -> None:
    """The canonical fixture spool passes validation."""
    valid, invalid, errors = validate_spool("fixtures/spool_degraded.jsonl", n=200)
    assert invalid == 0, f"Errors: {errors}"


def test_invalid_spool_produces_errors(tmp_path: Path) -> None:
    """A spool with bad health and wrong schema_version fails with clear messages."""
    bad_report = _patch(VALID_REPORT,
                        **{"assessment.health": "BORKED",
                           "meta.schema_version": "99"})
    spool = tmp_path / "bad.jsonl"
    spool.write_text(json.dumps(bad_report) + "\n")

    valid, invalid, errors = validate_spool(str(spool), n=200)
    assert invalid == 1
    assert valid == 0
    assert any("assessment.health" in str(e) for e in errors)
    assert any("schema_version" in str(e) for e in errors)


def test_invalid_json_line_counted_as_invalid(tmp_path: Path) -> None:
    spool = tmp_path / "bad.jsonl"
    spool.write_text("not-json\n" + json.dumps(VALID_REPORT) + "\n")

    valid, invalid, errors = validate_spool(str(spool), n=200)
    assert invalid == 1
    assert valid == 1
    assert any("invalid JSON" in str(e) for e in errors)


def test_missing_spool_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        validate_spool(str(tmp_path / "nonexistent.jsonl"), n=200)


def test_n_limits_lines_checked(tmp_path: Path) -> None:
    """With n=1 only the last report is validated."""
    bad = _patch(VALID_REPORT, **{"assessment.health": "BAD"})
    spool = tmp_path / "mixed.jsonl"
    spool.write_text(json.dumps(bad) + "\n" + json.dumps(VALID_REPORT) + "\n")

    # n=1 → only the last (valid) line
    valid, invalid, errors = validate_spool(str(spool), n=1)
    assert invalid == 0
    assert valid == 1
