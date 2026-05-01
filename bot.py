from __future__ import annotations

from typing import Any

from composer import MessageComposer
from decision_engine import DecisionEngine
from renderer import StructuredMessageRenderer


_decision_engine = DecisionEngine()
_composer = MessageComposer()
_renderer = StructuredMessageRenderer()


def compose(category: dict[str, Any], merchant: dict[str, Any], trigger: dict[str, Any], customer: dict[str, Any] | None = None) -> dict[str, Any]:
    intent = _decision_engine.build_intent(category, merchant, trigger, customer)
    message = _composer.compose(category, merchant, trigger, intent, customer)
    return {
        "body": message["body"],
        "cta": message["cta"],
        "send_as": message["send_as"],
        "suppression_key": message["suppression_key"],
        "rationale": message["rationale"],
    }


def render_message(structured_intent: dict[str, Any]) -> dict[str, str]:
    return _renderer.render(structured_intent)
