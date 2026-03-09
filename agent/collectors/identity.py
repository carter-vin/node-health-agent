"""
agent.collectors.identity

node_id: stable host identifier (hostname or NODE_AGENT_NODE_ID env override).
boot_id: changes on reboot. Source priority: Linux /proc, dev cache in ./state,
         None when both unavailable (best-effort).
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass
from pathlib import Path

LINUX_BOOT_ID_PATH = Path("/proc/sys/kernel/random/boot_id")

# Allows multi-node simulation on a single host or forced stable IDs in demos.
NODE_ID_ENV = "NODE_AGENT_NODE_ID"

DEFAULT_STATE_DIR = Path("state")
DEV_BOOT_ID_FILE = "boot_id"


@dataclass(frozen=True)
class IdentityResult:
    node_id: str
    boot_id: str | None  # None when boot_id unavailable
    source: str  # "linux_proc" | "dev_cache" | "failed"


def _read_linux_boot_id() -> str | None:
    """Read /proc boot_id on Linux; return None when unavailable or unreadable."""
    if not LINUX_BOOT_ID_PATH.exists():
        return None
    try:
        return LINUX_BOOT_ID_PATH.read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


def _read_or_create_dev_boot_id(state_dir: Path) -> str | None:
    """Read or create a stable dev boot_id in ./state (for non-Linux). Returns None on IO failure."""
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / DEV_BOOT_ID_FILE

        if path.exists():
            return path.read_text(encoding="utf-8").strip() or None

        new_id = str(uuid.uuid4())
        path.write_text(new_id + "\n", encoding="utf-8")
        return new_id
    except Exception:
        return None


def collect_identity(state_dir: Path = DEFAULT_STATE_DIR) -> IdentityResult:
    """
    Collect node identity.

    node_id: NODE_AGENT_NODE_ID env override, else hostname (always present).
    boot_id: Linux /proc, else dev cache in ./state, else None (best-effort).
    """
    node_id = os.getenv(NODE_ID_ENV) or socket.gethostname()

    if os.getenv("NODE_AGENT_FAIL_IDENTITY") == "1":
        return IdentityResult(node_id=node_id, boot_id=None, source="failed")

    boot_id = _read_linux_boot_id()
    if boot_id:
        return IdentityResult(node_id=node_id, boot_id=boot_id, source="linux_proc")


    boot_id = _read_or_create_dev_boot_id(state_dir)
    source = "dev_cache" if boot_id else "failed"
    return IdentityResult(node_id=node_id, boot_id=boot_id, source=source)
