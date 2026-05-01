from __future__ import annotations
from typing import Any
from utils import MAX_BODY_CHARS

class StructuredMessageRenderer:
    def render(self, payload: dict[str, Any]) -> dict[str, str]:
        # Minimal deterministic renderer: use payload pieces verbatim and append a fixed CTA.
        fact = str(payload.get("fact", "")).strip().rstrip(".?!")
        insight = str(payload.get("insight", "")).strip().rstrip(".?!")
        action = str(payload.get("action", "")).strip().rstrip(".?!")

        cta = "Want me to do this for you?"
        parts = [p for p in (fact, insight, action) if p]
        body = ". ".join(parts).strip()
        if body:
            body = body + "."
        # Append CTA as a separate sentence
        full = f"{body} {cta}".strip()
        if len(full) > MAX_BODY_CHARS:
            full = full[: MAX_BODY_CHARS].rstrip()  # simple trim
        return {"body": full, "cta": cta}
    # No CTA variation — single stable CTA used above.
