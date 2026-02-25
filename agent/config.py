"""
agent.config

Config layer for health evaluation thresholds.

Precedence: defaults → JSON file → env vars
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


# Default thresholds (matches historical hardcoded constants in evaluate.py)
_DEFAULTS: dict[str, Any] = {
    "cpu": {
        "degraded_factor": 0.85,
        "unhealthy_factor": 1.25,
    },
    "mem": {
        "degraded_pct": 15.0,
        "unhealthy_pct": 8.0,
    },
    "disk": {
        "degraded_pct": 10.0,
        "unhealthy_pct": 5.0,
    },
    "evaluation": {
        "profile_name": "default",
    },
}

# env var → (section, key, cast)
_ENV_OVERRIDES: dict[str, tuple[str, str, type]] = {
    "NODE_AGENT_CPU_DEGRADED_FACTOR": ("cpu", "degraded_factor", float),
    "NODE_AGENT_CPU_UNHEALTHY_FACTOR": ("cpu", "unhealthy_factor", float),
    "NODE_AGENT_MEM_DEGRADED_PCT": ("mem", "degraded_pct", float),
    "NODE_AGENT_MEM_UNHEALTHY_PCT": ("mem", "unhealthy_pct", float),
    "NODE_AGENT_DISK_DEGRADED_PCT": ("disk", "degraded_pct", float),
    "NODE_AGENT_DISK_UNHEALTHY_PCT": ("disk", "unhealthy_pct", float),
    "NODE_AGENT_EVAL_PROFILE": ("evaluation", "profile_name", str),
}


def normalize_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """
    Return a canonical config dict with all required keys populated.

    Merges cfg over defaults; unknown keys in cfg are ignored.
    """
    result: dict[str, Any] = {
        "cpu": dict(_DEFAULTS["cpu"]),
        "mem": dict(_DEFAULTS["mem"]),
        "disk": dict(_DEFAULTS["disk"]),
        "evaluation": dict(_DEFAULTS["evaluation"]),
    }
    for section in ("cpu", "mem", "disk", "evaluation"):
        if section in cfg and isinstance(cfg[section], dict):
            result[section].update(cfg[section])
    return result


def compute_config_hash(cfg: dict[str, Any]) -> str:
    """
    Compute a stable 16-hex-char SHA-256 prefix of the normalized config.

    Stable across key orderings.
    """
    normalized = normalize_config(cfg)
    serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """
    Load config with precedence: defaults → JSON file → env vars.

    Invalid or missing file → silently falls back to defaults.
    Invalid env var values → silently ignored.
    """
    cfg: dict[str, Any] = {}

    if config_path:
        try:
            payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                cfg = payload
        except Exception:
            pass  # fall back to defaults

    normalized = normalize_config(cfg)

    for env_var, (section, key, cast) in _ENV_OVERRIDES.items():
        value = os.getenv(env_var)
        if value is not None:
            try:
                normalized[section][key] = cast(value)
            except (ValueError, TypeError):
                pass

    return normalized
