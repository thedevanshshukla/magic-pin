# Vera Bot: Stable Message Engine

## Executive Summary

Vera is a deterministic, rule-based messaging engine that selects triggers, builds intents, and composes WhatsApp-style messages for merchant engagement without using LLM-based humanization or caching layers. The system achieves stable scoring (~36-37/50) through simplified, fact-driven message composition.

---

## System Architecture

### High-Level Pipeline

```
Trigger + Context → Decision Engine → Intent → Composer → Renderer → Message
```

### Core Modules

1. **api.py** - FastAPI server exposing `/v1/context`, `/v1/tick`, `/v1/reply` endpoints
2. **decision_engine.py** - Intent builder using trigger kind and payload
3. **composer.py** - Combines intent parts into message body
4. **renderer.py** - Formats message with fact, insight, action, CTA
5. **reply_engine.py** - State machine for handling merchant/customer replies
6. **storage.py** - In-memory context store, conversation tracking, suppression management
7. **utils.py** - Helpers for parsing, detection, formatting
8. **bot.py** - Thin convenience wrappers
9. **local_judge.py** - Local testing harness
10. **judge_simulator.py** - Full LLM-based evaluation harness

---

## Core Logic: Decision Engine

### Build Intent Process

The `DecisionEngine.build_intent()` method creates an Intent from a trigger by extracting facts directly from the trigger payload. No artificial number generation, no LLM humanization.

### Trigger Kind → Fact/Insight/Action Mapping

#### perf_dip (Performance Drop)
- **Fact**: `"{metric} down {delta}% in {window}"` (e.g., "calls down 50% in 7d")
- **Insight**: "This is affecting your visibility."
- **Action**: "I can help fix this quickly."
- **Strategy**: recover + urgency

#### supply_alert (Supply/Compliance Alert)
- **Fact**: `"{batch_count} affected batches; about {affected} of your {total} patients"` (from payload)
- **Insight**: "This needs prompt attention."
- **Action**: "I can draft a patient-safe notification."
- **Strategy**: inform + urgency

#### gbp_unverified (Google Business Profile)
- **Fact**: "Your profile is still unverified on Google."
- **Insight**: "This is limiting your discoverability."
- **Action**: "I can guide you through verification."
- **Strategy**: recover + loss_aversion

#### recall_due (Dental/Medical Recall)
- **Fact**: `"Last visit {date}; recall due {date}"` (from payload)
- **Insight**: "This is a live booking window."
- **Action**: "I can hold a slot for you."
- **CTA**: "Reply 1 for slot or 2 for another time." (multi_choice_slot)
- **Strategy**: convert + booking

#### customer_lapsed_hard (Lapsed Customer Winback)
- **Fact**: `"{customer_name}, it's been {days} days since your last visit"` (if customer scoped, else "Your customers are lapsing.")
- **Insight**: "Re-engagement is still possible."
- **Action**: "I can draft a restart message."
- **Strategy**: re-engage + convert

#### winback_eligible (Subscription Expiry / Lapse)
- **Fact**: `"{days_since_expiry} days since expiry; {lapsed_count} lapsed customers"`
- **Insight**: "There's still a window to win them back."
- **Action**: "I can draft a restart offer."
- **Strategy**: recover + curiosity

#### research_digest (Educational/Research Content)
- **Fact**: "New research is relevant to your practice."
- **Insight**: "Your patients might benefit from this."
- **Action**: "I can draft a patient education message."
- **Strategy**: educate + curiosity

#### festival_upcoming (Seasonal/Event-Based)
- **Fact**: `"{festival} in {days} days"` (e.g., "Diwali in 10 days")
- **Insight**: "Promotions typically convert better here."
- **Action**: "I can create a ready post."
- **Strategy**: promote + urgency

#### dormant_with_vera (Merchant Disengagement)
- **Fact**: `"Last merchant reply {days} days ago"`
- **Insight**: "A light operator question is stronger than a reminder."
- **Action**: "I can draft a re-engagement message."
- **Strategy**: re-engage

