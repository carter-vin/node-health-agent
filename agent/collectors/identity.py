"""
agent.collectors.identity

AUTHOR: carter-vin

- node_id: stable host identifier (default hostname; override via env var)
- boot_id: changes on reboot (Linux: /proc/.../boot_id), dev fallback cache on disk

Design goals:
- Deterministic behavior
- Graceful degradation on non-Linux dev environments
- No network calls, no heavy dependencies
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LINUX_BOOT_ID_PATH = Path("/proc/sys/kernel/random/boot_id")

# Env var override is important for:
# - multi-node simulation on a single laptop
# - forcing stable IDs in demos
NODE_ID_ENV = "NODE_AGENT_NODE_ID"

# Where we store a dev fallback boot_id when /proc boot_id isn't available.
# This path is repo-local (./state) by contract.
DEFAULT_STATE_DIR = Path("state")
DEV_BOOT_ID_FILE = "boot_id"


@dataclass(frozen=True)
class IdentityResult:
    """
    Identity collector output.

    We keep this separate from the schema's Identity class so that:
    - collectors remain independent of schema specifics
    - we can attach error metadata if needed later

    boot_id is None when acquisition failed (best-effort).
    node_id is always present.
    """

    node_id: str
    boot_id: str | None  # None when boot_id unavailable
    source: str  # e.g., "env+hostname", "linux_proc", "dev_cache", "failed"


def _read_linux_boot_id() -> Optional[str]:
    """
    Attempt to read the Linux boot_id from /proc.

    Returns:
    - boot_id string if available
    - None if not available or unreadable
    """
    try:
        if LINUX_BOOT_ID_PATH.exists():
            return LINUX_BOOT_ID_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        # Swallow errors so collectors do not crash the agent
        return None
    return None


def _read_or_create_dev_boot_id(state_dir: Path) -> str | None:
    """
    Read or create a dev boot_id in repo-local state.

    This simulates "boot scoping" on systems without /proc boot_id (e.g., macOS).
    Returns None on IO failure.
    """
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / DEV_BOOT_ID_FILE

        if path.exists():
            # Keep boot_id stable across runs until state is removed
            return path.read_text(encoding="utf-8").strip() or None

        # Create a new boot_id and persist it
        new_id = str(uuid.uuid4())
        path.write_text(new_id + "\n", encoding="utf-8")
        return new_id
    except Exception:
        return None


def collect_identity(state_dir: Path = DEFAULT_STATE_DIR) -> IdentityResult:
    """
    Collect node identity.

    node_id (always present):
    1) NODE_AGENT_NODE_ID env override
    2) hostname

    boot_id (best-effort, may be None):
    - Linux: /proc boot_id
    - else: repo-local cached UUID in ./state/boot_id
    - None when both sources unavailable; caller adds collector_failed:identity reason
    """

    # node_id always resolves
    node_id = os.getenv(NODE_ID_ENV) or socket.gethostname()

    # Test hook: simulate boot_id unavailability (node_id still resolves)
    if os.getenv("NODE_AGENT_FAIL_IDENTITY") == "1":
        return IdentityResult(node_id=node_id, boot_id=None, source="failed")

    # Boot_id selection: Linux proc, else dev cache, else None
    boot_id = _read_linux_boot_id()
    if boot_id:
        return IdentityResult(node_id=node_id, boot_id=boot_id, source="linux_proc")

    boot_id = _read_or_create_dev_boot_id(state_dir)
    source = "dev_cache" if boot_id else "failed"
    return IdentityResult(node_id=node_id, boot_id=boot_id, source=source)
