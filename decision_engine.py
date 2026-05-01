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

        identity = merchant.get("identity", {})
        performance = merchant.get("performance", {})
        customer_aggregate = merchant.get("customer_aggregate", {})
        peer_stats = category.get("peer_stats", {})
        merchant_name = identity.get("name", "Your business")

        def _first_active_offer() -> str | None:
            for offer in merchant.get("offers", []):
                if offer.get("status") == "active" and offer.get("title"):
                    return str(offer["title"])
            return None

        def _digest_item(item_id: str | None) -> dict[str, Any] | None:
            if not item_id:
                return None
            for item in category.get("digest", []):
                if item.get("id") == item_id:
                    return item
            return None

        kind = trigger.get("kind", "")
        payload = trigger.get("payload", {})

        customer_scoped = bool(customer or trigger.get("scope") == "customer")
        send_as = "merchant_on_behalf" if customer_scoped else "vera"
        audience = "customer" if customer_scoped else "merchant"
        tone = self.TONE_MAP.get(merchant.get("category_slug", category.get("slug", "")), "practical")

        fact = ""
        insight = ""
        action = ""
        cta = "Reply YES and I'll do this now."
        cta_type = "open_ended"
        strategy = "inform + action"
        
        if kind == "perf_dip":
            metric = payload.get("metric", "performance")
            delta_pct = payload.get("delta_pct", 0)
            window = payload.get("window", "7d")
            baseline = payload.get("vs_baseline")
            calls = performance.get("calls")
            views = performance.get("views")
            baseline_part = f" vs baseline {baseline}" if baseline is not None else ""
            fact = f"{merchant_name}: {metric} down {int(abs(delta_pct * 100))}% in {window}{baseline_part}; current views {views}, calls {calls}"
            insight = "This is a fixable visibility dip if we act this week."
            action = "I can draft a focused recovery post with your best offer."
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
                fact = f"{merchant_name}: {fact} ({alert_id})"
            else:
                fact = f"{merchant_name}: {fact}"
            insight = "Fast outreach can prevent unsafe dispensing and complaints."
            action = "I can draft batch-wise patient and counter-staff notices."
            strategy = "inform + urgency"
        
        elif kind == "gbp_unverified":
            verification_path = payload.get("verification_path", "postcard or phone call")
            uplift_pct = payload.get("estimated_uplift_pct", 0)
            uplift_text = f"{int(uplift_pct * 100)}%" if uplift_pct else "more"
            fact = f"{merchant_name}: Google profile is still unverified"
            insight = f"Verification via {verification_path} can lift visibility by {uplift_text}."
            action = "I can guide verification and draft your first post right after."
            strategy = "recover + loss_aversion"
        
        elif kind == "recall_due":
            last_visit = payload.get("last_service_date", "")
            due_date = payload.get("due_date", "")
            slots = payload.get("available_slots", [])
            slot_labels = [s.get("label") for s in slots if s.get("label")][:2]
            slot_text = f"; slots: {', '.join(slot_labels)}" if slot_labels else ""
            fact = f"{merchant_name}: last visit {last_visit}; recall due {due_date}{slot_text}"
            insight = "This is the highest-conversion window for a rebooking."
            action = "I can send the slot hold message now."
            cta = "Reply 1 to lock slot A, 2 for slot B, or 3 for another time."
            cta_type = "multi_choice_slot"
            strategy = "convert + booking"
        
        elif kind == "customer_lapsed_hard":
            if customer:
                customer_name = customer.get("identity", {}).get("name", "there")
                days_since = payload.get("days_since_last_visit", 0)
                focus = payload.get("previous_focus", "")
                months = payload.get("previous_membership_months", 0)
                fact = f"{merchant_name}: {customer_name}, it's been {days_since} days since your {focus} session"
                if months > 0:
                    insight = f"You were with us for {months} months — you can return."
                else:
                    insight = "Re-engagement is still possible."
            else:
                lapsed = customer_aggregate.get("lapsed_180d_plus") or customer_aggregate.get("lapsed_90d_plus")
                fact = f"{merchant_name}: lapsed customers now {lapsed}"
                insight = "A personalized comeback note usually reactivates intent faster."
            action = "I can draft a comeback offer with a clear next step."
            cta = "Reply YES and I'll prepare the comeback message now."
            strategy = "re-engage + convert"
        
        elif kind == "winback_eligible":
            days_since = payload.get("days_since_expiry", 0)
            lapsed_count = payload.get("lapsed_count", payload.get("lapsed_customers_added_since_expiry", 0))
            perf_dip_pct = payload.get("perf_dip_pct")
            dip_text = f"; performance down {int(abs(perf_dip_pct * 100))}%" if perf_dip_pct is not None else ""
            fact = f"{merchant_name}: {days_since} days since expiry; {lapsed_count} customers lapsed{dip_text}"
            insight = "This is still salvageable with one precise restart campaign."
            action = "I can draft a winback offer using your strongest past service."
            strategy = "recover + curiosity"
        
        elif kind == "research_digest":
            digest_item = _digest_item(payload.get("top_item_id"))
            if digest_item:
                title = digest_item.get("title", "New research is relevant")
                source = digest_item.get("source", "trusted source")
                trial_n = digest_item.get("trial_n")
                n_part = f" (n={trial_n})" if trial_n else ""
                fact = f"{merchant_name}: {title}{n_part} — {source}"
                insight = str(digest_item.get("actionable") or "This can directly improve patient communication.")
            else:
                fact = f"{merchant_name}: new research update is relevant to your category"
                insight = "This can improve how you explain treatment value."
            action = "I can draft a 90-second patient education WhatsApp from this item."
            strategy = "educate + curiosity"
        
        elif kind == "festival_upcoming":
            festival = payload.get("festival", "upcoming event")
            days = payload.get("days_until", 0)
            offer = _first_active_offer()
            offer_text = f"; best active offer: {offer}" if offer else ""
            fact = f"{merchant_name}: {festival} in {days} days{offer_text}"
            insight = "Festival demand windows convert better with one clear offer."
            action = "I can draft a ready festival post and CTA for this week."
            strategy = "promote + urgency"
        
        elif kind == "dormant_with_vera":
            days = payload.get("days_since_last_merchant_message", 0)
            last_topic = payload.get("last_topic", "operations")
            fact = f"{merchant_name}: last merchant reply {days} days ago (topic: {last_topic})"
            insight = "A practical, low-friction restart ask works better than reminders."
            action = "I can draft a one-line re-engagement question now."
            strategy = "re-engage"
        
        elif kind == "ipl_match_today":
            match = payload.get("match", "IPL match")
            city = payload.get("city", identity.get("city", "your city"))
            match_time = payload.get("match_time_iso", "today")
            fact = f"{merchant_name}: {match} in {city} at {str(match_time)[11:16]}"
            insight = "Match-time demand spikes when the offer is explicit and immediate."
            action = "I can create a match-day combo post from your current menu offer."
            strategy = "capitalize + nuance"
        
        elif kind == "curious_ask_due":
            template = payload.get("ask_template", "weekly performance focus")
            fact = f"{merchant_name}: weekly operator check due ({template.replace('_', ' ')})"
            insight = "One thoughtful answer can unlock the next high-impact action."
            action = "I can draft the question and a suggested response option."
            strategy = "engage + curiosity"
        
        elif kind == "review_theme_emerged":
            theme = payload.get("theme", "service issue")
            mention_count = payload.get("mention_count", payload.get("occurrences_30d", 1))
            quote = payload.get("common_quote")
            quote_text = f"; quote: {quote}" if quote else ""
            fact = f"{merchant_name}: {theme} mentioned {mention_count} times in recent reviews{quote_text}"
            insight = "Addressing this publicly improves trust and conversion."
            action = "I can draft owner-response copy plus one operational fix note."
            strategy = "recover + fix"
        
        elif kind == "competitor_opened":
            competitor = payload.get("competitor_name", "competitor")
            distance = payload.get("distance_km", "nearby")
            their_offer = payload.get("their_offer")
            offer_text = f" with offer '{their_offer}'" if their_offer else ""
            fact = f"{merchant_name}: {competitor} opened {distance} km away{offer_text}"
            insight = "Positioning your strongest proof point now protects local share."
            action = "I can draft a differentiation post using your best-reviewed service."
            strategy = "loss_aversion"
        
        elif kind == "regulation_change":
            regulation = payload.get("top_item_id", payload.get("regulation", "compliance requirement"))
            regulation = str(regulation).replace("d_", "").replace("_", " ")
            if regulation.lower().startswith("dci "):
                regulation = "DCI " + regulation[4:]
            deadline = payload.get("deadline_iso", "soon")
            fact = f"{merchant_name}: {regulation} due by {deadline[:10]}"
            insight = "Acting early avoids penalties and last-minute disruption."
            action = "I can create a compliance checklist mapped to your clinic workflow."
            strategy = "inform + action"
        
        elif kind == "seasonal_perf_dip":
            season = payload.get("season", payload.get("season_note", "season"))
            delta = payload.get("delta_pct", 0)
            window = payload.get("window", "7d")
            fact = f"{merchant_name}: views down {int(abs(delta * 100))}% in {window} during {season}"
            insight = "This pattern is seasonal, so a tactical campaign can recover quickly."
            action = "I can draft a seasonal retention offer for your active members."
            strategy = "recover + reframe"
        
        elif kind == "perf_spike":
            metric = payload.get("metric", "performance")
            delta = payload.get("delta_pct", 0)
            baseline = payload.get("vs_baseline")
            likely_driver = payload.get("likely_driver")
            driver_text = f"; likely driver: {likely_driver}" if likely_driver else ""
            baseline_text = f" vs baseline {baseline}" if baseline is not None else ""
            fact = f"{merchant_name}: {metric} up {int(delta * 100)}%{baseline_text}{driver_text}"
            insight = "This momentum is strongest when amplified in the next 48 hours."
            action = "I can publish an amplify post built on the same driver."
            strategy = "capitalize + amplify"
        
        elif kind == "milestone_reached":
            milestone = payload.get("milestone", payload.get("metric", "milestone"))
            value = payload.get("value", payload.get("value_now", ""))
            target = payload.get("milestone_value")
            target_text = f" (next: {target})" if target else ""
            fact = f"{merchant_name}: {milestone} at {value}{target_text}"
            insight = "Sharing this milestone boosts trust and social proof."
            action = "I can draft a milestone announcement plus a conversion CTA."
            strategy = "capitalize + amplify"
        
        elif kind == "chronic_refill_due":
            meds = payload.get("molecule_list") or []
            med = ", ".join(meds[:2]) if meds else payload.get("medicine", "your refill")
            runout = payload.get("stock_runs_out_iso", "")
            fact = f"{merchant_name}: refill due for {med}; stock runs out by {str(runout)[:10]}"
            insight = "A timely refill reminder prevents treatment gaps."
            action = "I can send a patient-friendly refill reminder now."
            strategy = "convert + refill"
        
        elif kind == "renewal_due":
            plan = payload.get("plan", "plan")
            days = payload.get("days_remaining", merchant.get("subscription", {}).get("days_remaining", 0))
            amount = payload.get("renewal_amount")
            amount_text = f"; renewal amount ₹{amount}" if amount else ""
            fact = f"{merchant_name}: {plan} renews in {days} days{amount_text}"
            insight = "Don't let your benefits lapse."
            action = "I can prepare a one-tap renewal flow and post-renewal action plan."
            strategy = "retain + action"
        
        elif kind == "wedding_package_followup":
            wedding_date = payload.get("wedding_date", "soon")
            days_to_wedding = payload.get("days_to_wedding", 0)
            fact = f"{merchant_name}: wedding on {wedding_date} — {days_to_wedding} days away"
            insight = "Now is the ideal window to start skin-prep and trial sequencing."
            action = "I can schedule the first prep session and follow-up sequence."
            cta = "Reply 1 to book or 2 if not ready yet."
            cta_type = "multi_choice_slot"
            strategy = "convert + booking"
        
        elif kind == "trial_followup":
            trial_date = payload.get("trial_date", "recently")
            options = payload.get("next_session_options", [])
            option = options[0].get("label") if options else None
            option_text = f"; next slot: {option}" if option else ""
            fact = f"{merchant_name}: trial completed on {trial_date}{option_text}"
            insight = "Converting right after trial gives the best continuation rate."
            action = "I can send the follow-up booking message now."
            strategy = "convert + book"
        
        elif kind == "active_planning_intent":
            topic = payload.get("intent_topic", "a new idea")
            last_msg = payload.get("merchant_last_message", "")
            fact = f"{merchant_name}: planning intent detected — {topic.replace('_', ' ')}"
            insight = f"You already signaled intent: '{last_msg[:60]}'" if last_msg else "This is a high-intent growth opportunity."
            action = "I can draft a concrete rollout plan and first customer-facing message."
            strategy = "grow + execute"
        
        elif kind == "category_seasonal":
            season = payload.get("season", "season")
            trends = payload.get("trends", [])
            trend_headline = ", ".join(trends[:2]) if trends else "demand mix shifting"
            fact = f"{merchant_name}: {season} demand shift — {trend_headline}"
            insight = "Shelf and messaging tweaks now can capture seasonal demand."
            action = "I can draft a shelf-priority and promotion plan for this week."
            strategy = "inform + action"
        
        elif kind == "cde_opportunity":
            credits = payload.get("credits", 1)
            digest_item = _digest_item(payload.get("digest_item_id"))
            if digest_item:
                title = digest_item.get("title", "CDE session")
                when = str(digest_item.get("date", "")).replace("T", " ")[:16]
                fact = f"{merchant_name}: {title} ({credits} CDE credits) at {when}"
            else:
                fact = f"{merchant_name}: CDE webinar available ({credits} credits)"
            insight = "This is a low-effort way to upgrade clinical positioning."
            action = "I can send registration details and a patient-facing takeaway draft."
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
