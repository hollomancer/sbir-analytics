"""Validation utilities for congressional district analysis.

This module provides helpers to validate data quality for district-level
fiscal impact analysis.
"""

from typing import Any

import pandas as pd
from loguru import logger


def validate_district_resolution(
    awards_df: pd.DataFrame,
    min_resolution_rate: float = 0.90,
    min_confidence: float = 0.80,
) -> dict[str, Any]:
    """Validate congressional district resolution quality.

    Args:
        awards_df: DataFrame with district resolution results
        min_resolution_rate: Minimum acceptable resolution rate (0-1)
        min_confidence: Minimum acceptable confidence score (0-1)

    Returns:
        Dictionary with validation results:
        {
            "passed": bool,
            "resolution_rate": float,
            "avg_confidence": float,
            "warnings": list[str],
            "errors": list[str],
            "stats": dict
        }
    """
    warnings = []
    errors = []

    # Check resolution rate
    total = len(awards_df)
    resolved = awards_df["congressional_district"].notna().sum()
    resolution_rate = resolved / total if total > 0 else 0

    if resolution_rate < min_resolution_rate:
        errors.append(
            f"Resolution rate {resolution_rate:.1%} is below minimum {min_resolution_rate:.1%}"
        )
    elif resolution_rate < (min_resolution_rate + 0.05):
        warnings.append(f"Resolution rate {resolution_rate:.1%} is close to minimum threshold")

    # Check confidence scores
    confidences = awards_df["congressional_district_confidence"].dropna()
    avg_confidence = confidences.mean() if not confidences.empty else 0
    low_confidence_count = (confidences < min_confidence).sum()

    if avg_confidence < min_confidence:
        errors.append(
            f"Average confidence {avg_confidence:.1%} is below minimum {min_confidence:.1%}"
        )

    if low_confidence_count > 0:
        low_confidence_pct = low_confidence_count / len(confidences) * 100
        if low_confidence_pct > 20:
            errors.append(
                f"{low_confidence_count} awards ({low_confidence_pct:.1f}%) have low confidence"
            )
        elif low_confidence_pct > 10:
            warnings.append(
                f"{low_confidence_count} awards ({low_confidence_pct:.1f}%) have low confidence"
            )

    # Method distribution
    method_counts = awards_df["congressional_district_method"].value_counts()

    # State distribution
    resolved_df = awards_df[awards_df["congressional_district"].notna()]
    states_with_resolution = resolved_df["company_state"].nunique()
    total_states = awards_df["company_state"].nunique()

    stats = {
        "total_awards": total,
        "resolved_awards": int(resolved),
        "unresolved_awards": int(total - resolved),
        "resolution_rate": resolution_rate,
        "avg_confidence": float(avg_confidence),
        "min_confidence_score": float(confidences.min()) if not confidences.empty else None,
        "max_confidence_score": float(confidences.max()) if not confidences.empty else None,
        "low_confidence_count": int(low_confidence_count),
        "resolution_methods": method_counts.to_dict(),
        "unique_districts": resolved_df["congressional_district"].nunique(),
        "states_with_resolution": states_with_resolution,
        "total_states": total_states,
    }

    result = {
        "passed": len(errors) == 0,
        "resolution_rate": resolution_rate,
        "avg_confidence": avg_confidence,
        "warnings": warnings,
        "errors": errors,
        "stats": stats,
    }

    # Log results
    if result["passed"]:
        logger.info("✓ District resolution validation PASSED")
    else:
        logger.warning("✗ District resolution validation FAILED")

    logger.info(f"  Resolution rate: {resolution_rate:.1%} ({resolved}/{total})")
    logger.info(f"  Average confidence: {avg_confidence:.1%}")
    logger.info(f"  Unique districts: {stats['unique_districts']}")

    if warnings:
        for warning in warnings:
            logger.warning(f"  ⚠ {warning}")

    if errors:
        for error in errors:
            logger.error(f"  ✗ {error}")

    return result


