#!/usr/bin/env python3
"""Helper script for transition-mvp-run-gated Makefile target."""
import json
import sys
from pathlib import Path

summary_path = Path("reports/validation/transition_mvp.json")
if not summary_path.exists():
    print(f"Validation summary not found at {summary_path}", file=sys.stderr)
    sys.exit(2)

data = json.loads(summary_path.read_text(encoding="utf-8"))
gates = data.get("gates", {})
cs = gates.get("contracts_sample", {}) or {}
vr = gates.get("vendor_resolution", {}) or {}
failures = []

if not cs.get("passed", False):
    failures.append("contracts_sample coverage gate failed")

if not vr.get("passed", False):
    failures.append("vendor_resolution rate gate failed")

if failures:
    for f in failures:
        print(f"ERROR: {f}", file=sys.stderr)
    sys.exit(1)

print("Validation gates passed.")

