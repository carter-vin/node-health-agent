#!/usr/bin/env python3
"""
scripts/validate_spool.py

Minimal spool validator — stdlib only, no external dependencies.

Validates each report in the tail window against the v1 report contract:
- Required top-level keys present: assessment, identity, meta, signals, timing
- assessment.health in {OK, DEGRADED, UNHEALTHY}
- meta.schema_version == "1"
- timing.emitted_at is RFC3339-parseable (best-effort)
- identity.node_id is non-empty

Usage:
    python scripts/validate_spool.py --spool spool/node_reports.jsonl --n 200
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

VALID_HEALTH = frozenset({"OK", "DEGRADED", "UNHEALTHY"})
REQUIRED_KEYS = frozenset({"assessment", "identity", "meta", "signals", "timing"})
REQUIRED_SCHEMA_VERSION = "1"


class ValidationError(NamedTuple):
    line: int
    message: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.message}"


def _is_rfc3339(value: object) -> bool:
    """
    Best-effort RFC3339 timestamp check using datetime.fromisoformat (Python 3.11+
    handles timezone offsets; earlier versions require manual stripping).
    """
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        pass
    # Fallback: try replacing trailing Z with +00:00 for Python < 3.11
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_report(report: dict, line: int) -> list[ValidationError]:
    """
    Validate a single parsed report dict against the v1 contract.

    Returns a list of ValidationError (empty means valid).
    """
    errors: list[ValidationError] = []

    # Required top-level keys
    missing = REQUIRED_KEYS - set(report.keys())
    if missing:
        errors.append(ValidationError(line, f"missing required keys: {sorted(missing)}"))
        return errors  # nested checks unsafe without the keys

    # assessment.health
    health = report.get("assessment", {}).get("health")
    if health not in VALID_HEALTH:
        errors.append(ValidationError(
            line,
            f"assessment.health must be one of {sorted(VALID_HEALTH)}, got {health!r}",
        ))

    # assessment.reasons must be a list
    reasons = report.get("assessment", {}).get("reasons")
    if not isinstance(reasons, list):
        errors.append(ValidationError(line, "assessment.reasons must be an array"))

    # meta.schema_version
    schema_version = report.get("meta", {}).get("schema_version")
    if schema_version != REQUIRED_SCHEMA_VERSION:
        errors.append(ValidationError(
            line,
            f"meta.schema_version must be {REQUIRED_SCHEMA_VERSION!r}, got {schema_version!r}",
        ))

    # timing.emitted_at RFC3339
    emitted_at = report.get("timing", {}).get("emitted_at")
    if not _is_rfc3339(emitted_at):
        errors.append(ValidationError(
            line,
            f"timing.emitted_at is not a valid RFC3339 timestamp: {emitted_at!r}",
        ))

    # timing.seq >= 1
    seq = report.get("timing", {}).get("seq")
    if not isinstance(seq, int) or seq < 1:
        errors.append(ValidationError(line, f"timing.seq must be an integer >= 1, got {seq!r}"))

    # identity.node_id non-empty
    node_id = report.get("identity", {}).get("node_id")
    if not isinstance(node_id, str) or not node_id.strip():
        errors.append(ValidationError(line, "identity.node_id must be a non-empty string"))

    # signals must be a dict
    signals = report.get("signals")
    if not isinstance(signals, dict):
        errors.append(ValidationError(line, "signals must be an object"))

    return errors


def validate_spool(spool_path: str, n: int) -> tuple[int, int, list[ValidationError]]:
    """
    Validate the last n reports from a spool file.

    Returns (valid_count, invalid_count, all_errors).
    Raises FileNotFoundError when spool is missing.
    """
    path = Path(spool_path)
    if not path.exists():
        raise FileNotFoundError(f"spool not found: {spool_path}")

    raw_lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    tail = raw_lines[-n:] if n > 0 else raw_lines

    all_errors: list[ValidationError] = []
    valid_count = 0
    invalid_count = 0

    for i, line in enumerate(tail, 1):
        try:
            report = json.loads(line)
        except json.JSONDecodeError:
            all_errors.append(ValidationError(i, "invalid JSON"))
            invalid_count += 1
            continue

        if not isinstance(report, dict):
            all_errors.append(ValidationError(i, f"expected JSON object, got {type(report).__name__}"))
            invalid_count += 1
            continue

        errors = validate_report(report, i)
        if errors:
            all_errors.extend(errors)
            invalid_count += 1
        else:
            valid_count += 1

    return valid_count, invalid_count, all_errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate reports in a node-health-agent spool JSONL file.",
    )
    parser.add_argument("--spool", required=True, help="Path to spool JSONL file")
    parser.add_argument(
        "--n", type=int, default=200,
        help="Number of reports to validate from the end (default: 200, 0 = all)",
    )
    args = parser.parse_args()

    try:
        valid_count, invalid_count, errors = validate_spool(args.spool, args.n)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if errors:
        for err in errors:
            print(str(err), file=sys.stderr)
        print(
            f"\nvalidation failed: {invalid_count} invalid, {valid_count} valid",
            file=sys.stderr,
        )
        return 1

    print(f"ok: {valid_count} reports valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
