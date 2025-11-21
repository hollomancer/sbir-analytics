"""Congressional District Impact Allocator.

This module allocates state-level economic impacts to congressional districts
based on proportional award distribution.

Since StateIO provides state-level economic models, we allocate those impacts
to districts proportionally based on SBIR award amounts in each district.
"""

from __future__ import annotations

import pandas as pd
from loguru import logger


def allocate_state_impacts_to_districts(
    state_impacts_df: pd.DataFrame,
    awards_with_districts_df: pd.DataFrame,
) -> pd.DataFrame:
    """Allocate state-level economic impacts to congressional districts.

    Takes state-level impacts (from StateIO) and allocates them proportionally
    to districts based on award distribution within each state.

    Args:
        state_impacts_df: DataFrame with state-level impacts, must include:
            - state: Two-letter state code
            - bea_sector: BEA sector code
            - fiscal_year: Fiscal year
            - production_impact, wage_impact, tax_impact, jobs_created, etc.
        awards_with_districts_df: DataFrame with awards enriched with districts:
            - state: State code
            - congressional_district: District code (e.g., "CA-12")
            - bea_sector: BEA sector (or naics_code that can be mapped)
            - fiscal_year: Fiscal year
            - award_amount: Award amount

    Returns:
        DataFrame with district-level allocated impacts:
            - congressional_district: District code
            - state: State code
            - bea_sector: BEA sector
            - fiscal_year: Fiscal year
            - district_award_total: Total awards in this district/sector/year
            - state_award_total: Total awards in parent state/sector/year
            - allocation_share: Proportion of state awards in this district (0-1)
            - production_impact_allocated: Allocated production impact
            - wage_impact_allocated: Allocated wage impact
            - tax_impact_allocated: Allocated tax impact
            - jobs_created_allocated: Allocated jobs
            - allocation_method: Method used ("proportional_by_awards")
            - confidence: Confidence score for allocation
    """
    logger.info("Allocating state-level impacts to congressional districts...")

    # Filter awards to only those with resolved districts
    awards_with_districts = awards_with_districts_df[
        awards_with_districts_df["congressional_district"].notna()
    ].copy()

    if len(awards_with_districts) == 0:
        logger.warning("No awards have resolved congressional districts. Cannot allocate.")
        return pd.DataFrame()

    logger.info(
        f"Using {len(awards_with_districts)}/{len(awards_with_districts_df)} "
        f"awards with resolved districts ({len(awards_with_districts) / len(awards_with_districts_df):.1%})"
    )

    # Map NAICS to BEA if not already present
    if "bea_sector" not in awards_with_districts.columns:
        if "naics_code" in awards_with_districts.columns:
            from ..naics_bea_mapper import NAICSBEAMapper

            mapper = NAICSBEAMapper()
            awards_with_districts["bea_sector"] = awards_with_districts["naics_code"].apply(
                lambda x: mapper.map_naics_to_bea_summary(str(x))
            )
            logger.debug("Mapped NAICS codes to BEA sectors for district allocation")
        else:
            logger.error("Awards must have either 'bea_sector' or 'naics_code' column")
            return pd.DataFrame()

    # Step 1: Calculate district-level award totals
    district_awards = (
        awards_with_districts.groupby(
            ["state", "congressional_district", "bea_sector", "fiscal_year"]
        )["award_amount"]
        .sum()
        .reset_index()
    )
    district_awards.rename(columns={"award_amount": "district_award_total"}, inplace=True)

    # Step 2: Calculate state-level award totals (for allocation denominator)
    state_awards = (
        awards_with_districts.groupby(["state", "bea_sector", "fiscal_year"])["award_amount"]
        .sum()
        .reset_index()
    )
    state_awards.rename(columns={"award_amount": "state_award_total_from_districts"}, inplace=True)

    # Step 3: Join to get allocation shares
    district_allocations = district_awards.merge(
        state_awards, on=["state", "bea_sector", "fiscal_year"], how="left"
    )

    # Calculate allocation share
    district_allocations["allocation_share"] = (
        district_allocations["district_award_total"]
        / district_allocations["state_award_total_from_districts"]
    )

    # Step 4: Join with state-level impacts
    district_impacts = district_allocations.merge(
        state_impacts_df,
        on=["state", "bea_sector", "fiscal_year"],
        how="left",
    )

    # Step 5: Allocate impact columns
    impact_columns = [
        "production_impact",
        "wage_impact",
        "proprietor_income_impact",
        "gross_operating_surplus",
        "tax_impact",
        "consumption_impact",
        "jobs_created",
    ]

    for col in impact_columns:
        if col in district_impacts.columns:
            allocated_col = f"{col}_allocated"
            district_impacts[allocated_col] = (
                district_impacts[col] * district_impacts["allocation_share"]
            )

    # Add metadata
    district_impacts["allocation_method"] = "proportional_by_awards"

    # Calculate confidence score based on:
    # - Congressional district resolution confidence
    # - Allocation share (lower is less confident - might be noise)
    # - Original model confidence

    # Get average district resolution confidence for this district/state/sector/year
    district_confidence = (
        awards_with_districts.groupby(
            ["state", "congressional_district", "bea_sector", "fiscal_year"]
        )["congressional_district_confidence"]
        .mean()
        .reset_index()
    )
    district_confidence.rename(
        columns={"congressional_district_confidence": "avg_district_resolution_confidence"},
        inplace=True,
    )

    district_impacts = district_impacts.merge(
        district_confidence,
        on=["state", "congressional_district", "bea_sector", "fiscal_year"],
        how="left",
    )

    # Combined confidence score
    # Factors: district resolution confidence * model confidence * allocation share factor
    district_impacts["allocation_confidence"] = (
        district_impacts.get("avg_district_resolution_confidence", 0.8)
        * district_impacts.get("confidence", 0.85)
        * (0.7 + 0.3 * district_impacts["allocation_share"])  # Penalize very small allocations
    )

    # Select final columns
    output_columns = [
        "congressional_district",
        "state",
        "bea_sector",
        "fiscal_year",
        "district_award_total",
        "state_award_total_from_districts",
        "allocation_share",
    ]

    # Add allocated impact columns
    for col in impact_columns:
        allocated_col = f"{col}_allocated"
        if allocated_col in district_impacts.columns:
            output_columns.append(allocated_col)

    # Add metadata columns
    metadata_cols = ["allocation_method", "allocation_confidence", "model_version"]
    for col in metadata_cols:
        if col in district_impacts.columns:
            output_columns.append(col)

    final_df = district_impacts[[c for c in output_columns if c in district_impacts.columns]].copy()

    logger.info(f"Allocated impacts to {len(final_df)} district/sector/year combinations")
    logger.info(
        f"Covering {final_df['congressional_district'].nunique()} unique congressional districts"
    )

    return final_df


