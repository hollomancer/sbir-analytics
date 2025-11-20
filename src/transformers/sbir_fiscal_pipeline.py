"""SBIR Fiscal Impact Pipeline.

Complete pipeline to calculate tax and job impacts from SBIR awards using
USEEIOR and StateIO economic models.

Pipeline flow:
    SBIR Awards (with NAICS) → Map to BEA Sectors → Aggregate → USEEIOR/StateIO
    → Tax & Wage Impacts → Employment Calculation → Final Results
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pandas as pd
from loguru import logger

from .naics_bea_mapper import NAICSBEAMapper
from .r_stateio_adapter import RStateIOAdapter

if TYPE_CHECKING:
    from ..config import Config


class SBIRFiscalImpactCalculator:
    """Calculate fiscal and employment impacts from SBIR awards.

    This class provides the complete pipeline from SBIR awards (with NAICS codes)
    to tax revenue and job creation impacts by state and industry.
    """

    def __init__(
        self,
        config: Config | None = None,
        r_adapter: RStateIOAdapter | None = None,
        naics_mapper: NAICSBEAMapper | None = None,
    ):
        """Initialize SBIR fiscal impact calculator.

        Args:
            config: Optional configuration object
            r_adapter: Optional pre-configured R adapter
            naics_mapper: Optional NAICS-BEA mapper
        """
        self.r_adapter = r_adapter or RStateIOAdapter(config=config)
        self.naics_mapper = naics_mapper or NAICSBEAMapper()

    def calculate_impacts_from_sbir_awards(
        self,
        awards_df: pd.DataFrame,
        include_employment: bool = True,
    ) -> pd.DataFrame:
        """Calculate complete fiscal impacts from SBIR awards.

        Args:
            awards_df: DataFrame with SBIR awards containing:
                - award_id: Unique award identifier
                - award_amount: Dollar amount of award
                - state: Two-letter state code
                - naics_code: NAICS industry code (2-6 digits)
                - fiscal_year: Award fiscal year
            include_employment: Whether to calculate employment impacts

        Returns:
            DataFrame with columns:
                - state: State code
                - bea_sector: BEA sector code
                - fiscal_year: Fiscal year
                - award_total: Total SBIR awards (sum of shocks)
                - production_impact: Total production multiplier effect
                - wage_impact: Wage and salary impacts
                - proprietor_income_impact: Proprietor income impacts
                - gross_operating_surplus: Business surplus impacts
                - tax_impact: Tax revenue impacts (state + federal)
                - consumption_impact: Consumption effects
                - jobs_created: Employment created (if include_employment=True)
                - model_version: Economic model version used
                - confidence: Confidence score (0-1)
                - quality_flags: Data quality indicators

        Raises:
            ValueError: If required columns missing or data invalid
        """
        logger.info(f"Processing {len(awards_df)} SBIR awards for fiscal impact calculation")

        # Validate input
        self._validate_awards_input(awards_df)

        # Step 1: Map NAICS codes to BEA sectors
        logger.debug("Mapping NAICS codes to BEA sectors...")
        awards_with_bea = self._map_naics_to_bea(awards_df)

        # Step 2: Aggregate awards by state/sector/year to create shocks
        logger.debug("Aggregating awards into demand shocks...")
        shocks = self._aggregate_awards_to_shocks(awards_with_bea)

        logger.info(
            f"Created {len(shocks)} demand shocks from {len(awards_df)} awards "
            f"across {shocks['state'].nunique()} states and "
            f"{shocks['bea_sector'].nunique()} sectors"
        )

        # Step 3: Compute economic impacts using USEEIOR/StateIO
        logger.info("Computing economic impacts using USEEIOR/StateIO...")
        impacts = self.r_adapter.compute_impacts(shocks)

        # Step 4: Add employment impacts if requested
        if include_employment:
            logger.debug("Calculating employment impacts...")
            impacts = self._add_employment_impacts(impacts)

        # Step 5: Add award totals for reference
        impacts = self._add_award_totals(impacts, shocks)

        logger.info(
            f"Completed fiscal impact calculation: {len(impacts)} impact rows generated"
        )

        return impacts

    def _validate_awards_input(self, awards_df: pd.DataFrame) -> None:
        """Validate SBIR awards input DataFrame.

        Args:
            awards_df: Awards DataFrame to validate

        Raises:
            ValueError: If validation fails
        """
        required_columns = ["award_amount", "state", "naics_code", "fiscal_year"]
        missing = [col for col in required_columns if col not in awards_df.columns]

        if missing:
            raise ValueError(
                f"Missing required columns in awards DataFrame: {missing}. "
                f"Required: {required_columns}"
            )

        if len(awards_df) == 0:
            raise ValueError("Awards DataFrame is empty")

        # Check for null values in required columns
        null_counts = awards_df[required_columns].isnull().sum()
        if null_counts.any():
            null_cols = null_counts[null_counts > 0].to_dict()
            raise ValueError(f"Null values found in required columns: {null_cols}")

    def _map_naics_to_bea(self, awards_df: pd.DataFrame) -> pd.DataFrame:
        """Map NAICS codes to BEA sectors.

        Args:
            awards_df: Awards DataFrame with naics_code column

        Returns:
            Awards DataFrame with added bea_sector column
        """
        awards_with_bea = awards_df.copy()

        # Map NAICS to BEA
        awards_with_bea["bea_sector"] = awards_with_bea["naics_code"].apply(
            lambda naics: self.naics_mapper.map_naics_to_bea_summary(str(naics))
        )

        # Log mapping statistics
        mapping_stats = (
            awards_with_bea.groupby(["naics_code", "bea_sector"]).size().reset_index(name="count")
        )
        logger.debug(
            f"NAICS to BEA mapping: {len(mapping_stats)} unique NAICS→BEA mappings, "
            f"{awards_with_bea['bea_sector'].nunique()} unique BEA sectors"
        )

        return awards_with_bea

    def _aggregate_awards_to_shocks(self, awards_df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate awards into demand shocks by state/sector/year.

        Args:
            awards_df: Awards DataFrame with bea_sector column

        Returns:
            Shocks DataFrame with columns: state, bea_sector, fiscal_year, shock_amount
        """
        # Group by state, sector, year and sum award amounts
        shocks = (
            awards_df.groupby(["state", "bea_sector", "fiscal_year"])["award_amount"]
            .sum()
            .reset_index()
        )

        # Rename to match expected format
        shocks.rename(columns={"award_amount": "shock_amount"}, inplace=True)

        # Convert to Decimal for precision
        shocks["shock_amount"] = shocks["shock_amount"].apply(
            lambda x: Decimal(str(x)) if pd.notnull(x) else Decimal("0")
        )

        return shocks

    def _add_employment_impacts(self, impacts: pd.DataFrame) -> pd.DataFrame:
        """Add employment (jobs created) to impacts.

        Uses a simplified multiplier approach. For production use, this should
        integrate with StateIO employment data.

        Args:
            impacts: Impacts DataFrame from R adapter

        Returns:
            Impacts DataFrame with added jobs_created column
        """
        impacts_with_jobs = impacts.copy()

        # Simplified employment calculation:
        # Rough estimate: 1 job per $100k of wage impact
        # This is conservative; actual multipliers vary by sector

        if "wage_impact" in impacts_with_jobs.columns:
            # Jobs ≈ wage_impact / average_wage
            # Using $100k as rough average (actual varies by sector/state)
            impacts_with_jobs["jobs_created"] = (
                impacts_with_jobs["wage_impact"].astype(float) / 100_000
            )
        else:
            logger.warning("wage_impact column not found, setting jobs_created to 0")
            impacts_with_jobs["jobs_created"] = 0.0

        # Round to 1 decimal place
        impacts_with_jobs["jobs_created"] = impacts_with_jobs["jobs_created"].round(1)

        return impacts_with_jobs

    def _add_award_totals(self, impacts: pd.DataFrame, shocks: pd.DataFrame) -> pd.DataFrame:
        """Add total award amounts to impact results for reference.

        Args:
            impacts: Impacts DataFrame
            shocks: Shocks DataFrame with shock_amount

        Returns:
            Impacts DataFrame with added award_total column
        """
        impacts_with_totals = impacts.copy()

        # Merge shock amounts as award totals
        merge_cols = ["state", "bea_sector", "fiscal_year"]
        impacts_with_totals = impacts_with_totals.merge(
            shocks[merge_cols + ["shock_amount"]].rename(columns={"shock_amount": "award_total"}),
            on=merge_cols,
            how="left",
        )

        return impacts_with_totals

    def calculate_summary_by_state(self, impacts: pd.DataFrame) -> pd.DataFrame:
        """Calculate summary statistics by state.

        Args:
            impacts: Full impacts DataFrame

        Returns:
            DataFrame with state-level summaries:
                - state
                - total_awards
                - total_tax_impact
                - total_jobs_created
                - total_wage_impact
                - total_production_impact
        """
        summary = (
            impacts.groupby("state")
            .agg(
                {
                    "award_total": "sum",
                    "tax_impact": "sum",
                    "jobs_created": "sum",
                    "wage_impact": "sum",
                    "production_impact": "sum",
                }
            )
            .reset_index()
        )

        summary.rename(
            columns={
                "award_total": "total_awards",
                "tax_impact": "total_tax_impact",
                "jobs_created": "total_jobs_created",
                "wage_impact": "total_wage_impact",
                "production_impact": "total_production_impact",
            },
            inplace=True,
        )

        return summary

    def calculate_summary_by_sector(self, impacts: pd.DataFrame) -> pd.DataFrame:
        """Calculate summary statistics by industry sector.

        Args:
            impacts: Full impacts DataFrame

        Returns:
            DataFrame with sector-level summaries
        """
        summary = (
            impacts.groupby("bea_sector")
            .agg(
                {
                    "award_total": "sum",
                    "tax_impact": "sum",
                    "jobs_created": "sum",
                    "wage_impact": "sum",
                    "production_impact": "sum",
                }
            )
            .reset_index()
        )

        summary.rename(
            columns={
                "award_total": "total_awards",
                "tax_impact": "total_tax_impact",
                "jobs_created": "total_jobs_created",
                "wage_impact": "total_wage_impact",
                "production_impact": "total_production_impact",
            },
            inplace=True,
        )

        # Add sector descriptions
        summary["sector_description"] = summary["bea_sector"].apply(
            self.naics_mapper.get_bea_code_description
        )

        return summary

    def calculate_district_impacts(
        self,
        awards_df: pd.DataFrame,
        congressional_district_resolver: Any = None,
    ) -> pd.DataFrame:
        """Calculate fiscal impacts allocated to congressional districts.

        This is a two-step process:
        1. Calculate state-level impacts using StateIO economic models
        2. Allocate those impacts to districts proportionally

        Args:
            awards_df: DataFrame with SBIR awards (must have address fields)
            congressional_district_resolver: Optional pre-configured resolver

        Returns:
            DataFrame with district-level allocated impacts
        """
        from ..enrichers.congressional_district_resolver import CongressionalDistrictResolver
        from .fiscal.district_allocator import allocate_state_impacts_to_districts

        logger.info("Calculating congressional district impacts...")

        # Step 1: Resolve congressional districts
        if congressional_district_resolver is None:
            congressional_district_resolver = CongressionalDistrictResolver(method="auto")

        awards_with_districts = congressional_district_resolver.enrich_awards_with_districts(
            awards_df
        )

        # Step 2: Calculate state-level impacts (using StateIO)
        state_impacts = self.calculate_impacts_from_sbir_awards(awards_df)

        # Step 3: Allocate state impacts to districts
        district_impacts = allocate_state_impacts_to_districts(
            state_impacts_df=state_impacts,
            awards_with_districts_df=awards_with_districts,
        )

        return district_impacts

    def calculate_summary_by_district(
        self, district_impacts: pd.DataFrame
    ) -> pd.DataFrame:
        """Calculate summary statistics by congressional district.

        Args:
            district_impacts: District-level impacts from calculate_district_impacts

        Returns:
            DataFrame with district-level summaries
        """
        from .fiscal.district_allocator import summarize_by_district

        return summarize_by_district(district_impacts)