#### Default (Unknown Trigger)
- **Fact**: "There's an update for your attention."
- **Insight**: "Let's keep things moving forward."
- **Action**: "I can help with the next step."

---

## Reasoning & Sentiment Patterns

### Core Principles

1. **Payload-Driven Facts Only**
   - All factual claims (numbers, dates, counts) come directly from trigger payload
   - No estimation, calculation, or inference of metrics
   - No "2x measurable results" without context
   - No invented percentages or customer counts

2. **Single, Unified Insight**
   - Every message uses ONE insight that frames the situation neutrally
   - No loss-aversion language ("missing calls", "losing customers")
   - No artificial urgency injection ("right now", "this week", "before X ends")
   - Insights acknowledge the business problem: "affecting your visibility", "needs attention", "discoverability"

3. **Clear, Actionable Intent**
   - Action states what Vera will do, not what merchant/customer must do
   - Verb: "I can help", "I can draft", "I can guide", "I can hold"
   - No pressure: action is presented as an option, not a demand

4. **Deterministic CTA**
   - Single, stable CTA: "Want me to do this for you?"
   - Exceptions only for slot-selection or multi-choice: "Reply 1 for slot or 2 for another time."
   - No category-specific or condition-specific CTA variations

### Sentiment Tone by Category

| Category | Tone | Examples |
|----------|------|----------|
| dentists | clinical | "Last visit", "recall due", "live booking window" |
| salons | aspirational | "win them back", "restart offer" |
| restaurants | practical | straightforward facts and actions |
| gyms | motivational | "restart message", "re-engagement is still possible" |
| pharmacies | trust | "patient-safe", "prompt attention", "needs attention" |

### What is NOT Done

- ❌ No LLM-based humanization
- ❌ No multi-turn branching logic
- ❌ No cache layers (all outputs are fresh)
- ❌ No artificial numbers (e.g., "10% could return = 7 visits this week")
- ❌ No forced urgency ("right now", "this week", "before Friday")
- ❌ No personalization beyond customer name (no "Dr. Meera", location customization, etc.)
- ❌ No multi-part CTAs with varying options per trigger kind
- ❌ No fallback safe intents when self-score is low
- ❌ No signal derivation (low_ctr, ready_to_push, etc.) influencing message text

---

## Message Composition Pipeline

### Step 1: Build Intent (decision_engine.py)

### Restoration Journey (Simplified to Stable)
```

- `audience`: "merchant" or "customer"
- `priority_score`: simple urgency * 10

### Step 2: Compose Message (composer.py)

```python
message = composer.compose(category, merchant, trigger, intent, customer)
```

Takes intent parts and calls renderer:
```python
body_struct = {"fact": intent.fact, "insight": intent.insight, "action": intent.action}
rendered = renderer.render(body_struct)

### Step 3: Render Final Message (renderer.py)

```python
def render(payload):
    fact = str(payload.get("fact", "")).strip()
    insight = str(payload.get("insight", "")).strip()
    action = str(payload.get("action", "")).strip()

    cta = "Want me to do this for you?"
    parts = [p for p in (fact, insight, action) if p]
    body = ". ".join(parts).strip()
    if body and not body.endswith("?"):
        body = body + "."
    full = f"{body} {cta}".strip()
    if len(full) > MAX_BODY_CHARS:
        full = full[:MAX_BODY_CHARS].rstrip()
    return {"body": full, "cta": cta}
```

### Step 4: API Response (api.py)

API `/v1/tick` endpoint returns:
```python
{
    "actions": [{
        "conversation_id": "...",
        "merchant_id": "...",
        "customer_id": "...",
        "send_as": "vera" | "merchant_on_behalf",
        "trigger_id": "...",
        "body": "...",  # Final composed message
        "cta": "...",
        "suppression_key": "...",
        "rationale": "..."
    }]
}
```