def validate_district_allocation(
    district_impacts_df: pd.DataFrame,
    min_allocation_confidence: float = 0.75,
) -> dict[str, Any]:
    """Validate district impact allocation quality.

    Args:
        district_impacts_df: DataFrame with allocated impacts
        min_allocation_confidence: Minimum acceptable allocation confidence

    Returns:
        Dictionary with validation results
    """
    warnings: list[str] = []
    errors: list[str] = []

    # Check for required columns
    required_cols = [
        "congressional_district",
        "state",
        "district_award_total",
        "allocation_share",
        "allocation_confidence",
    ]
    missing_cols = [col for col in required_cols if col not in district_impacts_df.columns]

    if missing_cols:
        errors.append(f"Missing required columns: {missing_cols}")
        return {
            "passed": False,
            "warnings": warnings,
            "errors": errors,
            "stats": {},
        }

    # Check allocation confidence
    confidences = district_impacts_df["allocation_confidence"].dropna()
    avg_confidence = confidences.mean() if not confidences.empty else 0
    low_confidence = (confidences < min_allocation_confidence).sum()

    if avg_confidence < min_allocation_confidence:
        errors.append(
            f"Average allocation confidence {avg_confidence:.1%} "
            f"is below minimum {min_allocation_confidence:.1%}"
        )

    if low_confidence > 0:
        low_pct = low_confidence / len(confidences) * 100
        if low_pct > 30:
            errors.append(f"{low_confidence} allocations ({low_pct:.1f}%) have low confidence")
        elif low_pct > 15:
            warnings.append(f"{low_confidence} allocations ({low_pct:.1f}%) have low confidence")

    # Check allocation shares sum to ~1.0 per state/sector
    allocation_sums = (
        district_impacts_df.groupby(["state", "bea_sector", "fiscal_year"])["allocation_share"]
        .sum()
        .reset_index()
    )
    allocation_sums.columns = ["state", "bea_sector", "fiscal_year", "total_share"]

    # Shares should sum to ~1.0 (within 5% tolerance)
    invalid_sums = allocation_sums[
        (allocation_sums["total_share"] < 0.95) | (allocation_sums["total_share"] > 1.05)
    ]

    if len(invalid_sums) > 0:
        warnings.append(
            f"{len(invalid_sums)} state/sector combinations have allocation shares not summing to 1.0"
        )

    # Statistics
    stats = {
        "total_allocations": len(district_impacts_df),
        "unique_districts": district_impacts_df["congressional_district"].nunique(),
        "unique_states": district_impacts_df["state"].nunique(),
        "avg_allocation_confidence": float(avg_confidence),
        "low_confidence_count": int(low_confidence),
        "min_allocation_share": float(district_impacts_df["allocation_share"].min()),
        "max_allocation_share": float(district_impacts_df["allocation_share"].max()),
        "avg_allocation_share": float(district_impacts_df["allocation_share"].mean()),
        "total_awards_allocated": float(district_impacts_df["district_award_total"].sum()),
    }

    # Check for very small allocations (might be noise)
    small_allocations = (district_impacts_df["allocation_share"] < 0.01).sum()
    if small_allocations > 0:
        small_pct = small_allocations / len(district_impacts_df) * 100
        if small_pct > 20:
            warnings.append(
                f"{small_allocations} allocations ({small_pct:.1f}%) have very small shares (<1%)"
            )

    result = {
        "passed": len(errors) == 0,
        "warnings": warnings,
        "errors": errors,
        "stats": stats,
    }

    # Log results
    if result["passed"]:
        logger.info("✓ District allocation validation PASSED")
    else:
        logger.warning("✗ District allocation validation FAILED")

    logger.info(f"  Total allocations: {stats['total_allocations']}")
    logger.info(f"  Unique districts: {stats['unique_districts']}")
    logger.info(f"  Average confidence: {avg_confidence:.1%}")

    if warnings:
        for warning in warnings:
            logger.warning(f"  ⚠ {warning}")

    if errors:
        for error in errors:
            logger.error(f"  ✗ {error}")

    return result


