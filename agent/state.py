"""
agent.state
AUTHOR: carter-vin

Persistent agent state (repo-local ./state)

Current responsibilities:
- Deterministic per-boot sequence counter (seq) scoped to identity.boot_id
- Commit semantics: seq increments ONLY after a successful emit

State file:
- ./state/seq.json
  {
    "boot_id": "<boot scope>",
    "next_seq": 1
  }

Design goals:
- Small surface area
- Explicit failure modes
- Safe defaults (reset on boot_id change)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_STATE_DIR = Path("state")
SEQ_STATE_FILE = "seq.json"


@dataclass(frozen=True)
class SeqState:
    """
    Stored seq state.

    boot_id:
    - boot scope key
    next_seq:
    - next sequence number to emit (must be >= 1)
    """
    boot_id: str
    next_seq: int

    def to_dict(self) -> dict[str, Any]:
        return {"boot_id": self.boot_id, "next_seq": self.next_seq}

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "SeqState":
        boot_id = str(payload.get("boot_id", "")).strip()
        next_seq = payload.get("next_seq", 1)

        # Defensive parsing; keep it strict but survivable
        try:
            next_seq_int = int(next_seq)
        except Exception:
            next_seq_int = 1

        if not boot_id:
            # Caller should treat this as invalid and reset
            boot_id = ""

        if next_seq_int < 1:
            next_seq_int = 1

        return SeqState(boot_id=boot_id, next_seq=next_seq_int)


def _state_path(state_dir: Path) -> Path:
    return state_dir / SEQ_STATE_FILE


def load_seq_state(*, state_dir: Path = DEFAULT_STATE_DIR) -> SeqState | None:
    """
    Load seq state from disk

    Returns:
    - SeqState if file exists and parses
    - None if missing or unreadable
    """
    path = _state_path(state_dir)

    try:
        if not path.exists():
            return None

        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None

        state = SeqState.from_dict(payload)

        # If boot_id is empty after parsing, treat as invalid
        if not state.boot_id:
            return None

        return state

    except Exception:
        # State should never crash the agent
        return None


def save_seq_state(state: SeqState, *, state_dir: Path = DEFAULT_STATE_DIR) -> None:
    """
    Persist seq state to disk

    Failure semantics:
    - Raises on IO errors (caller decides whether to downgrade)
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    path = _state_path(state_dir)

    # Deterministic JSON: stable ordering and compact formatting
    path.write_text(
        json.dumps(state.to_dict(), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def get_seq_for_boot(boot_id: str, *, state_dir: Path = DEFAULT_STATE_DIR) -> int:
    """
    Get the next seq for this boot_id WITHOUT mutating state

    Rules:
    - If no state exists -> return 1
    - If stored boot_id differs -> return 1 (reset)
    - Else -> return stored next_seq
    """
    boot_id = boot_id.strip()
    if not boot_id:
        return 1

    current = load_seq_state(state_dir=state_dir)
    if current is None:
        return 1

    if current.boot_id != boot_id:
        return 1

    return current.next_seq


def commit_seq_after_emit(boot_id: str, emitted_seq: int, *, state_dir: Path = DEFAULT_STATE_DIR) -> None:
    """
    Commit seq state after a successful emission

    This enforces the gate semantics:
    - seq only advances when emit succeeded
    - boot_id change resets seq

    Behavior:
    - If boot_id differs from stored -> set next_seq = emitted_seq + 1 and store boot_id
    - Else -> set next_seq = max(stored.next_seq, emitted_seq + 1)
    """
    boot_id = boot_id.strip()
    if not boot_id:
        return

    next_seq = max(1, int(emitted_seq) + 1)

    current = load_seq_state(state_dir=state_dir)

    # No existing state or boot_id change -> reset baseline
    if current is None or current.boot_id != boot_id:
        save_seq_state(SeqState(boot_id=boot_id, next_seq=next_seq), state_dir=state_dir)
        return

    # Same boot_id: monotonic advance (guard against weird calls)
    committed = max(current.next_seq, next_seq)
    save_seq_state(SeqState(boot_id=boot_id, next_seq=committed), state_dir=state_dir)
