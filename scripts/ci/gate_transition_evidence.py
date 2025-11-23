#!/usr/bin/env python3
"""Gate on transition evidence completeness."""

import json
import sys
from pathlib import Path


def main():
    """Check evidence completeness gate and exit with appropriate code."""
    ev_path = Path("data/processed/transitions_evidence.checks.json")

    if not ev_path.exists():
        print(
            f"::error file={ev_path}::Evidence checks JSON not found. Ensure transition_evidence_v1 ran."
        )
        sys.exit(2)

    data = json.loads(ev_path.read_text(encoding="utf-8"))
    comp = data.get("completeness") or {}
    complete = bool(comp.get("complete", False))

    print("Evidence checks:", json.dumps(comp, indent=2))

    if not complete:
        th = comp.get("threshold")
        ca = comp.get("candidates_above_threshold")
        er = comp.get("evidence_rows_for_above_threshold")
        print(f"::error::Evidence completeness gate failed: {er}/{ca} candidates at ≥{th}")
        sys.exit(1)

    print("Evidence completeness gate passed.")


if __name__ == "__main__":
    main()