def generate_quality_report(
    awards_with_districts_df: pd.DataFrame,
    district_impacts_df: pd.DataFrame,
) -> str:
    """Generate a comprehensive quality report for district analysis.

    Args:
        awards_with_districts_df: Awards with resolved districts
        district_impacts_df: District-level impacts

    Returns:
        String containing formatted quality report
    """
    lines = []
    lines.append("=" * 80)
    lines.append("CONGRESSIONAL DISTRICT ANALYSIS QUALITY REPORT")
    lines.append("=" * 80)
    lines.append("")

    # Section 1: Resolution Quality
    resolution_validation = validate_district_resolution(awards_with_districts_df)
    lines.append("1. DISTRICT RESOLUTION QUALITY")
    lines.append("-" * 80)
    lines.append(f"Status: {'✓ PASS' if resolution_validation['passed'] else '✗ FAIL'}")
    lines.append(f"Resolution Rate: {resolution_validation['resolution_rate']:.1%}")
    lines.append(f"Average Confidence: {resolution_validation['avg_confidence']:.1%}")

    stats = resolution_validation["stats"]
    lines.append("\nResolution Statistics:")
    lines.append(f"  Total Awards: {stats['total_awards']:,}")
    lines.append(f"  Resolved: {stats['resolved_awards']:,}")
    lines.append(f"  Unresolved: {stats['unresolved_awards']:,}")
    lines.append(f"  Unique Districts: {stats['unique_districts']}")
    lines.append(
        f"  States with Resolution: {stats['states_with_resolution']}/{stats['total_states']}"
    )

    if stats["resolution_methods"]:
        lines.append("\nResolution Methods Used:")
        for method, count in stats["resolution_methods"].items():
            pct = count / stats["resolved_awards"] * 100 if stats["resolved_awards"] > 0 else 0
            lines.append(f"  {method}: {count:,} ({pct:.1f}%)")

    lines.append("")

    # Section 2: Allocation Quality
    allocation_validation = validate_district_allocation(district_impacts_df)
    lines.append("2. IMPACT ALLOCATION QUALITY")
    lines.append("-" * 80)
    lines.append(f"Status: {'✓ PASS' if allocation_validation['passed'] else '✗ FAIL'}")

    alloc_stats = allocation_validation["stats"]
    if alloc_stats:
        lines.append(f"Average Confidence: {alloc_stats['avg_allocation_confidence']:.1%}")
        lines.append("\nAllocation Statistics:")
        lines.append(f"  Total Allocations: {alloc_stats['total_allocations']:,}")
        lines.append(f"  Unique Districts: {alloc_stats['unique_districts']}")
        lines.append(f"  Total Awards Allocated: ${alloc_stats['total_awards_allocated']:,.2f}")
        lines.append(f"  Avg Allocation Share: {alloc_stats['avg_allocation_share']:.1%}")

    lines.append("")

    # Section 3: Warnings and Errors
    all_warnings = resolution_validation["warnings"] + allocation_validation["warnings"]
    all_errors = resolution_validation["errors"] + allocation_validation["errors"]

    if all_warnings:
        lines.append("3. WARNINGS")
        lines.append("-" * 80)
        for warning in all_warnings:
            lines.append(f"  ⚠ {warning}")
        lines.append("")

    if all_errors:
        lines.append("4. ERRORS")
        lines.append("-" * 80)
        for error in all_errors:
            lines.append(f"  ✗ {error}")
        lines.append("")

    # Section 4: Recommendations
    lines.append("5. RECOMMENDATIONS")
    lines.append("-" * 80)

    if resolution_validation["resolution_rate"] < 0.95:
        lines.append("  • Improve address data quality to increase resolution rate")

    if resolution_validation["avg_confidence"] < 0.85:
        lines.append("  • Consider using Census API for higher confidence scores")

    if alloc_stats and alloc_stats.get("low_confidence_count", 0) > 0:
        lines.append("  • Review low-confidence allocations before reporting")

    if not all_warnings and not all_errors:
        lines.append("  • Quality is good! Data is suitable for reporting.")

    lines.append("")
    lines.append("=" * 80)

    return "\n".join(lines)
