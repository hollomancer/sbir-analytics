#!/usr/bin/env python3
"""Generate a GitHub Actions step summary table from benchmark evaluation JSON."""

import json
import sys
from pathlib import Path


def fmt(val):
    return f"{val:,}" if isinstance(val, (int, float)) else str(val)


def main():
    eval_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/scripts_output/benchmark_evaluation.json")
    if not eval_path.exists():
        print("Benchmark evaluation file not found.", file=sys.stderr)
        sys.exit(1)

    with open(eval_path) as f:
        d = json.load(f)

    print("| Metric | Count |")
    print("|--------|-------|")
    for key, label in [
        ("total_companies_evaluated", "Companies evaluated"),
        ("companies_subject_to_transition", "Subject to transition benchmark"),
        ("companies_failing_transition", "Failing transition benchmark"),
        ("companies_subject_to_commercialization", "Subject to commercialization benchmark"),
        ("companies_failing_commercialization", "Failing commercialization benchmark"),
    ]:
        print(f"| {label} | {fmt(d.get(key, 0))} |")


if __name__ == "__main__":
    main()
