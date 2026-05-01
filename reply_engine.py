from __future__ import annotations

from typing import Any

from storage import ConversationState
from utils import detect_auto_reply, detect_negative_intent, detect_out_of_scope, detect_positive_intent, detect_wait_intent


class ReplyEngine:
    def respond(
        self,
        conversation: ConversationState,
        merchant: dict[str, Any],
        trigger: dict[str, Any],
        customer: dict[str, Any] | None,
        message: str,
    ) -> dict[str, Any]:
        lowered = message.lower().strip()
        
        # Low-intent / auto-reply check: end conversation immediately
        LOW_INTENT = ["ok", "okay", "k", "kk", "thanks", "thank you", "received", "noted", "cool"]
        if lowered in LOW_INTENT:
            return {"action": "end"}
        
        if any(x in lowered for x in ["ok lets do it", "let's do it", "whats next", "what next", "what's next", "go ahead"]):
            return {
                "action": "send",
                "body": "Got it — I’ll proceed and set this up now. Want me to push it live now?",
                "cta": "open_ended",
                "rationale": "user intent to proceed",
            }
        if detect_negative_intent(lowered):
            return {
                "action": "end",
                "rationale": "Merchant explicitly opted out or showed frustration. Closing the conversation cleanly.",
            }
        if detect_auto_reply(message):
            return {"action": "end"}
        if detect_wait_intent(lowered):
            return {
                "action": "wait",
                "wait_seconds": 14400,
                "rationale": "Merchant asked for time or is busy. Waiting 4 hours before retrying.",
            }
        if detect_out_of_scope(lowered):
            kind = trigger.get("kind", "this")
            return {
                "action": "send",
                "body": f"I'll have to leave that to your CA or ops team. Coming back to {kind.replace('_', ' ')} - want me to handle the next step here first?",
                "cta": "open_ended",
                "rationale": "Out-of-scope request declined politely, then redirected back to the active trigger.",
            }
        if detect_positive_intent(lowered):
            return self._positive_followup(trigger, merchant, customer)
        return {
            "action": "send",
            "body": "Understood. I can keep this simple and handle the next step for you. Reply YES when you want me to proceed.",
            "cta": "binary_yes_no",
            "rationale": "Reply was ambiguous, so reducing the ask to one clear next step.",
        }

    def _positive_followup(self, trigger: dict[str, Any], merchant: dict[str, Any], customer: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "action": "send",
            "body": "Got it — setting this up now. I’ll update you once it’s live.",
            "cta": "open_ended",
            "rationale": "Explicit intent detected, responding with clear execution confirmation.",
        }
