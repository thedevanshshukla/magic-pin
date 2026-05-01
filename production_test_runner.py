from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DATASET_DIR = ROOT / "dataset"
DEFAULT_BOT_URL = "http://localhost:8000"
MAX_BODY_CHARS = 320
REQUEST_TIMEOUT = 10

FALLBACK_PATTERNS = [
    r"\bgeneric fallback\b",
    r"\bI can help with this\b",
    r"\bWant me to do this for you\?\b",
    r"\bThere's an update for your attention\b",
    r"\bGot it — here's what we can do next\b",
]


@dataclass
class ApiResponse:
    status: int
    body: dict[str, Any]
    elapsed: float


class RunnerError(RuntimeError):
    pass


class ProductionTestRunner:
    def __init__(self, bot_url: str, iterations: int = 5, start_backend: bool = True) -> None:
        self.bot_url = bot_url.rstrip("/")
        self.iterations = iterations
        self.start_backend = start_backend
        self.backend_process: subprocess.Popen[str] | None = None
        self.categories = self._load_json_dir(DATASET_DIR / "categories")
        self.merchants = self._load_seed_list(DATASET_DIR / "merchants_seed.json", "merchants")
        self.customers = self._load_seed_list(DATASET_DIR / "customers_seed.json", "customers")
        self.triggers = self._load_seed_list(DATASET_DIR / "triggers_seed.json", "triggers")
        self.context_by_scope: dict[str, dict[str, dict[str, Any]]] = {
            "category": {item["slug"]: item for item in self.categories.values()},
            "merchant": {item["merchant_id"]: item for item in self.merchants},
            "customer": {item["customer_id"]: item for item in self.customers},
            "trigger": {item["id"]: item for item in self.triggers},
        }
        self._merchant_to_customer = self._build_customer_index(self.customers)

    def _load_json_dir(self, folder: Path) -> dict[str, dict[str, Any]]:
        data: dict[str, dict[str, Any]] = {}
        if not folder.exists():
            return data
        for path in sorted(folder.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            key = payload.get("slug") or path.stem
            data[key] = payload
        return data

    def _load_seed_list(self, path: Path, key: str) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return list(payload.get(key, []))

    def _build_customer_index(self, customers: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        index: dict[str, list[dict[str, Any]]] = {}
        for customer in customers:
            index.setdefault(customer.get("merchant_id", ""), []).append(customer)
        return index

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> ApiResponse:
        url = f"{self.bot_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        request = Request(url, data=data, headers=headers, method=method)
        start = time.perf_counter()
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                raw = response.read().decode("utf-8")
                elapsed = time.perf_counter() - start
                return ApiResponse(response.status, json.loads(raw), elapsed)
        except URLError as exc:
            elapsed = time.perf_counter() - start
            raise RunnerError(f"request failed {method} {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            elapsed = time.perf_counter() - start
            raise RunnerError(f"invalid JSON from {method} {path}: {exc}") from exc

    def _assert(self, condition: bool, step: str, message: str) -> None:
        if not condition:
            raise RunnerError(f"FAILURE at step {step}: {message}")

    def _assert_json(self, response: ApiResponse, step: str) -> None:
        self._assert(response.status == 200, step, f"expected HTTP 200, got {response.status}")
        self._assert(response.elapsed < REQUEST_TIMEOUT, step, f"response exceeded {REQUEST_TIMEOUT}s ({response.elapsed:.2f}s)")

    def _ensure_backend(self) -> None:
        if not self.start_backend:
            return
        try:
            self._request("GET", "/v1/healthz")
            return
        except RunnerError:
            pass
        parsed = urlparse(self.bot_url)
        if parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise RunnerError(f"bot URL {self.bot_url} is not reachable and auto-start is only enabled for local hosts")
        self.backend_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", urlparse(self.bot_url).port and str(urlparse(self.bot_url).port) or "8000"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        deadline = time.perf_counter() + 30
        while time.perf_counter() < deadline:
            try:
                self._request("GET", "/v1/healthz")
                return
            except RunnerError:
                time.sleep(1)
        raise RunnerError("backend failed to start within 30s")

    def _reset(self) -> None:
        for path in ("/reset", "/v1/reset"):
            try:
                response = self._request("POST", path)
                self._assert_json(response, "reset")
                if response.body.get("status") in {"reset", "ok"}:
                    return
            except RunnerError:
                continue
        # Reset is optional in the brief; continue if absent.

    def _push_contexts(self, step_prefix: str = "phase1") -> None:
        for scope, items in (
            ("category", self.categories.values()),
            ("merchant", self.merchants),
            ("customer", self.customers),
            ("trigger", self.triggers),
        ):
            for item in items:
                if scope == "category":
                    context_id = item["slug"]
                else:
                    context_id = item[f"{scope}_id"] if f"{scope}_id" in item else item["id"]
                response = self._request(
                    "POST",
                    "/v1/context",
                    {
                        "scope": scope,
                        "context_id": context_id,
                        "version": int(item.get("version", 1)),
                        "payload": item,
                        "delivered_at": "2026-05-01T10:00:00Z",
                    },
                )
                self._assert_json(response, f"{step_prefix}:context:{scope}:{context_id}")
                self._assert(response.body.get("accepted") is True, f"{step_prefix}:context:{scope}:{context_id}", f"context rejected: {response.body}")

    def _check_health_and_metadata(self, expect_loaded_counts: bool = False) -> None:
        health = self._request("GET", "/v1/healthz")
        self._assert_json(health, "healthz")
        self._assert(health.body.get("status") == "ok", "healthz", f"unexpected health response: {health.body}")

        metadata = self._request("GET", "/v1/metadata")
        self._assert_json(metadata, "metadata")
        self._assert("team_name" in metadata.body or "team" in metadata.body, "metadata", f"metadata missing team fields: {metadata.body}")

        if expect_loaded_counts:
            counts = health.body.get("contexts_loaded", {})
            self._assert(counts.get("category", 0) >= len(self.categories), "healthz", "category count below expected baseline")
            self._assert(counts.get("merchant", 0) >= len(self.merchants), "healthz", "merchant count below expected baseline")
            self._assert(counts.get("customer", 0) >= len(self.customers), "healthz", "customer count below expected baseline")
            self._assert(counts.get("trigger", 0) >= len(self.triggers), "healthz", "trigger count below expected baseline")

    def _pick_customer(self, merchant_id: str) -> dict[str, Any] | None:
        customers = self._merchant_to_customer.get(merchant_id, [])
        return customers[0] if customers else None

    def _validate_body(self, body: str, step: str) -> None:
        self._assert(bool(body), step, "empty body")
        self._assert(len(body) <= MAX_BODY_CHARS, step, f"body too long ({len(body)} chars)")
        self._assert("http://" not in body and "https://" not in body, step, "body contains a URL")
        lower = body.lower()
        for pattern in FALLBACK_PATTERNS:
            self._assert(re.search(pattern, body, re.IGNORECASE) is None, step, f"generic fallback phrase matched: {pattern}")
        self._assert("fallback" not in lower, step, "fallback wording present")

    def _validate_action(self, action: dict[str, Any], step: str) -> None:
        for field in ("body", "merchant_id", "trigger_id"):
            self._assert(field in action and action[field], step, f"missing field '{field}' in action: {action}")
        self._validate_body(str(action["body"]), step)

    def _simulate_conversation(self, conversation_id: str, merchant_id: str, customer_id: str | None, base_body: str) -> None:
        first = self._request(
            "POST",
            "/v1/reply",
            {
                "conversation_id": conversation_id,
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "from_role": "merchant",
                "message": "tell me more",
                "received_at": "2026-05-01T10:05:00Z",
                "turn_number": 2,
            },
        )
        self._assert_json(first, "reply:interest")
        self._assert("action" in first.body, "reply:interest", f"missing action in reply: {first.body}")
        if first.body.get("action") == "send":
            self._validate_body(str(first.body.get("body", "")), "reply:interest")

        second = self._request(
            "POST",
            "/v1/reply",
            {
                "conversation_id": conversation_id,
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "from_role": "merchant",
                "message": "ok",
                "received_at": "2026-05-01T10:07:00Z",
                "turn_number": 3,
            },
        )
        self._assert_json(second, "reply:auto_ack")
        self._assert("action" in second.body, "reply:auto_ack", f"missing action in reply: {second.body}")

        third = self._request(
            "POST",
            "/v1/reply",
            {
                "conversation_id": conversation_id,
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "from_role": "merchant",
                "message": "actually cancel that",
                "received_at": "2026-05-01T10:09:00Z",
                "turn_number": 4,
            },
        )
        self._assert_json(third, "reply:intent_switch")
        self._assert("action" in third.body, "reply:intent_switch", f"missing action in reply: {third.body}")

    def _run_replay_case(self, conversation_id: str, merchant_id: str, customer_id: str | None, messages: list[str], step_prefix: str) -> None:
        for turn_number, message in enumerate(messages, start=2):
            response = self._request(
                "POST",
                "/v1/reply",
                {
                    "conversation_id": conversation_id,
                    "merchant_id": merchant_id,
                    "customer_id": customer_id,
                    "from_role": "merchant",
                    "message": message,
                    "received_at": f"2026-05-01T10:{4 + turn_number:02d}:00Z",
                    "turn_number": turn_number,
                },
            )
            self._assert_json(response, f"{step_prefix}:reply:{turn_number}")
            self._assert("action" in response.body, f"{step_prefix}:reply:{turn_number}", f"missing action in reply: {response.body}")
            if response.body.get("action") == "send":
                self._validate_body(str(response.body.get("body", "")), f"{step_prefix}:reply:{turn_number}")

    def _phase_tick(self, available_triggers: list[str], phase_name: str) -> list[dict[str, Any]]:
        response = self._request(
            "POST",
            "/v1/tick",
            {
                "now": "2026-05-01T10:00:00Z",
                "available_triggers": available_triggers,
            },
        )
        self._assert_json(response, phase_name)
        actions = response.body.get("actions", [])
        self._assert(isinstance(actions, list), phase_name, f"actions is not a list: {response.body}")
        self._assert(len(actions) <= 20, phase_name, f"too many actions: {len(actions)}")
        for idx, action in enumerate(actions, start=1):
            self._validate_action(action, f"{phase_name}:action:{idx}")
        return actions

    def run_cycle(self, cycle_index: int) -> None:
        self._reset()
        self._push_contexts(step_prefix=f"cycle{cycle_index}:load")
        self._check_health_and_metadata(expect_loaded_counts=True)

        available_triggers = [trigger["id"] for trigger in self.triggers]
        actions = self._phase_tick(available_triggers, f"cycle{cycle_index}:tick")
        if not actions:
            raise RunnerError(f"FAILURE at step cycle{cycle_index}:tick - no actions returned")

        for action in actions[:5]:
            self._simulate_conversation(
                action["conversation_id"],
                action["merchant_id"],
                action.get("customer_id"),
                str(action["body"]),
            )

        if self.triggers:
            trigger = next((item for item in self.triggers if item.get("kind") in {"perf_dip", "perf_spike", "seasonal_perf_dip", "renewal_due"}), self.triggers[0])
            merchant_id = trigger["merchant_id"]
            merchant = self.context_by_scope["merchant"][merchant_id]
            updated_merchant = json.loads(json.dumps(merchant))
            updated_merchant.setdefault("performance", {}).setdefault("delta_7d", {})
            updated_merchant["performance"]["views"] = int(updated_merchant["performance"].get("views", 0)) + 111
            updated_merchant["performance"]["delta_7d"]["views_pct"] = 0.42
            response = self._request(
                "POST",
                "/v1/context",
                {
                    "scope": "merchant",
                    "context_id": merchant_id,
                    "version": 2,
                    "payload": updated_merchant,
                    "delivered_at": "2026-05-01T10:15:00Z",
                },
            )
            self._assert_json(response, f"cycle{cycle_index}:update")
            self._assert(response.body.get("accepted") is True, f"cycle{cycle_index}:update", f"merchant update rejected: {response.body}")

            updated_trigger = {
                "id": f"runner_update_{cycle_index}_{trigger['id']}",
                "scope": "merchant",
                "kind": "perf_dip",
                "source": "internal",
                "merchant_id": merchant_id,
                "customer_id": None,
                "payload": {
                    "metric": "views",
                    "delta_pct": -0.12,
                    "window": "7d",
                    "vs_baseline": 9,
                },
                "urgency": 4,
                "suppression_key": f"runner_update:{cycle_index}:{merchant_id}",
                "expires_at": "2026-05-02T00:00:00Z",
            }
            trigger_response = self._request(
                "POST",
                "/v1/context",
                {
                    "scope": "trigger",
                    "context_id": updated_trigger["id"],
                    "version": 1,
                    "payload": updated_trigger,
                    "delivered_at": "2026-05-01T10:16:00Z",
                },
            )
            self._assert_json(trigger_response, f"cycle{cycle_index}:update_trigger")
            self._assert(trigger_response.body.get("accepted") is True, f"cycle{cycle_index}:update_trigger", f"updated trigger rejected: {trigger_response.body}")

            updated_actions = self._phase_tick([updated_trigger["id"]], f"cycle{cycle_index}:tick_after_update")
            if updated_actions:
                updated_body = str(updated_actions[0]["body"])
                self._validate_body(updated_body, f"cycle{cycle_index}:tick_after_update")
                self._assert(
                    str(updated_merchant["performance"]["views"]) in updated_body,
                    f"cycle{cycle_index}:tick_after_update",
                    "updated performance views not reflected in body",
                )

        auto_reply = self._request(
            "POST",
            "/v1/reply",
            {
                "conversation_id": "conv_auto_reply",
                "merchant_id": self.triggers[0]["merchant_id"],
                "customer_id": None,
                "from_role": "merchant",
                "message": "ok",
                "received_at": "2026-05-01T10:20:00Z",
                "turn_number": 2,
            },
        )
        self._assert_json(auto_reply, f"cycle{cycle_index}:auto_reply")
        self._assert(auto_reply.body.get("action") in {"end", "wait", "send"}, f"cycle{cycle_index}:auto_reply", f"unexpected reply action: {auto_reply.body}")

        hostile = self._request(
            "POST",
            "/v1/reply",
            {
                "conversation_id": "conv_hostile",
                "merchant_id": self.triggers[0]["merchant_id"],
                "customer_id": None,
                "from_role": "merchant",
                "message": "this is useless",
                "received_at": "2026-05-01T10:25:00Z",
                "turn_number": 2,
            },
        )
        self._assert_json(hostile, f"cycle{cycle_index}:hostile")
        if hostile.body.get("action") == "send":
            self._validate_body(str(hostile.body.get("body", "")), f"cycle{cycle_index}:hostile")

        intent_switch = self._request(
            "POST",
            "/v1/reply",
            {
                "conversation_id": "conv_intent_switch",
                "merchant_id": self.triggers[0]["merchant_id"],
                "customer_id": None,
                "from_role": "merchant",
                "message": "show offers",
                "received_at": "2026-05-01T10:30:00Z",
                "turn_number": 2,
            },
        )
        self._assert_json(intent_switch, f"cycle{cycle_index}:intent_switch_1")
        intent_switch_2 = self._request(
            "POST",
            "/v1/reply",
            {
                "conversation_id": "conv_intent_switch",
                "merchant_id": self.triggers[0]["merchant_id"],
                "customer_id": None,
                "from_role": "merchant",
                "message": "no wait cancel",
                "received_at": "2026-05-01T10:31:00Z",
                "turn_number": 3,
            },
        )
        self._assert_json(intent_switch_2, f"cycle{cycle_index}:intent_switch_2")
        if intent_switch_2.body.get("action") == "send":
            self._validate_body(str(intent_switch_2.body.get("body", "")), f"cycle{cycle_index}:intent_switch_2")

    def run(self) -> None:
        self._ensure_backend()
        print(f"[INFO] Bot: {self.bot_url}")
        for idx in range(1, self.iterations + 1):
            self.run_cycle(idx)
        print("ALL TESTS PASSED ✅")

    def close(self) -> None:
        if self.backend_process:
            self.backend_process.terminate()
            try:
                self.backend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.backend_process.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Production simulation runner for Magicpin judge compatibility")
    parser.add_argument("--bot_url", default=DEFAULT_BOT_URL, help="Base URL of the bot under test")
    parser.add_argument("--iterations", type=int, default=3, help="How many full cycles to run")
    parser.add_argument("--no-start-backend", dest="start_backend", action="store_false", help="Do not auto-start api.py when the local bot URL is unreachable")
    parser.set_defaults(start_backend=True)
    args = parser.parse_args()

    runner = ProductionTestRunner(args.bot_url, iterations=args.iterations, start_backend=args.start_backend)
    try:
        runner.run()
        return 0
    except RunnerError as exc:
        print(str(exc))
        return 1
    finally:
        runner.close()


if __name__ == "__main__":
    raise SystemExit(main())
