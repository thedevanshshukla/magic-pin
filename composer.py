from __future__ import annotations

import re
from typing import Any

from decision_engine import Intent
from renderer import StructuredMessageRenderer


class MessageComposer:
    def __init__(self) -> None:
        self.renderer = StructuredMessageRenderer()

    def compose(
        self,
        category: dict[str, Any],
        merchant: dict[str, Any],
        trigger: dict[str, Any],
        intent: Intent,
        customer: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        # Compose a simple, direct message from the intent pieces.
        fact = intent.fact or ""
        insight = intent.insight or ""
        action = intent.action or ""
        # Strict composition: no validation, no fallbacks, no humanizer.
        body_struct = {"fact": fact, "insight": insight, "action": action}
        rendered = self.renderer.render(body_struct)
        body = rendered.get("body", "")

        return {
            "body": body,
            "cta": rendered.get("cta", ""),
            "send_as": intent.send_as,
            "suppression_key": trigger.get("suppression_key", ""),
            "rationale": intent.rationale,
            "template_name": self._template_name(trigger.get("kind", ""), customer is not None),
        }

    def _template_name(self, kind: str, is_customer: bool) -> str:
        prefix = "merchant" if is_customer else "vera"
        return f"{prefix}_{kind}_v1"
