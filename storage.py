from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from utils import detect_auto_reply, expiry_passed, parse_iso, utc_now


@dataclass
class ConversationState:
    conversation_id: str
    trigger_id: str
    merchant_id: str
    customer_id: str | None
    send_as: str
    created_at: str
    status: str = "open"
    turns: list[dict[str, Any]] = field(default_factory=list)
    sent_bodies: list[str] = field(default_factory=list)
    auto_reply_count: int = 0


class ContextStore:
    def __init__(self) -> None:
        self.categories: dict[str, dict[str, Any]] = {}
        self.merchants: dict[str, dict[str, Any]] = {}
        self.customers: dict[str, dict[str, Any]] = {}
        self.triggers: dict[str, dict[str, Any]] = {}
        self._conversations: dict[str, ConversationState] = {}
        self._suppression: dict[str, datetime] = {}
        self._merchant_mute_until: dict[str, datetime] = {}

    def counts(self) -> dict[str, int]:
        return {
            "category": len(self.categories),
            "merchant": len(self.merchants),
            "customer": len(self.customers),
            "trigger": len(self.triggers),
        }

    def upsert_context(self, scope: str, context_id: str, version: int, payload: dict[str, Any]) -> tuple[bool, int | None]:
        if scope == "category":
            self.categories[context_id] = payload
        elif scope == "merchant":
            self.merchants[context_id] = payload
        elif scope == "customer":
            self.customers[context_id] = payload
        elif scope == "trigger":
            self.triggers[context_id] = payload
        else:
            return False, None
        return True, None

    def reset(self) -> None:
        self.categories.clear()
        self.merchants.clear()
        self.customers.clear()
        self.triggers.clear()
        self._conversations.clear()
        self._suppression.clear()
        self._merchant_mute_until.clear()

    def get_context(self, scope: str, context_id: str | None) -> dict[str, Any] | None:
        if not context_id:
            return None
        if scope == "category":
            return self.categories.get(context_id)
        if scope == "merchant":
            return self.merchants.get(context_id)
        if scope == "customer":
            return self.customers.get(context_id)
        if scope == "trigger":
            return self.triggers.get(context_id)
        return None

    def remember_send(self, suppression_key: str, expires_at: str | None) -> None:
        expiry = parse_iso(expires_at) or (utc_now() + timedelta(days=7))
        self._suppression[suppression_key] = expiry

    def is_suppressed(self, suppression_key: str, now: datetime) -> bool:
        expiry = self._suppression.get(suppression_key)
        if not expiry:
            return False
        if expiry <= now:
            self._suppression.pop(suppression_key, None)
            return False
        return True

    def merchant_muted(self, merchant_id: str, now: datetime) -> bool:
        muted_until = self._merchant_mute_until.get(merchant_id)
        if not muted_until:
            return False
        if muted_until <= now:
            self._merchant_mute_until.pop(merchant_id, None)
            return False
        return True

    def mute_merchant(self, merchant_id: str, days: int = 30) -> None:
        self._merchant_mute_until[merchant_id] = utc_now() + timedelta(days=days)

    def create_conversation(self, state: ConversationState) -> None:
        self._conversations[state.conversation_id] = state

    def get_conversation(self, conversation_id: str) -> ConversationState | None:
        return self._conversations.get(conversation_id)

    def note_reply(self, conversation_id: str, from_role: str, message: str, received_at: str) -> ConversationState | None:
        state = self._conversations.get(conversation_id)
        if not state:
            return None
        if detect_auto_reply(message):
            state.auto_reply_count += 1
        else:
            state.auto_reply_count = 0
        state.turns.append({"from": from_role, "body": message, "ts": received_at})
        return state

    def note_send(self, conversation_id: str, body: str) -> None:
        state = self._conversations.get(conversation_id)
        if not state:
            return
        state.turns.append({"from": "bot", "body": body, "ts": utc_now().isoformat()})
        state.sent_bodies.append(body)

    def same_body_sent(self, conversation_id: str, body: str) -> bool:
        state = self._conversations.get(conversation_id)
        if not state:
            return False
        return body in state.sent_bodies

    def close_conversation(self, conversation_id: str) -> None:
        state = self._conversations.get(conversation_id)
        if state:
            state.status = "closed"

    def active_trigger_payloads(self, trigger_ids: list[str], now: datetime) -> list[dict[str, Any]]:
        triggers: list[dict[str, Any]] = []
        for trigger_id in trigger_ids:
            trigger = self.get_context("trigger", trigger_id)
            if not trigger:
                continue
            if expiry_passed(trigger.get("expires_at"), now):
                continue
            triggers.append(trigger)
        triggers.sort(key=lambda item: (item.get("urgency", 0), item.get("scope") == "customer"), reverse=True)
        return triggers[:20]
