"""
triage.render.json
AUTHOR: carter-vin

JSON renderer wrapper
"""

from __future__ import annotations

import json

from triage.render.base import Renderer
from triage.summarize import render_json


class JsonRenderer(Renderer):
    name = "json"

    def render(self, summaries, *, meta: dict) -> str:
        payload = render_json(summaries, meta=meta)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
