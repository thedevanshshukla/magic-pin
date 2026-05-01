import json
import hashlib
import time

CACHE = {}
CACHE_TTL = 300  # 5 minutes

def make_cache_key(category, merchant, trigger, customer):
    payload = {
        "category": category,
        "merchant": merchant,
        "merchant_version": merchant.get("version"),
        "trigger": trigger,
        "trigger_payload": trigger.get("payload"),
        "customer": customer
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()

def get_cached(key):
    if key in CACHE:
        value, ts = CACHE[key]
        if time.time() - ts < CACHE_TTL:
            return value
    return None

def set_cache(key, value):
    CACHE[key] = (value, time.time())
