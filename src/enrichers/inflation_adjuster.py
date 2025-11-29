"""
Inflation adjustment service for fiscal returns analysis.

This module implements BEA GDP deflator integration for monetary normalization,
supporting configurable base year adjustment with linear interpolation and
quality flags for extrapolation and missing periods.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pandas as pd
from loguru import logger

from ..config.loader import get_config


@dataclass
class InflationAdjustmentResult:
    """Result of inflation adjustment with quality flags and metadata."""

    original_amount: Decimal
    adjusted_amount: Decimal
    base_year: int
    award_year: int
    inflation_factor: float
    confidence: float
    source: str
    method: str
    quality_flags: list[str]
    timestamp: datetime
    metadata: dict[str, Any]


class InflationAdjuster:
    """Inflation adjustment service using BEA GDP deflator data."""

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize the inflation adjuster.

        Args:
            config: Optional configuration override (dict or FiscalAnalysisConfig)
        """
        from src.config.schemas.fiscal import FiscalAnalysisConfig

        config_obj = config or get_config().fiscal_analysis
        # Handle both dict and FiscalAnalysisConfig objects
        if isinstance(config_obj, dict):
            # Convert dict to FiscalAnalysisConfig
            self.config = FiscalAnalysisConfig(**config_obj)
        else:
            # Already a FiscalAnalysisConfig
            self.config = config_obj
        self.base_year = self.config.base_year
        self.inflation_source = self.config.inflation_source
        self.quality_thresholds = self.config.quality_thresholds

        # BEA GDP deflator data (2009=100 base)
        # This is sample data - in production, this would be loaded from BEA API or data file
        self.bea_gdp_deflator = {
            1990: 72.2,
            1991: 75.0,
            1992: 76.8,
            1993: 78.6,
            1994: 80.1,
            1995: 81.5,
            1996: 82.7,
            1997: 84.1,
            1998: 84.9,
            1999: 85.8,
            2000: 87.0,
            2001: 88.4,
            2002: 89.6,
            2003: 91.2,
            2004: 93.4,
            2005: 96.0,
            2006: 98.6,
            2007: 101.0,
            2008: 102.3,
            2009: 100.0,
            2010: 101.2,
            2011: 103.3,
            2012: 105.2,
            2013: 106.7,
            2014: 108.3,
            2015: 108.6,
            2016: 109.7,
            2017: 111.7,
            2018: 114.1,
            2019: 116.0,
            2020: 117.6,
            2021: 122.2,
            2022: 130.7,
            2023: 135.4,
            2024: 138.2,
        }

        # Convert to base year index (default 2023=100)
        self._normalize_deflator_to_base_year()

        logger.info(
            f"Initialized InflationAdjuster with base year {self.base_year} and {len(self.bea_gdp_deflator)} deflator values"
        )

    def _normalize_deflator_to_base_year(self) -> None:
        """Normalize deflator values to use configured base year as 100."""
        if self.base_year in self.bea_gdp_deflator:
            base_value = self.bea_gdp_deflator[self.base_year]
            # Rescale all values so base_year = 100
            for year in self.bea_gdp_deflator:
                self.bea_gdp_deflator[year] = (self.bea_gdp_deflator[year] / base_value) * 100.0

            logger.info(f"Normalized deflator to base year {self.base_year} = 100.0")
        else:
            logger.warning(f"Base year {self.base_year} not found in deflator data")

    def get_deflator_value(self, year: int) -> float | None:
        """Get deflator value for a specific year.

        Args:
            year: Year to get deflator for

        Returns:
            Deflator value or None if not available
        """
        return self.bea_gdp_deflator.get(year)

    def interpolate_deflator(self, year: int) -> float | None:
        """Interpolate deflator value for missing years using linear interpolation.

        Args:
            year: Year to interpolate deflator for

        Returns:
            Interpolated deflator value or None if cannot interpolate
        """
        if year in self.bea_gdp_deflator:
            return self.bea_gdp_deflator[year]

        # Find surrounding years
        years = sorted(self.bea_gdp_deflator.keys())

        # Find the two closest years
        lower_year = None
        upper_year = None

        for y in years:
            if y < year:
                lower_year = y
            elif y > year and upper_year is None:
                upper_year = y
                break

        # Linear interpolation
        if lower_year is not None and upper_year is not None:
            lower_value = self.bea_gdp_deflator[lower_year]
            upper_value = self.bea_gdp_deflator[upper_year]

            # Linear interpolation formula
            weight = (year - lower_year) / (upper_year - lower_year)
            interpolated_value = lower_value + weight * (upper_value - lower_value)

            logger.debug(
                f"Interpolated deflator for {year}: {interpolated_value:.2f} (between {lower_year}:{lower_value:.2f} and {upper_year}:{upper_value:.2f})"
            )
            return interpolated_value

        return None

    def extrapolate_deflator(self, year: int) -> float | None:
        """Extrapolate deflator value for years outside available range.

        Args:
            year: Year to extrapolate deflator for

        Returns:
            Extrapolated deflator value or None if cannot extrapolate
        """
        years = sorted(self.bea_gdp_deflator.keys())

        if not years:
            return None

        min_year = min(years)
        max_year = max(years)

        # Extrapolate backwards (use average growth rate from first 5 years)
        if year < min_year:
            if len(years) >= 5:
                early_years = years[:5]
                early_values = [self.bea_gdp_deflator[y] for y in early_years]

                # Calculate average annual growth rate
                total_growth = early_values[-1] / early_values[0]
                years_span = early_years[-1] - early_years[0]
                avg_growth_rate = (total_growth ** (1 / years_span)) - 1

                # Extrapolate backwards
                years_back = min_year - year
                extrapolated_value = self.bea_gdp_deflator[min_year] / (
                    (1 + avg_growth_rate) ** years_back
                )

                logger.debug(
                    f"Extrapolated deflator backwards for {year}: {extrapolated_value:.2f} (growth rate: {avg_growth_rate:.3f})"
                )
                return extrapolated_value

        # Extrapolate forwards (use average growth rate from last 5 years)
        elif year > max_year:
            if len(years) >= 5:
                recent_years = years[-5:]
                recent_values = [self.bea_gdp_deflator[y] for y in recent_years]

                # Calculate average annual growth rate
                total_growth = recent_values[-1] / recent_values[0]
                years_span = recent_years[-1] - recent_years[0]
                avg_growth_rate = (total_growth ** (1 / years_span)) - 1

                # Extrapolate forwards
                years_forward = year - max_year
                extrapolated_value = self.bea_gdp_deflator[max_year] * (
                    (1 + avg_growth_rate) ** years_forward
                )

                logger.debug(
                    f"Extrapolated deflator forwards for {year}: {extrapolated_value:.2f} (growth rate: {avg_growth_rate:.3f})"
                )
                return extrapolated_value

        return None

    def get_inflation_factor(
        self, from_year: int, to_year: int | None = None
    ) -> tuple[float | None, list[str]]:
        """Calculate inflation factor to convert from one year to another.

        Args:
            from_year: Source year
            to_year: Target year (defaults to base_year)

        Returns:
            Tuple of (inflation factor, quality flags)
        """
        if to_year is None:
            to_year = self.base_year

        quality_flags = []

        # Get deflator values
        from_deflator = self.get_deflator_value(from_year)
        to_deflator = self.get_deflator_value(to_year)

        # Try interpolation if direct values not available
        if from_deflator is None:
            from_deflator = self.interpolate_deflator(from_year)
            if from_deflator is not None:
                quality_flags.append("from_year_interpolated")

        if to_deflator is None:
            to_deflator = self.interpolate_deflator(to_year)
            if to_deflator is not None:
                quality_flags.append("to_year_interpolated")

        # Try extrapolation if interpolation failed
        if from_deflator is None:
            from_deflator = self.extrapolate_deflator(from_year)
            if from_deflator is not None:
                quality_flags.append("from_year_extrapolated")

        if to_deflator is None:
            to_deflator = self.extrapolate_deflator(to_year)
            if to_deflator is not None:
                quality_flags.append("to_year_extrapolated")

        # Calculate inflation factor
        if from_deflator is not None and to_deflator is not None:
            inflation_factor = to_deflator / from_deflator
            return inflation_factor, quality_flags

        quality_flags.append("missing_deflator_data")
        return None, quality_flags

    def extract_award_year(self, award_row: pd.Series) -> int | None:
        """Extract award year from award data.

        Args:
            award_row: Award row data

        Returns:
            Award year or None if not found
        """
        # Check common date column names
        date_columns = [
            "Award_Date",
            "award_date",
            "Date",
            "date",
            "Award_Year",
            "award_year",
            "Year",
            "year",
        ]

        for col in date_columns:
            if col in award_row.index and pd.notna(award_row[col]):
                value = award_row[col]

                # Handle different date formats
                try:
                    # If it's already a year (integer or numeric)
                    if isinstance(value, (int, float)) and 1980 <= value <= 2030:
                        return int(value)

                    # If it's a date string or datetime
                    if isinstance(value, str):
                        # Try to parse as year first
                        if value.isdigit() and 1980 <= int(value) <= 2030:
                            return int(value)

                        # Try to parse as date
                        parsed_date = pd.to_datetime(value, errors="coerce")
                        if pd.notna(parsed_date):
                            return parsed_date.year

                    # If it's a pandas datetime
                    elif hasattr(value, "year"):
                        return value.year

                except (ValueError, TypeError):
                    continue

        return None

    def adjust_single_award(
        self, award_row: pd.Series, target_year: int | None = None
    ) -> InflationAdjustmentResult:
        """Adjust a single award amount for inflation.

        Args:
            award_row: Award row data
            target_year: Target year for adjustment (defaults to base_year)

        Returns:
            Inflation adjustment result
        """
        if target_year is None:
            target_year = self.base_year

        # Extract award amount
        amount_columns = [
            "Award_Amount",
            "award_amount",
            "Amount",
            "amount",
            "Award_Value",
            "award_value",
        ]
        original_amount = None
        amount_column = None

        for col in amount_columns:
            if col in award_row.index and pd.notna(award_row[col]):
                try:
                    # Handle string amounts with currency symbols and commas
                    amount_str = str(award_row[col]).replace("$", "").replace(",", "").strip()
                    original_amount = Decimal(amount_str)
                    amount_column = col
                    break
                except (ValueError, TypeError):
                    continue

        if original_amount is None:
            # Return result with error
            return InflationAdjustmentResult(
                original_amount=Decimal("0"),
                adjusted_amount=Decimal("0"),
                base_year=target_year,
                award_year=0,
                inflation_factor=1.0,
                confidence=0.0,
                source=self.inflation_source,
                method="error",
                quality_flags=["missing_amount"],
                timestamp=datetime.now(),
                metadata={"error": "No valid amount found"},
            )

        # Extract award year
        award_year = self.extract_award_year(award_row)

        if award_year is None:
            # Return result with error
            return InflationAdjustmentResult(
                original_amount=original_amount,
                adjusted_amount=original_amount,  # No adjustment possible
                base_year=target_year,
                award_year=0,
                inflation_factor=1.0,
                confidence=0.0,
                source=self.inflation_source,
                method="error",
                quality_flags=["missing_year"],
                timestamp=datetime.now(),
                metadata={"error": "No valid award year found", "amount_column": amount_column},
            )

        # Calculate inflation factor
        inflation_factor, quality_flags = self.get_inflation_factor(award_year, target_year)

        if inflation_factor is None:
            # Return result with error
            return InflationAdjustmentResult(
                original_amount=original_amount,
                adjusted_amount=original_amount,  # No adjustment possible
                base_year=target_year,
                award_year=award_year,
                inflation_factor=1.0,
                confidence=0.0,
                source=self.inflation_source,
                method="error",
                quality_flags=quality_flags,
                timestamp=datetime.now(),
                metadata={
                    "error": "Could not calculate inflation factor",
                    "amount_column": amount_column,
                },
            )

        # Apply inflation adjustment
        adjusted_amount = original_amount * Decimal(str(inflation_factor))
        adjusted_amount = adjusted_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Determine confidence based on quality flags
        confidence = 1.0
        if "interpolated" in str(quality_flags):
            confidence = 0.90
        elif "extrapolated" in str(quality_flags):
            confidence = 0.70

        # Determine method
        method = "direct_adjustment"
        if any("interpolated" in flag for flag in quality_flags):
            method = "interpolated_adjustment"
        elif any("extrapolated" in flag for flag in quality_flags):
            method = "extrapolated_adjustment"

        return InflationAdjustmentResult(
            original_amount=original_amount,
            adjusted_amount=adjusted_amount,
            base_year=target_year,
            award_year=award_year,
            inflation_factor=inflation_factor,
            confidence=confidence,
            source=self.inflation_source,
            method=method,
            quality_flags=quality_flags,
            timestamp=datetime.now(),
            metadata={
                "amount_column": amount_column,
                "from_deflator": self.get_deflator_value(award_year) or "calculated",
                "to_deflator": self.get_deflator_value(target_year) or "calculated",
            },
        )

    def adjust_awards_dataframe(
        self, awards_df: pd.DataFrame, target_year: int | None = None
    ) -> pd.DataFrame:
        """Adjust entire awards DataFrame for inflation.

        Args:
            awards_df: SBIR awards DataFrame
            target_year: Target year for adjustment (defaults to base_year)

        Returns:
            DataFrame with inflation adjustment columns
        """
        if target_year is None:
            target_year = self.base_year

        enriched_df = awards_df.copy()

        # Initialize inflation adjustment columns
        enriched_df["fiscal_original_amount"] = None
        enriched_df["fiscal_adjusted_amount"] = None
        enriched_df["fiscal_inflation_factor"] = None
        enriched_df["fiscal_award_year"] = None
        enriched_df["fiscal_base_year"] = target_year
        enriched_df["fiscal_inflation_confidence"] = None
        enriched_df["fiscal_inflation_source"] = self.inflation_source
        enriched_df["fiscal_inflation_method"] = None
        enriched_df["fiscal_inflation_quality_flags"] = None
        enriched_df["fiscal_inflation_timestamp"] = None
        enriched_df["fiscal_inflation_metadata"] = None

        logger.info(
            f"Starting inflation adjustment for {len(awards_df)} awards to {target_year} dollars"
        )

        # Track adjustment statistics
        method_counts: dict[Any, Any] = {}
        confidence_distribution = []
        successful_adjustments = 0
        total_original_amount = Decimal("0")
        total_adjusted_amount = Decimal("0")

        # Adjust each award
        for idx, row in awards_df.iterrows():
            try:
                result = self.adjust_single_award(row, target_year)

                # Store adjustment results
                enriched_df.at[idx, "fiscal_original_amount"] = float(result.original_amount)  # type: ignore[index]
                enriched_df.at[idx, "fiscal_adjusted_amount"] = float(result.adjusted_amount)  # type: ignore[index]
                enriched_df.at[idx, "fiscal_inflation_factor"] = result.inflation_factor  # type: ignore[index]
                enriched_df.at[idx, "fiscal_award_year"] = result.award_year  # type: ignore[index]
                enriched_df.at[idx, "fiscal_inflation_confidence"] = result.confidence  # type: ignore[index]
                enriched_df.at[idx, "fiscal_inflation_method"] = result.method  # type: ignore[index]
                enriched_df.at[idx, "fiscal_inflation_quality_flags"] = json.dumps(  # type: ignore[index]
                    result.quality_flags
                )
                enriched_df.at[idx, "fiscal_inflation_timestamp"] = result.timestamp  # type: ignore[index]
                enriched_df.at[idx, "fiscal_inflation_metadata"] = json.dumps(  # type: ignore[index]
                    result.metadata, default=str
                )

                # Track statistics
                method_counts[result.method] = method_counts.get(result.method, 0) + 1
                confidence_distribution.append(result.confidence)

                if result.method != "error":
                    successful_adjustments += 1
                    total_original_amount += result.original_amount
                    total_adjusted_amount += result.adjusted_amount

            except Exception as e:
                logger.error(f"Failed to adjust inflation for award {idx}: {e}")

        # Log adjustment statistics
        total_awards = len(awards_df)
        success_rate = successful_adjustments / total_awards if total_awards > 0 else 0
        avg_confidence = (
            sum(confidence_distribution) / len(confidence_distribution)
            if confidence_distribution
            else 0
        )
        avg_inflation_factor = (
            float(total_adjusted_amount / total_original_amount)
            if total_original_amount > 0
            else 1.0
        )

        logger.info("Inflation adjustment complete:")
        logger.info(f"  Success rate: {success_rate:.1%} ({successful_adjustments}/{total_awards})")
        logger.info(f"  Average confidence: {avg_confidence:.2f}")
        logger.info(f"  Average inflation factor: {avg_inflation_factor:.3f}")
        logger.info(f"  Method breakdown: {method_counts}")
        logger.info(f"  Total original amount: ${total_original_amount:,.2f}")
        logger.info(f"  Total adjusted amount: ${total_adjusted_amount:,.2f}")

        return enriched_df

    def validate_adjustment_quality(self, enriched_df: pd.DataFrame) -> dict[str, Any]:
        """Validate inflation adjustment quality against configured thresholds.

        Args:
            enriched_df: DataFrame with inflation adjustments

        Returns:
            Quality validation results
        """
        total_awards = len(enriched_df)
        successful_adjustments = (enriched_df["fiscal_inflation_method"] != "error").sum()
        success_rate = successful_adjustments / total_awards if total_awards > 0 else 0

        # Calculate confidence distribution
        confidences = enriched_df["fiscal_inflation_confidence"].dropna()
        high_confidence_count = (confidences >= 0.90).sum() if not confidences.empty else 0
        medium_confidence_count = (
            ((confidences >= 0.70) & (confidences < 0.90)).sum() if not confidences.empty else 0
        )
        low_confidence_count = (confidences < 0.70).sum() if not confidences.empty else 0

        # Method distribution
        method_counts = enriched_df["fiscal_inflation_method"].value_counts().to_dict()

        # Quality flags analysis
        quality_flags_series = enriched_df["fiscal_inflation_quality_flags"].dropna()
        all_flags = []
        for flags_json in quality_flags_series:
            try:
                flags = json.loads(flags_json) if isinstance(flags_json, str) else flags_json
                if isinstance(flags, list):
                    all_flags.extend(flags)
            except (json.JSONDecodeError, TypeError):
                continue

        flag_counts: dict[Any, Any] = {}
        for flag in all_flags:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

        # Calculate total amounts
        original_amounts = enriched_df["fiscal_original_amount"].dropna()
        adjusted_amounts = enriched_df["fiscal_adjusted_amount"].dropna()
        total_original = float(original_amounts.sum()) if not original_amounts.empty else 0
        total_adjusted = float(adjusted_amounts.sum()) if not adjusted_amounts.empty else 0

        # Quality assessment
        quality_results = {
            "total_awards": total_awards,
            "successful_adjustments": int(successful_adjustments),
            "success_rate": success_rate,
            "success_threshold": self.quality_thresholds.get("inflation_adjustment_success", 0.95),
            "success_meets_threshold": success_rate
            >= self.quality_thresholds.get("inflation_adjustment_success", 0.95),
            "confidence_distribution": {
                "high_confidence": int(high_confidence_count),
                "medium_confidence": int(medium_confidence_count),
                "low_confidence": int(low_confidence_count),
            },
            "method_distribution": method_counts,
            "quality_flag_distribution": flag_counts,
            "average_confidence": float(confidences.mean()) if not confidences.empty else 0.0,
            "total_original_amount": total_original,
            "total_adjusted_amount": total_adjusted,
            "overall_inflation_factor": (
                total_adjusted / total_original if total_original > 0 else 1.0
            ),
            "base_year": self.base_year,
            "inflation_source": self.inflation_source,
        }

        # Log quality assessment
        if quality_results["success_meets_threshold"]:
            logger.info(f"Inflation adjustment quality: PASS (success rate: {success_rate:.1%})")
        else:
            logger.warning(
                f"Inflation adjustment quality: FAIL (success rate: {success_rate:.1%}, threshold: {quality_results['success_threshold']:.1%})"
            )

        return quality_results


def adjust_awards_for_inflation(
    awards_df: pd.DataFrame, target_year: int | None = None, config: dict[str, Any] | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Main function to adjust SBIR awards for inflation.

    Args:
        awards_df: SBIR awards DataFrame
        target_year: Target year for adjustment (defaults to config base_year)
        config: Optional configuration override

    Returns:
        Tuple of (adjusted DataFrame, quality metrics)
    """
    adjuster = InflationAdjuster(config)

    if target_year is None:
        target_year = adjuster.base_year

    adjusted_df = adjuster.adjust_awards_dataframe(awards_df, target_year)
    quality_metrics = adjuster.validate_adjustment_quality(adjusted_df)

    return adjusted_df, quality_metrics