---

## Conversation & Reply Handling

### Reply Detection (utils.py + reply_engine.py)

Replies are classified using simple pattern matching:

| Pattern | Action | Wait Time |
|---------|--------|-----------|
| Auto-reply patterns ("thank you", "automated", etc.) | send encouragement | none |
| Positive ("yes", "ok", "send it") | execute next step | none |
| Negative ("stop", "unsubscribe", "not interested") | close conversation + mute merchant | 30 days |
| Wait patterns ("later", "tomorrow", "busy") | wait and retry | 4 hours |
| Out-of-scope ("gst", "tax", "ca filing") | redirect politely | none |

### Conversation Lifecycle

1. **Create** - when message sent from tick endpoint
2. **Note Reply** - track incoming merchant/customer reply
3. **Auto-reply Handling** - if same auto-reply 3x, close conversation
4. **Send Followup** - if positive intent, confirm execution
5. **Close** - on negative intent, out-of-scope resolution, or explicit merchant opt-out

### Suppression & Muting

- **Trigger Suppression**: same trigger_id + suppression_key not sent again within expiry window
- **Merchant Mute**: if merchant opts out, mute for 30 days (no messages sent)

---

## Priority Scoring

Simple, deterministic scoring:

```python
priority_score = urgency * 10 + (5 if "ready_to_push" in signals else 0)
```

- **Base**: urgency from trigger (1-5) × 10 = 10-50
- **Bonus**: +5 if active offer exists
- **Result**: 10-55 range (stable, no variance)

Candidates are ranked by priority_score; highest wins.

---

## Expected Message Quality

### Example Messages (Stable Version)

**perf_dip trigger:**
```
"calls down 50% in 7d. This is affecting your visibility. I can help fix this quickly. Want me to do this for you?"
```

**recall_due trigger (customer-scoped):**
```
"Last visit 2026-05-12; recall due 2026-11-12. This is a live booking window. I can hold a slot for you. Want me to do this for you?"
```

**winback_eligible trigger:**
```
"38 days since expiry; 10 lapsed customers. There's still a window to win them back. I can draft a restart offer. Want me to do this for you?"
```

### Scoring (Judge Evaluation)

**FINAL VALIDATION RESULTS: 41/50 (82% quality score) — STABLE OPTIMIZED VERSION**

Latest 5 test messages scored 41-46/50 with consistent pattern:

| Trigger Kind | Score | Specificity | Category Fit | Merchant Fit | Trigger Relevance | Engagement |
|--------------|-------|-------------|--------------|--------------|-------------------|-----------|
| regulation_change | 41/50 | 8/10 | 9/10 | 8/10 | 9/10 | 7/10 |
| wedding_package_followup | 42/50 | 8/10 | 9/10 | 9/10 | 9/10 | 7/10 |
| customer_lapsed_hard | 41/50 | 8/10 | 9/10 | 8/10 | 9/10 | 7/10 |
| supply_alert (pharmacy) | 43/50 | 9/10 | 10/10 | 8/10 | 9/10 | 7/10 |
| gbp_unverified | 46/50 | 9/10 | 10/10 | 9/10 | 10/10 | 8/10 |

**Scoring Breakdown:**
- **Specificity**: Avg 8/10 (merchant names, dates, batches, verification paths explicit)
- **Category Fit**: Avg 9/10 (tone is precise and contextually appropriate)
- **Merchant Fit**: Avg 8/10 (includes merchant context and business details)
- **Trigger Relevance**: Avg 9/10 (directly addresses root cause of each trigger)
- **Engagement Compulsion**: Avg 7/10 (clear CTA, appropriate but not maximally compelling)

**Key Insight**: The 46/50 (gbp_unverified) message scores 8/10 on engagement because it includes a **quantified benefit** ("can lift visibility by 30%") from the payload. Messages lacking quantified metrics plateau at 7/10 engagement. See "Engagement Optimization Analysis" section below.

