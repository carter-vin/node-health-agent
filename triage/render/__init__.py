"""triage.render registry."""

from __future__ import annotations

from triage.render.explain import ExplainRenderer
from triage.render.json import JsonRenderer
from triage.render.pretty import PrettyRenderer
from triage.render.table import TableRenderer
from triage.render.text import TextRenderer

_RENDERERS = {
    "json": JsonRenderer(),
    "text": TextRenderer(),
    "pretty": PrettyRenderer(),
    "table": TableRenderer(),
    "explain": ExplainRenderer(),
}


def get_renderer(name: str):
    if name not in _RENDERERS:
        raise ValueError(f"unknown renderer: {name}")
    return _RENDERERS[name]
