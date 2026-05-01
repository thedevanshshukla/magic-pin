from __future__ import annotations

import json
from pathlib import Path

from bot import compose
from decision_engine import DecisionEngine


ROOT = Path(__file__).parent
DATASET = ROOT / "dataset"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    categories = {
        slug: load_json(path)
        for path in (DATASET / "categories").glob("*.json")
        for slug in [path.stem]
    }
    merchants = load_json(DATASET / "merchants_seed.json")["merchants"]
    customers = {item["customer_id"]: item for item in load_json(DATASET / "customers_seed.json")["customers"]}
    triggers = load_json(DATASET / "triggers_seed.json")["triggers"]
    engine = DecisionEngine()

    for merchant in merchants:
        category = categories[merchant["category_slug"]]
        print("=" * 100)
        print(f"{merchant['merchant_id']} | {merchant['identity']['name']} | {merchant['category_slug']}")
        merchant_triggers = [t for t in triggers if t.get("merchant_id") == merchant["merchant_id"]]
        scored = []
        for trigger in merchant_triggers:
            customer = customers.get(trigger.get("customer_id")) if trigger.get("customer_id") else None
            score_info = engine.score_trigger(category, merchant, trigger, customer)
            scored.append((score_info["score"], trigger, customer, score_info))
        for score, trigger, customer, score_info in sorted(scored, key=lambda item: item[0], reverse=True):
            message = compose(category, merchant, trigger, customer)
            who = customer["identity"]["name"] if customer else "merchant"
            print(f"[{score:02d}] {trigger['id']} -> {who}")
            print(f"  reasons: {', '.join(score_info['reasons'])}")
            print(f"  body: {message['body']}")
            print(f"  cta: {message['cta']}")
            print()


if __name__ == "__main__":
    main()
