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
        self._contexts: dict[tuple[str, str], dict[str, Any]] = {}
        self._conversations: dict[str, ConversationState] = {}
        self._suppression: dict[str, datetime] = {}
        self._merchant_mute_until: dict[str, datetime] = {}

    def counts(self) -> dict[str, int]:
        counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        for (scope, _), _value in self._contexts.items():
            counts[scope] = counts.get(scope, 0) + 1
        return counts

    def upsert_context(self, scope: str, context_id: str, version: int, payload: dict[str, Any]) -> tuple[bool, int | None]:
        key = (scope, context_id)
        current = self._contexts.get(key)
        if current and current["version"] >= version:
            return False, current["version"]
        self._contexts[key] = {"version": version, "payload": payload}
        return True, None

    def get_context(self, scope: str, context_id: str | None) -> dict[str, Any] | None:
        if not context_id:
            return None
        record = self._contexts.get((scope, context_id))
        return record["payload"] if record else None

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
