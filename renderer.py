from __future__ import annotations
from typing import Any
from utils import MAX_BODY_CHARS

class StructuredMessageRenderer:
    def render(self, payload: dict[str, Any]) -> dict[str, str]:
        # Deterministic renderer: use payload pieces verbatim and append provided CTA.
        fact = str(payload.get("fact", "")).strip().rstrip(".?!")
        insight = str(payload.get("insight", "")).strip().rstrip(".?!")
        action = str(payload.get("action", "")).strip().rstrip(".?!")

        cta = str(payload.get("cta") or "Reply YES and I'll do this now.").strip()
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
