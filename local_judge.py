from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


ROOT = Path(__file__).parent
DATASET_DIR = ROOT / "dataset"
BOT_URL = "http://localhost:8000"
RANDOM_SEED = 7


@dataclass
class SimulationResult:
    merchant_id: str
    trigger_id: str
    message: str
    cta: str
    score: int
    reply_case: str
    reply_message: str | None
    bot_followup: dict[str, Any] | None


class LocalJudge:
    def __init__(self, bot_url: str = BOT_URL) -> None:
        self.bot_url = bot_url.rstrip("/")
        self.session = requests.Session()
        self.random = random.Random(RANDOM_SEED)
        self.categories = self._load_categories()
        self.merchants = self._load_seed_file("merchants_seed.json", "merchants", "merchant_id")
        self.customers = self._load_seed_file("customers_seed.json", "customers", "customer_id")
        self.triggers = self._load_seed_file("triggers_seed.json", "triggers", "id")
        self._backend_process: subprocess.Popen[str] | None = None

    def _load_categories(self) -> dict[str, dict[str, Any]]:
        categories: dict[str, dict[str, Any]] = {}
        for path in (DATASET_DIR / "categories").glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            categories[payload["slug"]] = payload
        return categories

    def _load_seed_file(self, filename: str, key: str, id_field: str) -> dict[str, dict[str, Any]]:
        payload = json.loads((DATASET_DIR / filename).read_text(encoding="utf-8"))
        return {item[id_field]: item for item in payload[key]}

    def start_backend(self) -> None:
        if self._is_healthy():
            print(f"Backend already running at {self.bot_url}")
            return
        print("Starting backend on localhost:8000 ...")
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "api:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ]
        self._backend_process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            if self._is_healthy():
                print("Backend is up.")
                return
            time.sleep(0.5)
        raise RuntimeError("Backend did not start within 20 seconds.")

    def stop_backend(self) -> None:
        if not self._backend_process:
            return
        self._backend_process.terminate()
        try:
            self._backend_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._backend_process.kill()
        self._backend_process = None

    def _is_healthy(self) -> bool:
        try:
            response = self.session.get(f"{self.bot_url}/v1/healthz", timeout=2)
            return response.ok
        except requests.RequestException:
            return False

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(f"{self.bot_url}{path}", json=payload, timeout=15)
        response.raise_for_status()
        return response.json()

    def push_all_context(self) -> None:
        delivered_at = self._now_iso()
        for slug, category in self.categories.items():
            self._push_context("category", slug, category, delivered_at)
        for merchant_id, merchant in self.merchants.items():
            self._push_context("merchant", merchant_id, merchant, delivered_at)
        for customer_id, customer in self.customers.items():
            self._push_context("customer", customer_id, customer, delivered_at)
        for trigger_id, trigger in self.triggers.items():
            self._push_context("trigger", trigger_id, trigger, delivered_at)

    def _push_context(self, scope: str, context_id: str, payload: dict[str, Any], delivered_at: str) -> None:
        body = {
            "scope": scope,
            "context_id": context_id,
            "version": 1,
            "payload": payload,
            "delivered_at": delivered_at,
        }
        data = self._post("/v1/context", body)
        if not data.get("accepted") and data.get("reason") != "stale_version":
            raise RuntimeError(f"Context push failed for {scope}/{context_id}: {data}")

    def simulate_single_trigger(self, trigger_id: str) -> SimulationResult | None:
        trigger = self.triggers[trigger_id]
        tick_payload = {
            "now": self._tick_now(trigger),
            "available_triggers": [trigger_id],
        }
        tick_response = self._post("/v1/tick", tick_payload)
        actions = tick_response.get("actions", [])
        if not actions:
            print(f"Merchant: {trigger['merchant_id']}")
            print(f"Trigger: {trigger_id}")
            print("Selected Action: none")
            print("--------")
            return None

        action = actions[0]
        score = self._score_message(action["body"], action["cta"], trigger)
        merchant = self.merchants[action["merchant_id"]]
        print(f"Merchant: {merchant['identity']['name']}")
        print(f"Trigger ID: {trigger_id}")
        print(f"Trigger Kind: {trigger.get('kind', 'Unknown')}")
        print(f"Selected Action: {action['send_as']}")
        print(f"Message: {action['body']}")
        print(f"CTA: {action['cta']}")
        print(f"Score: {score}/10")
        print("--------")

        reply_case, reply_message = self._simulate_reply_case(trigger, action)
        if reply_case == "no_reply":
            return SimulationResult(
                merchant_id=action["merchant_id"],
                trigger_id=trigger_id,
                message=action["body"],
                cta=action["cta"],
                score=score,
                reply_case=reply_case,
                reply_message=None,
                bot_followup=None,
            )

        reply_payload = {
            "conversation_id": action["conversation_id"],
            "merchant_id": action["merchant_id"],
            "customer_id": action["customer_id"],
            "from_role": "merchant" if action["customer_id"] is None else "customer",
            "message": reply_message,
            "received_at": self._now_iso(),
            "turn_number": 2,
        }
        followup = self._post("/v1/reply", reply_payload)
        print(f"Simulated Reply ({reply_case}): {reply_message}")
        print(f"Bot Response: {followup}")
        print("========")
        return SimulationResult(
            merchant_id=action["merchant_id"],
            trigger_id=trigger_id,
            message=action["body"],
            cta=action["cta"],
            score=score,
            reply_case=reply_case,
            reply_message=reply_message,
            bot_followup=followup,
        )

    def run_full_simulation(self) -> list[SimulationResult]:
        results: list[SimulationResult] = []
        for trigger_id in self.triggers:
            result = self.simulate_single_trigger(trigger_id)
            if result:
                results.append(result)
        self._print_summary(results)
        return results

    def _simulate_reply_case(self, trigger: dict[str, Any], action: dict[str, Any]) -> tuple[str, str]:
        cases = [
            ("positive", "yes"),
            ("auto_reply", "Thank you for contacting us. Our team will respond shortly."),
            ("negative", "not interested"),
            ("no_reply", ""),
        ]
        choice = cases[self.random.randrange(len(cases))]
        if trigger.get("kind") == "active_planning_intent":
            return "positive", "okay, do it"
        return choice

    def _score_message(self, body: str, cta: str, trigger: dict[str, Any]) -> int:
        score = 0
        if any(char.isdigit() for char in body):
            score += 2
        if "I can" in body:
            score += 2
        if cta and body.endswith(cta):
            score += 2
        merchant = self.merchants[trigger["merchant_id"]]
        owner = merchant.get("identity", {}).get("owner_first_name", "")
        if owner and owner in body:
            score += 2
        if len(body) < 220:
            score += 2
        return score

    def _tick_now(self, trigger: dict[str, Any]) -> str:
        expires_at = trigger.get("expires_at")
        if expires_at:
            try:
                expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                candidate = expiry - timedelta(minutes=1)
                return candidate.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            except ValueError:
                pass
        return self._now_iso()

    def _print_summary(self, results: list[SimulationResult]) -> None:
        if not results:
            print("No messages were produced.")
            return
        avg_score = sum(item.score for item in results) / len(results)
        reply_breakdown: dict[str, int] = {}
        for item in results:
            reply_breakdown[item.reply_case] = reply_breakdown.get(item.reply_case, 0) + 1
        print("\nSummary")
        print(f"Messages sent: {len(results)}")
        print(f"Average heuristic score: {avg_score:.2f}/10")
        print(f"Reply cases: {reply_breakdown}")

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Vera judge simulator")
    parser.add_argument("--bot-url", default=BOT_URL, help="Bot base URL")
    parser.add_argument("--trigger-id", help="Run only a single trigger")
    parser.add_argument("--no-start", action="store_true", help="Do not start backend automatically")
    args = parser.parse_args()

    judge = LocalJudge(bot_url=args.bot_url)
    try:
        if not args.no_start:
            judge.start_backend()
        judge.push_all_context()
        if args.trigger_id:
            judge.simulate_single_trigger(args.trigger_id)
        else:
            judge.run_full_simulation()
    finally:
        if not args.no_start:
            judge.stop_backend()


if __name__ == "__main__":
    main()
