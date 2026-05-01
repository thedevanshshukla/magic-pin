# Magicpin Challenge Deliverable and Deployment Steps

This file translates the requirements from:
- `challenge-brief.md` (what to submit)
- `challenge-testing-brief.md` (how the judge tests and what must be deployed)

It is tailored to this repository.

## 1. What You Must Deliver

There are two practical delivery modes in the briefs. Prepare both.

### Mode A: Artifact submission package (from challenge brief section 7)

Required files:
1. `bot.py`
2. `submission.jsonl` (30 lines, one per canonical test pair)
3. `README.md` (1 page: approach, tradeoffs, needed context)

Optional:
1. `conversation_handlers.py` (multi-turn responder)

### Mode B: Live endpoint deployment (from testing brief)

You must expose a public base URL with these endpoints:
1. `GET /v1/healthz`
2. `GET /v1/metadata`
3. `POST /v1/context`
4. `POST /v1/tick`
5. `POST /v1/reply`

Submit the public URL to the portal.

## 2. What This Repo Already Has

Present in repo:
1. `api.py` with required API endpoints (+ `/reset` helper)
2. `bot.py` compose entrypoint
3. `judge_simulator.py` and `judge_feedback_loop.py` local validation harnesses
4. Deterministic baseline committed at 41/50

Still needed for final submission package:
1. `submission.jsonl` (if artifact mode is required)
2. `README.md` (challenge-facing, concise)

## 3. Delivery Checklist (Do This In Order)

## Step 1: Environment setup

```powershell
python -m pip install -r requirements.txt
```

## Step 2: Start server locally

```powershell
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

If port 8000 is busy:

```powershell
netstat -ano | findstr ":8000"
Stop-Process -Id <PID> -Force
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

## Step 3: Run local judge checks

```powershell
python judge_simulator.py --scenario all --provider groq --bot-url http://localhost:8000
```

```powershell
$env:JUDGE_ITERATIONS='3'
python judge_feedback_loop.py
```

Pass criteria:
1. Context push passes
2. No context failures
3. Score baseline remains around 41/50

## Step 4: Prepare submission artifacts

Create or update:
1. `README.md` with:
   - approach
   - determinism choices
   - context handling strategy
   - known limits
2. `submission.jsonl` with exactly 30 lines (one per official test pair)

Expected JSONL shape per line:

```json
{"test_id":"T01","body":"...","cta":"open_ended","send_as":"vera","suppression_key":"...","rationale":"..."}
```

## Step 5: Deploy public endpoint

Deploy app so the judge can reach it at:
- `https://<host>/v1/*`

Minimum deployment checks:
1. Public health works: `/v1/healthz`
2. Metadata returns team info: `/v1/metadata`
3. `/v1/tick` returns within 10s
4. `/v1/reply` returns within 10s
5. No URLs in generated message bodies
6. Message body length <= 320 chars

## Step 6: Pre-submission hard gate

Use this final gate before submitting URL:
1. Endpoint reachable publicly
2. All 5 endpoints return valid JSON schema
3. Context ingestion is idempotent/overwrite-safe
4. No timeout in local harness
5. `submission.jsonl` has 30 valid lines
6. `README.md` is present and concise
7. URL submitted in portal

## 4. Suggested Packaging Structure

If you want a clean handoff folder, package this set:
1. `api.py`
2. `bot.py`
3. `decision_engine.py`
4. `composer.py`
5. `renderer.py`
6. `reply_engine.py`
7. `storage.py`
8. `utils.py`
9. `requirements.txt`
10. `README.md`
11. `submission.jsonl`

Avoid packaging runtime artifacts:
1. `__pycache__/`
2. `judge_reports/`

## 5. Definition of Done for This Project

This project is "delivery ready" when:
1. Local 3-iteration feedback loop stays stable at ~41/50
2. Context push has no failures
3. Public URL serves all required endpoints
4. `submission.jsonl` + `README.md` are complete
5. Final dry run using deployed URL succeeds
