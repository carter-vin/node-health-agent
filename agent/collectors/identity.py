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
    """

    node_id: str
    boot_id: str
    source: str  # e.g., "env+hostname", "linux_proc", "dev_cache"


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


def _read_or_create_dev_boot_id(state_dir: Path) -> str:
    """
    Read or create a dev boot_id in repo-local state.

    This simulates "boot scoping" on systems without /proc boot_id (e.g., macOS).
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / DEV_BOOT_ID_FILE

    if path.exists():
        # Keep boot_id stable across runs until state is removed
        return path.read_text(encoding="utf-8").strip()

    # Create a new boot_id and persist it
    new_id = str(uuid.uuid4())
    path.write_text(new_id + "\n", encoding="utf-8")
    return new_id


def collect_identity(state_dir: Path = DEFAULT_STATE_DIR) -> IdentityResult:
    """
    Collect node identity.

    Precedence:
    1) node_id override from env var (NODE_AGENT_NODE_ID)
    2) hostname

    boot_id:
    - Linux: /proc boot_id
    - else: repo-local cached UUID in ./state/boot_id
    """

    # Test hook for validation
    if os.getenv("NODE_AGENT_FAIL_IDENTITY") == "1":
        raise RuntimeError("Simulated identity collector failure")

    # Node_id selection: override first, then hostname
    node_id = os.getenv(NODE_ID_ENV)
    if not node_id:
        node_id = socket.gethostname()

    # Boot_id selection: Linux proc, else dev cache
    boot_id = _read_linux_boot_id()
    if boot_id:
        return IdentityResult(node_id=node_id, boot_id=boot_id, source="linux_proc")

    boot_id = _read_or_create_dev_boot_id(state_dir)
    return IdentityResult(node_id=node_id, boot_id=boot_id, source="dev_cache")
