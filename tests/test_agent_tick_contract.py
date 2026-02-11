"""
Contract test for agent_tick event payload shape
"""

import json

from agent.logging import emit_event


def test_agent_tick_contract_required_fields(capsys) -> None:
    """
    agent_tick includes stable required fields with expected types
    """
    emit_event(
        "agent_tick",
        agent_version="0.1.0",
        mode="run",
        interval_s=1,
        tick_elapsed_ms=120,
        collect_elapsed_ms=35,
        sleep_ms=965,
        overrun=False,
        reports_emitted=1,
    )

    out = capsys.readouterr().out.strip()
    payload = json.loads(out)

    assert payload["event_type"] == "agent_tick"
    assert "utc_now" in payload
    assert payload["agent_version"] == "0.1.0"
    assert payload["mode"] == "run"
    assert isinstance(payload["interval_s"], int)
    assert isinstance(payload["tick_elapsed_ms"], int)
    assert isinstance(payload["collect_elapsed_ms"], int)
    assert isinstance(payload["sleep_ms"], int)
    assert isinstance(payload["overrun"], bool)
    assert isinstance(payload["reports_emitted"], int)


def test_agent_tick_contract_optional_fields(capsys) -> None:
    """
    agent_tick accepts optional fields with expected types
    """
    emit_event(
        "agent_tick",
        agent_version="0.1.0",
        mode="run",
        interval_s=1,
        tick_elapsed_ms=200,
        collect_elapsed_ms=40,
        build_elapsed_ms=50,
        emit_elapsed_ms=10,
        sleep_ms=800,
        overrun=False,
        reports_emitted=0,
        seq=7,
        node_id="node-a",
        skip_emit=True,
    )

    out = capsys.readouterr().out.strip()
    payload = json.loads(out)

    assert isinstance(payload["build_elapsed_ms"], int)
    assert isinstance(payload["emit_elapsed_ms"], int)
    assert isinstance(payload["seq"], int)
    assert isinstance(payload["node_id"], str)
    assert isinstance(payload["skip_emit"], bool)
