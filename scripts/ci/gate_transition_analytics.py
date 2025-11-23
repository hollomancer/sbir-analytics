#!/usr/bin/env python3
"""Gate on transition analytics checks."""

import json
import os
import sys
from pathlib import Path


def _env_float(key, default):
    """Get float from environment variable with default."""
    try:
        return float(os.environ.get(key, str(default)))
    except Exception:
        return default


def main():
    """Check analytics gates and exit with appropriate code."""
    ac_path = Path("data/processed/transition_analytics.checks.json")

    if not ac_path.exists():
        print(
            f"::error file={ac_path}::Analytics checks JSON not found. Ensure transition_analytics ran."
        )
        sys.exit(2)

    data = json.loads(ac_path.read_text(encoding="utf-8"))

    award = data.get("award_transition_rate") or {}
    company = data.get("company_transition_rate") or {}
    a_den = int(award.get("denominator") or 0)
    c_den = int(company.get("denominator") or 0)
    a_rate = float(award.get("rate") or 0.0)
    c_rate = float(company.get("rate") or 0.0)

    # Basic sanity checks
    denom_ok = (a_den > 0) and (c_den > 0)
    rate_bounds_ok = (0.0 <= a_rate <= 1.0) and (0.0 <= c_rate <= 1.0)

    # Optional minimum thresholds from env
    min_award_rate = _env_float("SBIR_ETL__TRANSITION__ANALYTICS__MIN_AWARD_RATE", 0.0)
    min_company_rate = _env_float("SBIR_ETL__TRANSITION__ANALYTICS__MIN_COMPANY_RATE", 0.0)
    min_ok = (a_rate >= min_award_rate) and (c_rate >= min_company_rate)

    print(
        "Analytics checks:",
        json.dumps(
            {
                "award": {"denominator": a_den, "rate": a_rate, "min_rate": min_award_rate},
                "company": {"denominator": c_den, "rate": c_rate, "min_rate": min_company_rate},
                "sanity": {"denominators_positive": denom_ok, "rates_within_0_1": rate_bounds_ok},
            },
            indent=2,
        ),
    )

    if not denom_ok:
        print("::error::Analytics gate failed: zero denominators (award or company).")
        sys.exit(1)
    if not rate_bounds_ok:
        print("::error::Analytics gate failed: rates outside [0,1].")
        sys.exit(1)
    if not min_ok:
        print(
            f"::error::Analytics gate failed: rates below minimums "
            f"(award: {a_rate:.2%} < {min_award_rate:.2%} "
            f"or company: {c_rate:.2%} < {min_company_rate:.2%})."
        )
        sys.exit(1)

    print("Analytics checks gate passed.")


if __name__ == "__main__":
    main()
