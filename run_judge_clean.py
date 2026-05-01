#!/usr/bin/env python3
import os
import pathlib
import subprocess
import sys

# Clean old judge reports
judge_dir = pathlib.Path("judge_reports")
for f in ["feedback_loop_summary.json", "latest_judge_report.json"]:
    fpath = judge_dir / f
    if fpath.exists():
        fpath.unlink()
        print(f"Deleted {f}")

# Run judge
print("\nRunning judge_feedback_loop.py...\n")
sys.exit(subprocess.call([sys.executable, "judge_feedback_loop.py"]))
