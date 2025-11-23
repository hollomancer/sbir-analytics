#!/usr/bin/env python3
"""Evaluate CET taxonomy completeness checks."""

import json
import sys
from pathlib import Path


def main():
    """Evaluate taxonomy checks and exit with appropriate code."""
    checks_path = Path("data/processed/cet_taxonomy_checks.json")

    try:
        with open(checks_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        print(f"Checks file not found at {checks_path}; skipping taxonomy evaluation.")
        sys.exit(0)

    comp = data.get("completeness", {}) or {}
    missing_required = bool(comp.get("missing_required_fields", False))
    mk = comp.get("areas_missing_keywords_count")
    if mk is None:
        ak = comp.get("areas_missing_keywords") or []
        mk = len(ak)
    total = comp.get("total_areas") or data.get("cet_count") or 0
    issues = missing_required or (mk > 0) or (total != 21)

    if issues:
        print(
            f"CET taxonomy checks failed: missing_required={missing_required} missing_keywords={mk} total={total}"
        )
        sys.exit(1)

    print("CET taxonomy checks passed.")


if __name__ == "__main__":
    main()
