from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Intent:
    strategy: str
    goal: str
    levers: list[str]
    fact: str
    insight: str
    action: str
    cta: str
    cta_type: str
    tone: str
    audience: str
    send_as: str
    rationale: str
    signals: list[str]
    extras: dict[str, Any]
    priority_score: int


class DecisionEngine:
    TONE_MAP = {
        "dentists": "clinical",
        "salons": "aspirational",
        "restaurants": "practical",
        "gyms": "motivational",
        "pharmacies": "trust",
    }

    def build_intent(
        self,
        category: dict[str, Any],
        merchant: dict[str, Any],
        trigger: dict[str, Any],
        customer: dict[str, Any] | None = None,
    ) -> Intent:
        """Build intent from trigger with simplified, stable logic."""
        if not merchant or not category:
            raise RuntimeError("Context missing — aborting message generation")
        kind = trigger.get("kind", "")
        payload = trigger.get("payload", {})

        customer_scoped = bool(customer or trigger.get("scope") == "customer")
        send_as = "merchant_on_behalf" if customer_scoped else "vera"
        audience = "customer" if customer_scoped else "merchant"
        tone = self.TONE_MAP.get(merchant.get("category_slug", category.get("slug", "")), "practical")

        fact = ""
        insight = ""
        action = ""
        cta = "Want me to do this for you?"
        cta_type = "open_ended"
        strategy = "inform + action"
        
        if kind == "perf_dip":
            metric = payload.get("metric", "performance")
            delta_pct = payload.get("delta_pct", 0)
            window = payload.get("window", "7d")
            fact = f"{metric} down {int(abs(delta_pct * 100))}% in {window}"
            insight = "This is affecting your visibility."
            action = "I can help fix this quickly."
            strategy = "recover + urgency"
        
        elif kind == "supply_alert":
            batches = payload.get("affected_batches", [])
            molecule = payload.get("molecule", "item")
            manufacturer = payload.get("manufacturer", "manufacturer")
            alert_id = payload.get("alert_id", "")
            if batches:
                batch_str = ", ".join(batches[:2]) if len(batches) <= 2 else f"{batches[0]}, {batches[1]}"
                fact = f"{molecule.title()} recall from {manufacturer}; {len(batches)} batches affected: {batch_str}"
            else:
                fact = f"{molecule.title()} recall from {manufacturer}"
            if alert_id:
                fact = f"{fact} ({alert_id})"
            insight = "This needs prompt action to protect patients."
            action = "I can draft a patient-safe notification."
            strategy = "inform + urgency"
        
        elif kind == "gbp_unverified":
            merchant_name = merchant.get("identity", {}).get("name", "Your profile")
            verification_path = payload.get("verification_path", "postcard or phone call")
            uplift_pct = payload.get("estimated_uplift_pct", 0)
            uplift_text = f"{int(uplift_pct * 100)}%" if uplift_pct else "more"
            fact = f"{merchant_name}: Google profile is still unverified"
            insight = f"Verification via {verification_path} can lift visibility by {uplift_text}."
            action = "I can guide you through verification."
            strategy = "recover + loss_aversion"
        
        elif kind == "recall_due":
            last_visit = payload.get("last_service_date", "")
            due_date = payload.get("due_date", "")
            fact = f"Last visit {last_visit}; recall due {due_date}"
            insight = "This is a live booking window."
            action = "I can hold a slot for you."
            cta = "Reply 1 for slot or 2 for another time."
            cta_type = "multi_choice_slot"
            strategy = "convert + booking"
        
        elif kind == "customer_lapsed_hard":
            if customer:
                customer_name = customer.get("identity", {}).get("name", "there")
                days_since = payload.get("days_since_last_visit", 0)
                focus = payload.get("previous_focus", "")
                months = payload.get("previous_membership_months", 0)
                merchant_name = merchant.get("identity", {}).get("name", "This gym")
                fact = f"{merchant_name}: {customer_name}, it's been {days_since} days since your {focus} session"
                if months > 0:
                    insight = f"You were with us for {months} months — you can return."
                else:
                    insight = "Re-engagement is still possible."
            else:
                fact = "Your customers are lapsing."
                insight = "A personal message can bring them back."
            action = "I can draft a personalized comeback offer."
            strategy = "re-engage + convert"
        
        elif kind == "winback_eligible":
            days_since = payload.get("days_since_expiry", 0)
            lapsed_count = payload.get("lapsed_count", 0)
            fact = f"{days_since} days since expiry; {lapsed_count} lapsed customers"
            insight = "There's still a window to win them back."
            action = "I can draft a restart offer."
            strategy = "recover + curiosity"
        
        elif kind == "research_digest":
            fact = "New research is relevant to your practice."
            insight = "Your patients might benefit from this."
            action = "I can draft a patient education message."
            strategy = "educate + curiosity"
        
        elif kind == "festival_upcoming":
            festival = payload.get("festival", "upcoming event")
            days = payload.get("days_until", 0)
            fact = f"{festival} in {days} days"
            insight = "Promotions typically convert better here."
            action = "I can create a ready post."
            strategy = "promote + urgency"
        
        elif kind == "dormant_with_vera":
            days = payload.get("days_since_last_merchant_message", 0)
            fact = f"Last merchant reply {days} days ago"
            insight = "A light operator question is stronger than a reminder."
            action = "I can draft a re-engagement message."
            strategy = "re-engage"
        
        elif kind == "ipl_match_today":
            match_time = payload.get("match_time", "6pm")
            fact = f"IPL match at {match_time} today"
            insight = "Local customers will be watching and hungry."
            action = "I can create a match-day offer post."
            strategy = "capitalize + nuance"
        
        elif kind == "curious_ask_due":
            question = payload.get("question", "customer feedback")
            fact = f"You have a pending {question} question"
            insight = "A quick answer keeps customers engaged."
            action = "I can draft your response."
            strategy = "engage + curiosity"
        
        elif kind == "review_theme_emerged":
            theme = payload.get("theme", "service issue")
            mention_count = payload.get("mention_count", 1)
            fact = f"{theme} mentioned {mention_count} times in reviews"
            insight = "Addressing this pattern shows you listen."
            action = "I can draft a public response."
            strategy = "recover + fix"
        
        elif kind == "competitor_opened":
            competitor = payload.get("competitor_name", "competitor")
            distance = payload.get("distance_km", "nearby")
            fact = f"{competitor} opened {distance} km away"
            insight = "Competing on price is tough; compete on quality instead."
            action = "I can highlight your unique value."
            strategy = "loss_aversion"
        
        elif kind == "regulation_change":
            regulation = payload.get("top_item_id", payload.get("regulation", "compliance requirement"))
            regulation = str(regulation).replace("d_", "").replace("_", " ")
            if regulation.lower().startswith("dci "):
                regulation = "DCI " + regulation[4:]
            deadline = payload.get("deadline_iso", "soon")
            merchant_name = merchant.get("identity", {}).get("name", "Your clinic")
            fact = f"{merchant_name}: {regulation} due by {deadline[:10]}"
            insight = "Acting early avoids penalties and avoids last-minute work."
            action = "I can create a compliance checklist."
            strategy = "inform + action"
        
        elif kind == "seasonal_perf_dip":
            season = payload.get("season", "season")
            delta = payload.get("delta_pct", 0)
            fact = f"Views down {int(abs(delta * 100))}% during {season}"
            insight = "This is normal, not a crisis."
            action = "I can draft a seasonal retention offer."
            strategy = "recover + reframe"
        
        elif kind == "perf_spike":
            metric = payload.get("metric", "performance")
            delta = payload.get("delta_pct", 0)
            fact = f"{metric} up {int(delta * 100)}%"
            insight = "Momentum is gold—capitalize now."
            action = "I can amplify this trend."
            strategy = "capitalize + amplify"
        
        elif kind == "milestone_reached":
            milestone = payload.get("milestone", "milestone")
            value = payload.get("value", "")
            fact = f"You've reached {milestone}: {value}"
            insight = "This is worth celebrating with your customers."
            action = "I can draft a milestone announcement."
            strategy = "capitalize + amplify"
        
        elif kind == "chronic_refill_due":
            med = payload.get("medicine", "your refill")
            fact = f"{med} refill is due"
            insight = "A timely reminder prevents gaps."
            action = "I can send a patient-friendly reminder."
            strategy = "convert + refill"
        
        elif kind == "renewal_due":
            plan = payload.get("plan", "plan")
            days = payload.get("days_remaining", 0)
            fact = f"{plan} plan renews in {days} days"
            insight = "Don't let your benefits lapse."
            action = "I can process the renewal quickly."
            strategy = "retain + action"
        
        elif kind == "wedding_package_followup":
            wedding_date = payload.get("wedding_date", "soon")
            days_to_wedding = payload.get("days_to_wedding", 0)
            merchant_name = merchant.get("identity", {}).get("name", "Your salon")
            fact = f"{merchant_name}: wedding on {wedding_date} — {days_to_wedding} days away"
            insight = "Now is the time to start your skin prep."
            action = "I can schedule your first session."
            cta = "Reply 1 to book or 2 if not ready yet."
            cta_type = "multi_choice_slot"
            strategy = "convert + booking"
        
        elif kind == "trial_followup":
            trial_date = payload.get("trial_date", "recently")
            fact = f"You tried us on {trial_date}"
            insight = "One trial is a great start; consistency wins."
            action = "I can help you book your next session."
            strategy = "convert + book"
        
        elif kind == "active_planning_intent":
            topic = payload.get("intent_topic", "a new idea")
            fact = f"You want to add {topic.replace('_', ' ')}"
            insight = "Let's turn this into reality."
            action = "I can help you plan and execute."
            strategy = "grow + execute"
        
        elif kind == "category_seasonal":
            season = payload.get("season", "season")
            fact = f"Seasonal demand shift detected for {season}"
            insight = "Smart merchants adjust their shelves."
            action = "I can suggest what to stock more of."
            strategy = "inform + action"
        
        elif kind == "cde_opportunity":
            credits = payload.get("credits", 1)
            fact = f"Free webinar available ({credits} credits)"
            insight = "Continuing education keeps you sharp."
            action = "I can send you the link."
            strategy = "educate + curiosity"
        else:
            raise RuntimeError(f"Unsupported trigger kind: {kind}")

        if not fact or not insight or not action:
            raise RuntimeError("Context missing — aborting message generation")
        
        # Priority score is simple: based on urgency and kind
        urgency = trigger.get("urgency", 1)
        priority_score = urgency * 10
        
        extras = {
            "merchant_name": merchant.get("identity", {}).get("name", "Merchant"),
            "customer_name": customer.get("identity", {}).get("name") if customer else None,
        }
        
        return Intent(
            strategy=strategy,
            goal="convert" if customer_scoped else "inform",
            levers=["numbers"],
            fact=fact,
            insight=insight,
            action=action,
            cta=cta,
            cta_type=cta_type,
            tone=tone,
            audience=audience,
            send_as=send_as,
            rationale=f"{kind} trigger",
            signals=[],
            extras=extras,
            priority_score=priority_score,
        )