def summarize_by_district(district_impacts_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize allocated impacts by congressional district.

    Args:
        district_impacts_df: District-level impacts from allocate_state_impacts_to_districts

    Returns:
        DataFrame with district-level summaries:
            - congressional_district: District code
            - state: State code
            - total_awards: Total SBIR awards in district
            - total_production_impact: Total production impact
            - total_tax_impact: Total tax revenue
            - total_jobs_created: Total jobs
            - sector_count: Number of BEA sectors active in district
            - avg_confidence: Average allocation confidence
    """
    summary = (
        district_impacts_df.groupby(["congressional_district", "state"])
        .agg(
            {
                "district_award_total": "sum",
                "production_impact_allocated": "sum",
                "tax_impact_allocated": "sum",
                "jobs_created_allocated": "sum",
                "wage_impact_allocated": "sum",
                "bea_sector": "nunique",
                "allocation_confidence": "mean",
            }
        )
        .reset_index()
    )

    summary.rename(
        columns={
            "district_award_total": "total_awards",
            "production_impact_allocated": "total_production_impact",
            "tax_impact_allocated": "total_tax_impact",
            "jobs_created_allocated": "total_jobs_created",
            "wage_impact_allocated": "total_wage_impact",
            "bea_sector": "sector_count",
            "allocation_confidence": "avg_confidence",
        },
        inplace=True,
    )

    # Sort by total awards descending
    summary = summary.sort_values("total_awards", ascending=False)

    return summary


def compare_districts_within_state(
    district_impacts_df: pd.DataFrame, state_code: str
) -> pd.DataFrame:
    """Compare congressional districts within a specific state.

    Args:
        district_impacts_df: District-level impacts
        state_code: Two-letter state code (e.g., "CA")

    Returns:
        DataFrame comparing districts within the state
    """
    state_districts = district_impacts_df[district_impacts_df["state"] == state_code].copy()

    if len(state_districts) == 0:
        logger.warning(f"No districts found for state {state_code}")
        return pd.DataFrame()

    summary = summarize_by_district(state_districts)

    # Add rankings within state
    summary["tax_impact_rank"] = summary["total_tax_impact"].rank(ascending=False, method="dense")
    summary["jobs_rank"] = summary["total_jobs_created"].rank(ascending=False, method="dense")
    summary["awards_rank"] = summary["total_awards"].rank(ascending=False, method="dense")

    logger.info(f"Found {len(summary)} districts in {state_code}")

    return summary
