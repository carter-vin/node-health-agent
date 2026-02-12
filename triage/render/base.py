"""
triage.render.base
AUTHOR: carter-vin

Renderer interface
"""

from __future__ import annotations

from typing import Iterable

from triage.summarize import NodeSummary


class Renderer:
    name: str = "base"

    def render(self, summaries: Iterable[NodeSummary], *, meta: dict) -> str:
        raise NotImplementedError
