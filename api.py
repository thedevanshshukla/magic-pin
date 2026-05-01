from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from bot import compose
from composer import MessageComposer
from config import BOT_VERSION, CONTACT_EMAIL, GROQ_MODEL, HOST, PORT, TEAM_MEMBERS, TEAM_NAME
from decision_engine import DecisionEngine
# cache layer disabled to use deterministic composer output
from reply_engine import ReplyEngine
from storage import ContextStore, ConversationState
from utils import infer_customer_stub, iso_now, meaningful_conversation_id, parse_iso, truncate_body


START_TIME = time.time()
app = FastAPI(title="magicpin Vera Message Engine", version=BOT_VERSION)
store = ContextStore()
decision_engine = DecisionEngine()
composer = MessageComposer()
reply_engine = ReplyEngine()

def _direct_compose(category, merchant, trigger, intent, customer=None):
    # Bypass cache and return composer output directly.
    return composer.compose(category, merchant, trigger, intent, customer)


class ContextBody(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str


class TickBody(BaseModel):
    now: str
    available_triggers: list[str] = Field(default_factory=list)


class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: str | None = None
    customer_id: str | None = None
    from_role: str
    message: str
    received_at: str
    turn_number: int


@app.get("/v1/healthz")
async def healthz() -> dict[str, Any]:
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": store.counts(),
    }


@app.get("/v1/metadata")
async def metadata() -> dict[str, Any]:
    return {
        "team_name": TEAM_NAME,
        "team_members": TEAM_MEMBERS,
        "model": GROQ_MODEL or "deterministic-rule-engine",
        "approach": "rule-based decision engine + deterministic structured renderer + reply state machine",
        "contact_email": CONTACT_EMAIL,
        "version": BOT_VERSION,
        "submitted_at": "2026-04-29T00:00:00Z",
    }


@app.post("/v1/context")
async def push_context(body: ContextBody) -> dict[str, Any]:
    if body.scope not in {"category", "merchant", "customer", "trigger"}:
        return {"accepted": False, "reason": "invalid_scope", "details": body.scope}
    store.upsert_context(body.scope, body.context_id, body.version, body.payload)
    if body.scope == "category":
        print("CATEGORY STORED:", body.context_id)
    elif body.scope == "merchant":
        print("MERCHANT STORED:", body.context_id)
    elif body.scope == "trigger":
        print("TRIGGER STORED:", body.context_id)
    return {"accepted": True, "ack_id": f"ack_{body.context_id}_v{body.version}", "stored_at": iso_now()}


@app.post("/reset")
@app.post("/v1/reset")
async def reset_contexts() -> dict[str, Any]:
    store.reset()
    return {"status": "reset"}


@app.post("/v1/tick")
async def tick(body: TickBody) -> dict[str, Any]:
    now = parse_iso(body.now) or datetime.now(timezone.utc)
    counts = store.counts()
    print("CATEGORIES:", counts.get("category", 0))
    print("MERCHANTS:", counts.get("merchant", 0))
    candidates: list[tuple[int, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any] | None, Any, dict[str, str]]] = []
    for trigger in store.active_trigger_payloads(body.available_triggers, now):
        suppression_key = trigger.get("suppression_key", "")
        if suppression_key and store.is_suppressed(suppression_key, now):
            continue
        merchant = store.get_context("merchant", trigger.get("merchant_id"))
        if not merchant:
            raise RuntimeError("Context missing — aborting message generation")
        if store.merchant_muted(merchant.get("merchant_id"), now):
            continue
        category = store.get_context("category", merchant.get("category_slug"))
        if not category:
            raise RuntimeError("Context missing — aborting message generation")
        customer = store.get_context("customer", trigger.get("customer_id")) if trigger.get("customer_id") else None
        if not customer and trigger.get("scope") == "customer":
            customer = infer_customer_stub(
                trigger.get("customer_id"),
                merchant.get("merchant_id"),
                merchant.get("category_slug"),
            )
        if customer and not customer.get("preferences", {}).get("reminder_opt_in", False):
            continue

        intent = decision_engine.build_intent(category, merchant, trigger, customer)
        message = _direct_compose(category, merchant, trigger, intent, customer)
        conversation_id = meaningful_conversation_id(trigger, merchant, customer)
        if store.get_conversation(conversation_id):
            continue
        candidates.append((intent.priority_score, trigger, merchant, category, customer, intent, message))

    if not candidates:
        return {"actions": []}

    best_score, trigger, merchant, _category, customer, _intent, message = max(candidates, key=lambda item: item[0])
    conversation_id = meaningful_conversation_id(trigger, merchant, customer)
    template_params = _template_params(trigger, merchant, customer, message["body"])
    action = {
        "conversation_id": conversation_id,
        "merchant_id": merchant.get("merchant_id"),
        "customer_id": customer.get("customer_id") if customer else None,
        "send_as": message["send_as"],
        "trigger_id": trigger.get("id"),
        "template_name": message["template_name"],
        "template_params": template_params,
        "body": message["body"],
        "cta": message["cta"],
        "suppression_key": message["suppression_key"],
        "rationale": message["rationale"],
    }
    store.create_conversation(
        ConversationState(
            conversation_id=conversation_id,
            trigger_id=trigger.get("id"),
            merchant_id=merchant.get("merchant_id"),
            customer_id=customer.get("customer_id") if customer else None,
            send_as=message["send_as"],
            created_at=iso_now(),
        )
    )
    store.note_send(conversation_id, message["body"])
    store.remember_send(trigger.get("suppression_key", ""), trigger.get("expires_at"))
    return {"actions": [action]}


@app.post("/v1/reply")
async def reply(body: ReplyBody) -> dict[str, Any]:
    conversation = store.note_reply(body.conversation_id, body.from_role, body.message, body.received_at)
    if not conversation:
        return {
            "action": "end",
            "rationale": "Conversation not found. Ending safely rather than guessing context.",
        }
    merchant = store.get_context("merchant", conversation.merchant_id) or {}
    trigger = store.get_context("trigger", conversation.trigger_id) or {}
    customer = store.get_context("customer", conversation.customer_id) if conversation.customer_id else None
    response = reply_engine.respond(conversation, merchant, trigger, customer, body.message)
    if response.get("action") == "send" and response.get("body"):
        response["body"] = truncate_body(response["body"])
        if not store.same_body_sent(body.conversation_id, response["body"]):
            store.note_send(body.conversation_id, response["body"])
    if response.get("action") == "end":
        store.close_conversation(body.conversation_id)
        if merchant.get("merchant_id") and "opted out" in response.get("rationale", "").lower():
            store.mute_merchant(merchant["merchant_id"])
    return response


def _template_params(trigger: dict[str, Any], merchant: dict[str, Any], customer: dict[str, Any] | None, body: str) -> list[str]:
    params: list[str] = []
    if customer:
        params.append(customer.get("identity", {}).get("name", "Customer"))
    else:
        params.append(merchant.get("identity", {}).get("owner_first_name", merchant.get("identity", {}).get("name", "Merchant")))
    params.append(trigger.get("kind", "message"))
    params.append(body[:120])
    return params[:5]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
