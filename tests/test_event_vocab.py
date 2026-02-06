"""
Contract test for event vocabulary enforcement.

The logging surface must reject unknown event types to keep aggregation stable.
"""

import pytest

from agent.logging import emit_event


def test_emit_event_rejects_invalid_event_type() -> None:
    """
    Unknown event types must raise ValueError.
    """
    with pytest.raises(ValueError, match="invalid event_type"):
        emit_event("not_a_real_event", agent_version="0.1.0")
