"""
Economic shock aggregator for fiscal returns analysis.

This module aggregates SBIR awards into state-by-sector-by-fiscal-year economic shocks
for StateIO model input, maintaining award-to-shock traceability for audit purposes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pandas as pd
from loguru import logger

from ...config.loader import get_config
from ...models.fiscal_models import EconomicShock


@dataclass
class ShockAggregationStats:
    """Statistics for shock aggregation quality and coverage."""

    total_shocks: int
    total_awards_aggregated: int
    unique_states: int
    unique_sectors: int
    unique_fiscal_years: int
    total_shock_amount: Decimal
    avg_confidence: float
    naics_coverage_rate: float
    geographic_resolution_rate: float
    awards_per_shock_avg: float


def calculate_fiscal_year(award_date: date | datetime | str | None) -> int | None:
    """Calculate government fiscal year from award date.

    Government fiscal years run from October 1 to September 30.
    For example, FY 2024 runs from Oct 1, 2023 to Sep 30, 2024.

    Args:
        award_date: Award date (date, datetime, or parseable string)

    Returns:
        Fiscal year (int) or None if date cannot be determined
    """
    if award_date is None:
        return None

    try:
        # Convert to date if needed
        if isinstance(award_date, str):
            award_date = pd.to_datetime(award_date).date()
        elif isinstance(award_date, datetime):
            award_date = award_date.date()
        elif isinstance(award_date, pd.Timestamp):
            award_date = award_date.date()

        if not isinstance(award_date, date):
            return None  # type: ignore[unreachable]

        # Fiscal year calculation: if month is Oct-Dec, fiscal year is next calendar year
        year = award_date.year
        month = award_date.month

        if month >= 10:  # Oct, Nov, Dec
            fiscal_year = year + 1
        else:  # Jan-Sep
            fiscal_year = year

        return fiscal_year

    except (ValueError, TypeError, AttributeError) as e:
        logger.warning(f"Failed to calculate fiscal year from {award_date}: {e}")
        return None


class FiscalShockAggregator:
    """Aggregate SBIR awards into state-by-sector-by-fiscal-year economic shocks.

    This aggregator processes BEA-mapped awards and creates EconomicShock objects
    for input to StateIO economic models. It maintains full traceability from
    individual awards to aggregated shocks for audit purposes.
    """

    def __init__(self, config: Any | None = None):
        """Initialize the fiscal shock aggregator.

        Args:
            config: Optional configuration override
        """
        self.config = config or get_config().fiscal_analysis
        self.base_year = getattr(self.config, "base_year", 2023)

    def extract_fiscal_year(self, award_row: pd.Series) -> int | None:
        """Extract fiscal year from award row.

        Tries multiple sources in order:
        1. Explicit fiscal_year field
        2. Calculated from award_date
        3. Calculated from proposal_award_date
        4. Award_year field (calendar year, converted to fiscal year)

        Args:
            award_row: Award row data

        Returns:
            Fiscal year or None if cannot be determined
        """
        # Try explicit fiscal_year field first
        if "fiscal_year" in award_row.index and pd.notna(award_row["fiscal_year"]):
            try:
                fy = int(award_row["fiscal_year"])
                if 1980 <= fy <= 2030:
                    return fy
            except (ValueError, TypeError):
                pass

        # Try award_date
        award_date_cols = ["award_date", "Award_Date", "proposal_award_date", "Proposal Award Date"]
        for col in award_date_cols:
            if col in award_row.index and pd.notna(award_row[col]):
                fy = calculate_fiscal_year(award_row[col])
                if fy:
                    return fy

        # Try award_year (calendar year -> fiscal year)
        if "award_year" in award_row.index and pd.notna(award_row["award_year"]):
            try:
                year = int(award_row["award_year"])
                # Calendar year maps to fiscal year starting in Oct of previous year
                # So calendar year 2023 maps to FY 2024 (Oct 2022 - Sep 2023)
                # But typically we want FY for the year it starts, so calendar year -> FY starting that October
                # Actually, for government accounting: FY 2024 = Oct 2023 - Sep 2024
                # If award is in calendar year 2023, it's likely in FY 2024
                # But to be safe, if it's early in the year (Jan-Sep), use that FY
                # If it's late (Oct-Dec), use next FY
                # Since we don't have month, assume midpoint -> use next FY
                return year + 1
            except (ValueError, TypeError):
                pass

        return None

    def extract_state_code(self, award_row: pd.Series) -> str | None:
        """Extract state code from award row.

        Tries multiple sources in order:
        1. resolved_state (from geographic resolution)
        2. company_state (from award data)
        3. State (from award data)

        Args:
            award_row: Award row data

        Returns:
            Two-letter state code or None
        """
        # Try geographic resolution field first
        state_cols = [
            "resolved_state",
            "company_state",
            "State",
            "state",
            "Company_State",
            "company_state",
        ]

        for col in state_cols:
            if col in award_row.index and pd.notna(award_row[col]):
                state_code = str(award_row[col]).strip().upper()
                # Validate it's a 2-letter code
                if len(state_code) == 2 and state_code.isalpha():
                    return state_code
                # Try to extract from full state name
                elif len(state_code) > 2:
                    # Could be full state name, but for now require 2-letter code
                    pass

        return None

    def extract_shock_amount(self, award_row: pd.Series) -> Decimal | None:
        """Extract inflation-adjusted award amount.

        Prefers inflation-adjusted amount, falls back to original amount.

        Args:
            award_row: Award row data

        Returns:
            Decimal amount or None
        """
        # Try inflation-adjusted amount first
        amount_cols = [
            "inflation_adjusted_amount",
            "adjusted_amount",
            "award_amount",
            "Award Amount",
            "amount",
        ]

        for col in amount_cols:
            if col in award_row.index and pd.notna(award_row[col]):
                try:
                    amount = Decimal(str(award_row[col]))
                    if amount >= 0:
                        return amount
                except (ValueError, TypeError):
                    continue

        return None

    def aggregate_shocks(
        self,
        awards_df: pd.DataFrame,
        chunk_size: int | None = None,
    ) -> list[EconomicShock]:
        """Aggregate awards into economic shocks.

        Groups awards by (state, bea_sector, fiscal_year) and creates EconomicShock objects.
        Supports weighted allocations when awards map to multiple BEA sectors.

        Args:
            awards_df: DataFrame with BEA-mapped awards (from bea_mapped_sbir_awards)
            chunk_size: Optional chunk size for processing (if None, processes all at once)

        Returns:
            List of EconomicShock objects
        """
        if awards_df.empty:
            logger.warning("Empty awards DataFrame provided to shock aggregator")
            return []

        logger.info(f"Starting shock aggregation for {len(awards_df)} award records")

        # Process in chunks if specified
        if chunk_size and len(awards_df) > chunk_size:
            all_shocks = []
            for i in range(0, len(awards_df), chunk_size):
                chunk = awards_df.iloc[i : i + chunk_size]
                chunk_shocks = self._aggregate_chunk(chunk)
                all_shocks.extend(chunk_shocks)
                logger.info(f"Processed chunk {i // chunk_size + 1}: {len(chunk_shocks)} shocks")
            return all_shocks
        else:
            return self._aggregate_chunk(awards_df)

    def _aggregate_chunk(self, awards_df: pd.DataFrame) -> list[EconomicShock]:
        """Aggregate a chunk of awards into shocks.

        Args:
            awards_df: DataFrame chunk with BEA-mapped awards

        Returns:
            List of EconomicShock objects
        """
        shocks_dict: dict[tuple[str, str, int], dict[str, Any]] = {}

        # Track statistics
        total_awards = len(awards_df)
        naics_coverage = 0
        geographic_coverage = 0
        total_confidence_sum = 0.0
        confidence_count = 0

        for _, row in awards_df.iterrows():
            # Extract key dimensions
            state = self.extract_state_code(row)
            fiscal_year = self.extract_fiscal_year(row)
            bea_sector = row.get("bea_sector_code")
            award_id = str(row.get("award_id", "UNKNOWN"))

            # Skip if missing critical dimensions
            if not state or not fiscal_year or pd.isna(bea_sector):
                continue

            bea_sector = str(bea_sector)

            # Extract amount with allocation weight
            base_amount = self.extract_shock_amount(row)
            if base_amount is None:
                continue

            # Apply allocation weight if present (for weighted BEA sector mappings)
            allocation_weight = float(row.get("bea_allocation_weight", 1.0))
            shock_amount = base_amount * Decimal(str(allocation_weight))

            # Create/update shock entry
            key = (state, bea_sector, fiscal_year)

            if key not in shocks_dict:
                shocks_dict[key] = {
                    "state": state,
                    "bea_sector": bea_sector,
                    "fiscal_year": fiscal_year,
                    "shock_amount": Decimal("0"),
                    "award_ids": [],
                    "confidences": [],
                    "naics_flags": [],
                }

            shocks_dict[key]["shock_amount"] += shock_amount
            shocks_dict[key]["award_ids"].append(award_id)

            # Track confidence and quality metrics
            mapping_confidence = float(row.get("bea_mapping_confidence", 0.70))
            shocks_dict[key]["confidences"].append(mapping_confidence)
            total_confidence_sum += mapping_confidence
            confidence_count += 1

            # Track NAICS and geographic coverage
            if pd.notna(row.get("fiscal_naics_code")):
                naics_coverage += 1
            if state:
                geographic_coverage += 1

        # Convert to EconomicShock objects
        shocks = []
        for key, data in shocks_dict.items():
            state, bea_sector, fiscal_year = key

            # Calculate aggregate confidence (weighted average)
            confidences = data["confidences"]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.70

            # Calculate coverage rates for this shock
            len(data["award_ids"])
            # For individual shock, use aggregate statistics as proxy
            # (full coverage would require tracking per-shock)
            naics_coverage_rate = naics_coverage / total_awards if total_awards > 0 else 0.0
            geo_resolution_rate = geographic_coverage / total_awards if total_awards > 0 else 0.0

            shock = EconomicShock(
                state=state,
                bea_sector=bea_sector,
                fiscal_year=fiscal_year,
                shock_amount=data["shock_amount"],
                award_ids=data["award_ids"],
                confidence=avg_confidence,
                naics_coverage_rate=naics_coverage_rate,
                geographic_resolution_rate=geo_resolution_rate,
                base_year=self.base_year,
            )

            shocks.append(shock)

        logger.info(
            f"Aggregated {len(shocks)} shocks from {total_awards} awards",
            extra={
                "unique_states": len({s.state for s in shocks}),
                "unique_sectors": len({s.bea_sector for s in shocks}),
                "unique_fiscal_years": len({s.fiscal_year for s in shocks}),
            },
        )

        return shocks

    def aggregate_shocks_to_dataframe(
        self, awards_df: pd.DataFrame, chunk_size: int | None = None
    ) -> pd.DataFrame:
        """Aggregate shocks and return as DataFrame.

        Convenience method that converts EconomicShock objects to DataFrame format.

        Args:
            awards_df: DataFrame with BEA-mapped awards
            chunk_size: Optional chunk size for processing

        Returns:
            DataFrame with shock aggregation results
        """
        shocks = self.aggregate_shocks(awards_df, chunk_size=chunk_size)

        if not shocks:
            # Return empty DataFrame with expected columns
            return pd.DataFrame(
                columns=[
                    "state",
                    "bea_sector",
                    "fiscal_year",
                    "shock_amount",
                    "num_awards",
                    "award_ids",
                    "confidence",
                    "naics_coverage_rate",
                    "geographic_resolution_rate",
                    "base_year",
                ]
            )

        # Convert to dict list
        shock_dicts = []
        for shock in shocks:
            shock_dicts.append(
                {
                    "state": shock.state,
                    "bea_sector": shock.bea_sector,
                    "fiscal_year": shock.fiscal_year,
                    "shock_amount": float(shock.shock_amount),
                    "num_awards": len(shock.award_ids),
                    "award_ids": shock.award_ids,
                    "confidence": shock.confidence,
                    "naics_coverage_rate": shock.naics_coverage_rate,
                    "geographic_resolution_rate": shock.geographic_resolution_rate,
                    "base_year": shock.base_year,
                    "created_at": shock.created_at.isoformat(),
                }
            )

        return pd.DataFrame(shock_dicts)

    def get_aggregation_statistics(self, shocks: list[EconomicShock]) -> ShockAggregationStats:
        """Calculate aggregation statistics.

        Args:
            shocks: List of EconomicShock objects

        Returns:
            ShockAggregationStats with quality metrics
        """
        if not shocks:
            return ShockAggregationStats(
                total_shocks=0,
                total_awards_aggregated=0,
                unique_states=0,
                unique_sectors=0,
                unique_fiscal_years=0,
                total_shock_amount=Decimal("0"),
                avg_confidence=0.0,
                naics_coverage_rate=0.0,
                geographic_resolution_rate=0.0,
                awards_per_shock_avg=0.0,
            )

        total_awards = sum(len(shock.award_ids) for shock in shocks)
        total_amount = sum(shock.shock_amount for shock in shocks)
        avg_confidence = sum(shock.confidence for shock in shocks) / len(shocks) if shocks else 0.0

        # Coverage rates (weighted by shock amount)
        total_shock_amount = sum(float(s.shock_amount) for s in shocks)
        if total_shock_amount > 0:
            weighted_naics_coverage = (
                sum(float(s.shock_amount) * s.naics_coverage_rate for s in shocks)
                / total_shock_amount
            )
            weighted_geo_coverage = (
                sum(float(s.shock_amount) * s.geographic_resolution_rate for s in shocks)
                / total_shock_amount
            )
        else:
            weighted_naics_coverage = 0.0
            weighted_geo_coverage = 0.0

        return ShockAggregationStats(
            total_shocks=len(shocks),
            total_awards_aggregated=total_awards,
            unique_states=len({s.state for s in shocks}),
            unique_sectors=len({s.bea_sector for s in shocks}),
            unique_fiscal_years=len({s.fiscal_year for s in shocks}),
            total_shock_amount=total_amount,
            avg_confidence=avg_confidence,
            naics_coverage_rate=weighted_naics_coverage,
            geographic_resolution_rate=weighted_geo_coverage,
            awards_per_shock_avg=total_awards / len(shocks) if shocks else 0.0,
        )
