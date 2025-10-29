#!/usr/bin/env python3
"""
Validate contracts_sample against Task 25.1 acceptance criteria.

Exit codes:
  0 - All criteria passed
  1 - One or more criteria failed
"""

import json
import sys
from pathlib import Path

import pandas as pd


def validate_contracts_sample(sample_path: Path = None) -> bool:
    """
    Validate contracts_sample against MVP acceptance criteria.

    Criteria:
      1. Sample size between 1k–10k rows
      2. ≥ 90% rows have action_date
      3. ≥ 60% have at least one identifier (UEI|DUNS|PIID|FAIN)

    Returns:
        True if all criteria pass, False otherwise
    """
    if sample_path is None:
        sample_path = Path("data/processed/contracts_sample.parquet")

    if not sample_path.exists():
        print(f"❌ Sample file not found: {sample_path}")
        return False

    try:
        df = pd.read_parquet(sample_path)
    except Exception as e:
        print(f"❌ Failed to load sample: {e}")
        return False

    print("=" * 80)
    print("TASK 25.1: CONTRACTS SAMPLE VALIDATION")
    print("=" * 80)

    total_rows = len(df)
    print(f"\n📊 Total rows: {total_rows:,}")

    # Acceptance Criteria 1: Sample size between 1k–10k
    min_size, max_size = 1000, 10000
    size_ok = min_size <= total_rows <= max_size
    print(f"\n✓ Sample size (1k-10k): {size_ok}")
    print(f"  Required: {min_size:,} - {max_size:,}")
    print(f"  Actual: {total_rows:,}")

    # Extract action_date from metadata if needed
    if "action_date" not in df.columns and "metadata" in df.columns:
        df["action_date"] = df["metadata"].apply(
            lambda x: x.get("action_date") if isinstance(x, dict) else None
        )
        df["action_date"] = pd.to_datetime(df["action_date"], errors="coerce")

    # Acceptance Criteria 2: ≥ 90% rows have action_date
    action_date_col = "action_date" if "action_date" in df.columns else "start_date"
    if action_date_col not in df.columns:
        print(f"\n❌ Date column not found (looked for: action_date, start_date)")
        return False

    action_date_cov = df[action_date_col].notna().sum() / total_rows if total_rows > 0 else 0.0
    date_ok = action_date_cov >= 0.90
    print(f"\n✓ Action date coverage (≥90%): {date_ok}")
    print(f"  Required: ≥ 90%")
    print(f"  Actual: {action_date_cov * 100:.1f}%")

    # Acceptance Criteria 3: ≥ 60% have at least one identifier
    has_uei = (
        df["vendor_uei"].notna() if "vendor_uei" in df.columns else pd.Series([False] * total_rows)
    )
    has_duns = (
        df["vendor_duns"].notna()
        if "vendor_duns" in df.columns
        else pd.Series([False] * total_rows)
    )
    has_piid = (
        df["contract_id"].notna()
        if "contract_id" in df.columns
        else pd.Series([False] * total_rows)
    )
    has_fain = df["fain"].notna() if "fain" in df.columns else pd.Series([False] * total_rows)

    has_any_ident = has_uei | has_duns | has_piid | has_fain
    ident_cov = has_any_ident.sum() / total_rows if total_rows > 0 else 0.0
    ident_ok = ident_cov >= 0.60
    print(f"\n✓ Identifier coverage (≥60%): {ident_ok}")
    print(f"  Required: ≥ 60%")
    print(f"  Actual: {ident_cov * 100:.1f}%")
    print(f"  Breakdown:")
    print(f"    - UEI: {has_uei.sum():,} ({has_uei.sum() / total_rows * 100:.1f}%)")
    print(f"    - DUNS: {has_duns.sum():,} ({has_duns.sum() / total_rows * 100:.1f}%)")
    print(f"    - PIID: {has_piid.sum():,} ({has_piid.sum() / total_rows * 100:.1f}%)")
    print(f"    - FAIN: {has_fain.sum():,} ({has_fain.sum() / total_rows * 100:.1f}%)")

    # Summary
    print("\n" + "=" * 80)
    print("ACCEPTANCE CRITERIA SUMMARY")
    print("=" * 80)
    all_ok = size_ok and date_ok and ident_ok
    status_symbol = "✓" if all_ok else "❌"
    print(f"{status_symbol} All criteria met: {all_ok}")
    print(f"  - Sample size (1k-10k): {'✓' if size_ok else '❌'}")
    print(f"  - Action date ≥90%: {'✓' if date_ok else '❌'}")
    print(f"  - Identifier ≥60%: {'✓' if ident_ok else '❌'}")

    # Load checks file if available
    checks_path = sample_path.with_suffix(".checks.json")
    if checks_path.exists():
        with open(checks_path) as f:
            checks = json.load(f)
        print(f"\n📋 Checks file: {checks_path}")
        print(
            f"  Date range: {checks.get('date_range', {}).get('min')} to {checks.get('date_range', {}).get('max')}"
        )

    return all_ok


if __name__ == "__main__":
    success = validate_contracts_sample()
    sys.exit(0 if success else 1)