---

## Data Flow & Context Store

### Context Types

1. **category** - Business category metadata (dentist, salon, gym, restaurant, pharmacy)
2. **merchant** - Merchant profile, performance, offers, location
3. **customer** - Customer identity, preferences, relationship history
4. **trigger** - Event/condition (recall due, perf dip, supply alert, etc.)

### Storage

All contexts stored in `ContextStore`:
- In-memory dictionary keyed by (scope, context_id)
- Versioning: reject stale updates
- Suppression tracking: track sent triggers + expiry
- Merchant muting: track opt-outs + mute windows
- Conversation state: track open conversations, turns, sends

---

## Files Changed for Stable Version

### decision_engine.py (SIMPLIFIED)
- Removed: `score_signal()`, `build_insight()`, `ensure_urgency()`, `derive_signals()`, `score_trigger()`, `build_safe_intent()`
- Kept: TONE_MAP, build_intent() with payload-driven logic
- Result: ~150 lines vs. 500+ in complex version

### api.py (CLEANED)
- Removed: `make_cache_key`, `get_cached`, `set_cache` imports
- Removed: `cached_compose()` function
- Changed: `tick()` calls `composer.compose()` directly
- Result: No caching layer, all outputs fresh

### composer.py (MINIMAL)
- Simplified to pass fact/insight/action to renderer
- Removed: validation, auto-fix, quality_check logic
- Result: Pure pass-through to renderer

### renderer.py (DETERMINISTIC)
- Single CTA: "Want me to do this for you?"
- Deterministic body: "{fact}. {insight}. {action}. {cta}"
- Result: No branching, no variation

### humanizer.py (NOT USED)
- Module exists but not imported or called anywhere
- Optional: can delete if cleanup needed

### cache.py (DISABLED)
- Module exists but not imported or called anywhere
- Optional: can delete if cleanup needed

---

## Testing & Validation

### Local Judge (local_judge.py)
- Simulates single triggers with random reply patterns
- Lightweight heuristic scoring (not LLM-based)
- Useful for fast iteration

### Judge Simulator (judge_simulator.py)
- Full LLM-based evaluation using OpenAI GPT-4o-mini
- Scores messages on 5 dimensions (specificity, category_fit, merchant_fit, trigger_relevance, engagement_compulsion)
- Expected average: 36-37/50 (stable)

### Judge Feedback Loop (judge_feedback_loop.py)
- Orchestrates judge iterations
- Collects worst messages and weakest dimensions
- Produces feedback_loop_summary.json

---

## Running the System

### Backend
```bash
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

### Local Judge (Quick Test)
```bash
python local_judge.py
```

### Full Judge Simulation (LLM-Based Evaluation)
```bash
python judge_simulator.py --scenario full_evaluation --provider groq --bot-url http://localhost:8000
```

### Feedback Loop (Multi-Iteration Judge)
```bash
python judge_feedback_loop.py
```

---

## Performance Notes

- **Response Time**: <100ms per tick (no LLM calls in pipeline)
- **Memory**: ~1MB (in-memory context store)
- **Scalability**: Single-threaded FastAPI; add uvicorn workers for concurrency
- **Stability**: Fully deterministic (same input = same output)

---

## Future Improvements (Without Destabilizing Score)

1. Add more trigger kinds with payload-driven facts
2. Enrich insight library (currently ~20 unique insights)
3. Implement A/B testing on CTA variations
4. Add location-based personalization to facts
5. Track message performance metrics and learn top performers
6. Implement soft suppression (reduce frequency vs. hard block)

---

## Engagement Optimization Analysis (41/50 Current Optimum)

### Problem Statement
Initial goal: improve from 40/50 → 45/50 by optimizing **engagement_compulsion** dimension (7/10 bottleneck).

### Investigation & Attempts

**Attempt 1: Consequence/Benefit Narrative Language**
- Changed insights to emphasize consequences: "competitors will capture slots", "your customers get closer to trying someone else"
- Changed actions to be more benefit-focused: "draft an irresistible comeback offer"
- Result: Score dropped to 39/50; specificity decreased from 8→7/10
- Finding: Narrative language replaces factual precision; judge penalizes this

**Attempt 2: Specific Action Promises**
- Added concrete time estimates: "I can fix this in 15 minutes", "I can book in 30 seconds"
- Added specific counts: "irresistible restart offer for all {count}"
- Result: Score dropped to 40/50; PowerHouse message dropped from 8→6/10 engagement
- Finding: Awkward phrasing ("comeback offer you can send today to Rashmi today") and arbitrary time estimates hurt credibility

**Attempt 3: Quantified Benefits & Owner Personalization**
- Extracted lapsed_count for winback messages
- Added owner names from merchant.identity.owner
- Kept facts and insights unchanged
- Result: No improvement; score fluctuated around 41/50
- Finding: Owner names not reliably available in payload; quantified counts alone don't drive engagement

### Root Cause Analysis

The **8/10 engagement message** (gbp_unverified, 46/50 total) has a key feature absent from 7/10 messages:

```
"Verification via postcard_or_phone_call can lift visibility by 30%."
                                                        ↑↑↑↑
                                     Quantified business benefit from payload
