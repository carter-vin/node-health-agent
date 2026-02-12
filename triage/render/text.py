"""
triage.render.text
AUTHOR: carter-vin

Text renderer wrapper
"""

from __future__ import annotations

from triage.render.base import Renderer
from triage.summarize import render_text


class TextRenderer(Renderer):
    name = "text"

    def render(self, summaries, *, meta: dict) -> str:
        return render_text(summaries, meta=meta)
