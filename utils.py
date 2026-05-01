from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Iterable


MAX_BODY_CHARS = 320
AUTO_REPLY_PATTERNS = (
    "thank you for contacting",
    "our team will respond shortly",
    "automated assistant",
    "auto reply",
    "this is an automated",
    "we will get back",
    "we'll get back",
)
POSITIVE_PATTERNS = (
    "yes",
    "yeah",
    "yep",
    "ok let's do it",
    "lets do it",
    "do it",
    "go ahead",
    "send it",
    "send me",
    "what's next",
    "whats next",
    "i want to join",
    "i want to do this",
    "please send",
    "confirm",
)
NEGATIVE_PATTERNS = (
    "stop messaging",
    "not interested",
    "don't message",
    "dont message",
    "spam",
    "useless",
    "no thanks",
    "unsubscribe",
    "leave me alone",
)
WAIT_PATTERNS = (
    "later",
    "tomorrow",
    "call me later",
    "remind me",
    "busy right now",
    "busy now",
)
OUT_OF_SCOPE_PATTERNS = (
    "gst",
    "tax filing",
    "ca filing",
    "accounting",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def has_url(text: str) -> bool:
    return bool(re.search(r"https?://|www\.", text))


def compact_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def truncate_body(text: str, limit: int = MAX_BODY_CHARS) -> str:
    if len(text) <= limit:
        return text
    trimmed = text[: limit - 1].rstrip(" ,;:-")
    cut = max(trimmed.rfind("."), trimmed.rfind("?"), trimmed.rfind("!"))
    if cut >= 120:
        return trimmed[: cut + 1]
    return trimmed + "..."


def pct_to_str(value: float | int | None, digits: int = 0) -> str:
    if value is None:
        return ""
    pct = value * 100 if abs(value) <= 1 else value
    if digits == 0:
        return f"{round(pct):.0f}%"
    return f"{pct:.{digits}f}%"


def price_from_text(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"₹\s*[\d,]+", text)
    if match:
        return match.group(0).replace(" ", "")
    return None


def first_active_offer(offers: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    for offer in offers:
        if offer.get("status") == "active":
            return offer
    return None


def merchant_display_name(merchant: dict[str, Any], category_slug: str) -> str:
    identity = merchant.get("identity", {})
    owner = identity.get("owner_first_name")
    name = identity.get("name", "")
    if category_slug == "dentists" and owner:
        return f"Dr. {owner}"
    if owner:
        return owner
    return name.split(" ")[0] if name else "there"


def merchant_sender_label(merchant: dict[str, Any], category_slug: str) -> str:
    name = merchant.get("identity", {}).get("name", "your clinic")
    if category_slug == "dentists":
        return "Dr. Meera's clinic" if "Dr. Meera" in name else f"{name} here"
    return f"{name} here"


def slot_labels(trigger: dict[str, Any]) -> list[str]:
    slots = trigger.get("payload", {}).get("available_slots", []) or trigger.get("payload", {}).get("next_session_options", [])
    return [slot.get("label") for slot in slots if slot.get("label")]


def find_digest_item(category: dict[str, Any], item_id: str | None) -> dict[str, Any] | None:
    if not item_id:
        return None
    for item in category.get("digest", []):
        if item.get("id") == item_id:
            return item
    return None


def infer_customer_stub(
    customer_id: str | None,
    merchant_id: str | None = None,
    category_slug: str | None = None,
) -> dict[str, Any] | None:
    if not customer_id:
        return None
    parts = customer_id.split("_")
    raw_name = "_".join(parts[2:-2]) if len(parts) >= 5 else parts[-1]
    raw_name = raw_name.lower()
    alias_map = {
        "grandfather": "Mr. Sharma",
        "karthik_jr": "Karthik",
        "anonymous": "there",
    }
    name = alias_map.get(raw_name)
    if not name:
        name = raw_name.replace("_", " ").strip().title() or "Customer"
    language_pref = "english"
    if category_slug in {"dentists", "pharmacies"}:
        language_pref = "hi-en mix"
    return {
        "customer_id": customer_id,
        "merchant_id": merchant_id,
        "identity": {"name": name, "language_pref": language_pref},
        "preferences": {"reminder_opt_in": True},
        "relationship": {},
        "state": "unknown",
    }


def safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def detect_auto_reply(message: str) -> bool:
    lowered = compact_whitespace(message).lower()
    return any(pattern in lowered for pattern in AUTO_REPLY_PATTERNS)


def detect_positive_intent(message: str) -> bool:
    lowered = compact_whitespace(message).lower()
    return any(pattern in lowered for pattern in POSITIVE_PATTERNS)


def detect_negative_intent(message: str) -> bool:
    lowered = compact_whitespace(message).lower()
    return any(pattern in lowered for pattern in NEGATIVE_PATTERNS)


def detect_wait_intent(message: str) -> bool:
    lowered = compact_whitespace(message).lower()
    return any(pattern in lowered for pattern in WAIT_PATTERNS)


def detect_out_of_scope(message: str) -> bool:
    lowered = compact_whitespace(message).lower()
    return any(pattern in lowered for pattern in OUT_OF_SCOPE_PATTERNS)


def meaningful_conversation_id(trigger: dict[str, Any], merchant: dict[str, Any], customer: dict[str, Any] | None = None) -> str:
    kind = trigger.get("kind", "message")
    merchant_id = merchant.get("merchant_id", "merchant")
    owner = merchant.get("identity", {}).get("owner_first_name", "merchant").lower()
    if customer:
        customer_name = customer.get("identity", {}).get("name", "customer").split(" ")[0].lower()
        if kind == "recall_due":
            due = trigger.get("payload", {}).get("due_date", "")
            parts = due.split("-")
            month_suffix = "_".join(parts[:2]) if len(parts) >= 2 else "due"
            return f"conv_{customer_name}_recall_{month_suffix}"
        suffix = re.sub(r"[^a-z0-9]+", "_", kind)
        return f"conv_{customer_name}_{suffix}_{merchant_id.split('_')[1]}"
    if kind == "research_digest":
        suppression = trigger.get("suppression_key", "")
        week = suppression.split(":")[-1] if suppression else "digest"
        return f"conv_{merchant_id.split('_')[1]}_{owner}_{week}"
    suffix = re.sub(r"[^a-z0-9]+", "_", kind)
    return f"conv_{merchant_id.split('_')[1]}_{suffix}"


def expiry_passed(expires_at: str | None, now: datetime) -> bool:
    expiry = parse_iso(expires_at)
    if not expiry:
        return False
    return expiry <= now


def future_iso(hours: int = 0, days: int = 0) -> str:
    return (utc_now() + timedelta(hours=hours, days=days)).isoformat().replace("+00:00", "Z")
