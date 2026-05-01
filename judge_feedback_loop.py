from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib import error as urlerror
from urllib import request as urlrequest
import requests

from judge_simulator import REPORTS_DIR, run_judge_session

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


ROOT = Path(__file__).parent
BOT_URL = os.getenv("BOT_URL", "http://localhost:8000")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", str(urlparse(BOT_URL).port or 8000)))
ITERATIONS = int(os.getenv("JUDGE_ITERATIONS", "1"))


def backend_is_up() -> bool:
    try:
        with urlrequest.urlopen(f"{BOT_URL}/v1/healthz", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def start_backend() -> subprocess.Popen[str] | None:
    if backend_is_up():
        return None
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "api:app",
        "--host",
        HOST,
        "--port",
        str(PORT),
    ]
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        if backend_is_up():
            return process
        time.sleep(1)
    process.terminate()
    raise RuntimeError("Backend failed to start within 30s")


def stop_backend(process: subprocess.Popen[str] | None) -> None:
    if not process:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def summarize_report(report: dict) -> dict:
    messages = report.get("messages", [])
    if not messages:
        return {
            "message_count": 0,
            "average_scores": report.get("average_scores", {}),
            "worst_messages": [],
            "weakest_dimensions": {},
        }

    totals = {
        "specificity": [],
        "category_fit": [],
        "merchant_fit": [],
        "trigger_relevance": [],
        "engagement_compulsion": [],
    }
    for message in messages:
        scores = message.get("scores", {})
        for key in totals:
            totals[key].append(scores.get(key, 0))

    weakest = {
        key: round(sum(values) / len(values), 2) if values else 0
        for key, values in totals.items()
    }
    worst_messages = sorted(messages, key=lambda item: item.get("scores", {}).get("total", 0))[:5]
    return {
        "message_count": len(messages),
        "average_scores": report.get("average_scores", {}),
        "weakest_dimensions": dict(sorted(weakest.items(), key=lambda item: item[1])),
        "worst_messages": worst_messages,
    }


def main() -> int:
    process = None
    try:
        process = start_backend()
        iterations: list[dict] = []
        for index in range(1, ITERATIONS + 1):
            try:
                requests.post(f"{BOT_URL}/reset", timeout=10)
            except Exception:
                requests.post(f"{BOT_URL}/v1/reset", timeout=10)
            print(f"Running judge iteration {index}/{ITERATIONS}...")
            report = run_judge_session(scenario="full_evaluation", provider=os.getenv("LLM_PROVIDER", "groq"), bot_url=BOT_URL)
            summary = summarize_report(report)
            iterations.append({
                "iteration": index,
                "summary": summary,
                "report_path": report.get("report_path", str(REPORTS_DIR / "latest_judge_report.json")),
            })
            avg_total = summary.get("average_scores", {}).get("total", 0)
            print(f"Average total: {avg_total}/50")
            weakest = summary.get("weakest_dimensions", {})
            if weakest:
                weakest_name, weakest_score = next(iter(weakest.items()))
                print(f"Focus next on: {weakest_name} ({weakest_score})")
            print("Worst 5 messages:")
            for m in summary.get("worst_messages", []):
                score = m.get("scores", {}).get("total", 0)
                body = m.get("action", {}).get("body", "")
                print(f"  - Score: {score} | Msg: {body}")

        output = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "bot_url": BOT_URL,
            "iterations": iterations,
        }
        REPORTS_DIR.mkdir(exist_ok=True)
        dt_str = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        output_path = REPORTS_DIR / f"feedback_loop_summary_{dt_str}.json"
        output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(f"Saved feedback loop summary to {output_path}")
        return 0
    finally:
        stop_backend(process)


if __name__ == "__main__":
    raise SystemExit(main())
