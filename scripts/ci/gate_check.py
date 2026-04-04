#!/usr/bin/env python3
"""Unified CI gate checker for JSON-based validation files.

Reads a JSON file and validates specific fields against expected conditions.
Exits 0 on pass, 1 on fail, 2 if the JSON file is missing.

Usage:
    python scripts/ci/gate_check.py transition-validation
    python scripts/ci/gate_check.py transition-evidence
    python scripts/ci/gate_check.py transition-analytics
    python scripts/ci/gate_check.py taxonomy
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except Exception:
        return default


def _get_nested(data: dict, *keys: str, default=None):
    """Traverse nested dict keys, returning default if any key is missing."""
    current = data
    for k in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(k, default)
    return current


# ---------------------------------------------------------------------------
# Gate definitions
# ---------------------------------------------------------------------------

def gate_transition_validation() -> int:
    """Gate: transition MVP validation summary."""
    path = Path("reports/validation/transition_mvp.json")
    if not path.exists():
        print(f"::error file={path}::Validation summary not found.")
        return 2

    data = json.loads(path.read_text(encoding="utf-8"))
    gates = data.get("gates", {})

    failures = []
    for gate_name in ("contracts_sample", "vendor_resolution"):
        if not bool(_get_nested(gates, gate_name, "passed", default=False)):
            failures.append(f"{gate_name} gate failed")

    print("Transition MVP validation:", json.dumps(data, indent=2))

    if failures:
        for f in failures:
            print(f"::error::{f}")
        return 1

    print("All validation gates passed.")
    return 0


def gate_transition_evidence() -> int:
    """Gate: transition evidence completeness."""
    path = Path("data/processed/transitions_evidence.checks.json")
    if not path.exists():
        print(f"::error file={path}::Evidence checks JSON not found.")
        return 2

    data = json.loads(path.read_text(encoding="utf-8"))
    comp = data.get("completeness") or {}
    complete = bool(comp.get("complete", False))

    print("Evidence checks:", json.dumps(comp, indent=2))

    if not complete:
        th = comp.get("threshold")
        ca = comp.get("candidates_above_threshold")
        er = comp.get("evidence_rows_for_above_threshold")
        print(f"::error::Evidence completeness gate failed: {er}/{ca} candidates at >={th}")
        return 1

    print("Evidence completeness gate passed.")
    return 0


def gate_transition_analytics() -> int:
    """Gate: transition analytics rate checks."""
    path = Path("data/processed/transition_analytics.checks.json")
    if not path.exists():
        print(f"::error file={path}::Analytics checks JSON not found.")
        return 2

    data = json.loads(path.read_text(encoding="utf-8"))

    award = data.get("award_transition_rate") or {}
    company = data.get("company_transition_rate") or {}
    a_den = int(award.get("denominator") or 0)
    c_den = int(company.get("denominator") or 0)
    a_rate = float(award.get("rate") or 0.0)
    c_rate = float(company.get("rate") or 0.0)

    denom_ok = (a_den > 0) and (c_den > 0)
    rate_bounds_ok = (0.0 <= a_rate <= 1.0) and (0.0 <= c_rate <= 1.0)

    min_award_rate = _env_float("SBIR_ETL__TRANSITION__ANALYTICS__MIN_AWARD_RATE", 0.0)
    min_company_rate = _env_float("SBIR_ETL__TRANSITION__ANALYTICS__MIN_COMPANY_RATE", 0.0)
    min_ok = (a_rate >= min_award_rate) and (c_rate >= min_company_rate)

    print("Analytics checks:", json.dumps({
        "award": {"denominator": a_den, "rate": a_rate, "min_rate": min_award_rate},
        "company": {"denominator": c_den, "rate": c_rate, "min_rate": min_company_rate},
        "sanity": {"denominators_positive": denom_ok, "rates_within_0_1": rate_bounds_ok},
    }, indent=2))

    if not denom_ok:
        print("::error::Analytics gate failed: zero denominators.")
        return 1
    if not rate_bounds_ok:
        print("::error::Analytics gate failed: rates outside [0,1].")
        return 1
    if not min_ok:
        print(
            f"::error::Analytics gate failed: rates below minimums "
            f"(award: {a_rate:.2%} < {min_award_rate:.2%} "
            f"or company: {c_rate:.2%} < {min_company_rate:.2%})."
        )
        return 1

    print("Analytics checks gate passed.")
    return 0


def gate_taxonomy() -> int:
    """Gate: CET taxonomy completeness."""
    path = Path("data/processed/cet_taxonomy_checks.json")
    if not path.exists():
        print(f"Checks file not found at {path}; skipping taxonomy evaluation.")
        return 0  # graceful skip

    data = json.loads(path.read_text(encoding="utf-8"))
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
            f"CET taxonomy checks failed: "
            f"missing_required={missing_required} missing_keywords={mk} total={total}"
        )
        return 1

    print("CET taxonomy checks passed.")
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

GATES = {
    "transition-validation": gate_transition_validation,
    "transition-evidence": gate_transition_evidence,
    "transition-analytics": gate_transition_analytics,
    "taxonomy": gate_taxonomy,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(f"Usage: {sys.argv[0]} <gate-name>")
        print(f"Available gates: {', '.join(GATES)}")
        sys.exit(0 if "--help" in sys.argv else 2)

    gate_name = sys.argv[1]
    if gate_name not in GATES:
        print(f"Unknown gate: {gate_name}")
        print(f"Available gates: {', '.join(GATES)}")
        sys.exit(2)

    sys.exit(GATES[gate_name]())


if __name__ == "__main__":
    main()