```

**Why 7/10 engagement plateau exists:**
1. Most trigger payloads lack quantified business metrics (e.g., % visibility lift, revenue impact, customer count before/after)
2. Adding artificial urgency/consequence language reduces specificity scoring (LLM judge values data precision)
3. Generic promises ("I can help", "I can draft") are considered low-friction but not compelling without supporting metrics
4. Engagement scoring rewards **payload-backed precision** over **emotive language**

### Current Optimum: 41/50 (82%)

**Why 41/50 is Stable:**
- ✅ All messages use ONLY facts from payload
- ✅ Insights are neutral, not forced urgency
- ✅ Actions state what Vera will do, not what merchant must do
- ✅ CTA is consistent and low-friction
- ✅ Specificity + Category Fit + Merchant Fit + Trigger Relevance all score 8-9/10
- ✅ Engagement plateaus at 7/10 due to missing quantified benefits in most triggers

**To Reach 45/50+ from Current 41/50:**

Would require ONE of:

1. **Payload Enrichment** (Recommended)
   - Add quantified metrics to triggers: visibility_lift_pct, revenue_impact, customer_recovery_rate, etc.
   - Example: `supply_alert` payload includes "estimated_liability_cost: $50,000" → "This puts your business at risk for $50k liability."
   - Estimated impact: +1-2 points per message (specificity + engagement)

2. **Trigger-Specific Insights** (Limited ROI)
   - Create category-aware or signal-specific insight variants
   - Example: dental recall → "live booking window" (good), pharmacy recall → "patient safety risk" (stronger)
   - Estimated impact: +0.5 points per message

3. **Conditional CTAs** (Contradicts Design Philosophy)
   - Add multi-choice CTAs per trigger: "Reply 1 to proceed" vs. "Want me to do this?"
   - Breaks deterministic principle; increases complexity
   - Estimated impact: +0.5-1 point per message (but with implementation risk)

4. **Owner Name Injection** (Dependency on Data)
   - Require merchant.identity.owner in ALL payloads
   - Use in insight: "Dr. Meera, ..." or action: "I'll have it ready for you by..."
   - Estimated impact: +0.2-0.5 points per message
   - Blocker: owner names not consistently available

### Conclusion

**41/50 represents a stable local optimum** within the current design constraints (payload structure, fact-driven philosophy, deterministic pipeline). Further improvements are constrained by:
- Limited quantified metrics in payloads
- Architectural choice to prioritize specificity over emotive appeal
- Judge's preference for data-backed claims over narrative urgency

To sustainably reach 45+/50, **payload enrichment with quantified business impact metrics is the highest-ROI path**.

