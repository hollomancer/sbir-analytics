"""
Abstract interface for economic input-output models.

This module defines the EconomicModelInterface for state-level input-output models
used in fiscal returns analysis.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd


@dataclass
class EconomicImpactResult:
    """Result from economic model simulation."""

    # Geographic and sectoral identifiers
    state: str
    bea_sector: str
    fiscal_year: int

    # Economic impact components
    wage_impact: Decimal
    proprietor_income_impact: Decimal
    gross_operating_surplus: Decimal
    consumption_impact: Decimal
    tax_impact: Decimal
    production_impact: Decimal

    # Model metadata
    model_version: str
    model_methodology: str
    multiplier_version: str | None
    confidence: float

    # Quality flags
    quality_flags: list[str]
    metadata: dict[str, Any]


class EconomicModelInterface(ABC):
    """Abstract interface for state-level input-output economic models.

    This interface defines the contract for economic models used to compute
    multiplier effects from SBIR spending shocks. Implementations may use
    R packages (via rpy2), Python libraries, or external APIs.
    """

    @abstractmethod
    def compute_impacts(
        self,
        shocks_df: pd.DataFrame,
        model_version: str | None = None,
    ) -> pd.DataFrame:
        """Compute economic impacts from spending shocks.

        Args:
            shocks_df: DataFrame with columns:
                - state: two-letter state code
                - bea_sector: BEA sector code
                - fiscal_year: fiscal year
                - shock_amount: spending amount (inflation-adjusted)
            model_version: Optional model version override

        Returns:
            DataFrame with economic impact components:
                - state, bea_sector, fiscal_year (from input)
                - wage_impact, proprietor_income_impact, gross_operating_surplus
                - consumption_impact, tax_impact, production_impact
                - model_version, confidence, quality_flags
        """
        pass

    @abstractmethod
    def get_model_version(self) -> str:
        """Get the version string for the current model configuration.

        Returns:
            Model version identifier (e.g., "StateIO_v2.1")
        """
        pass

    def validate_input(self, shocks_df: pd.DataFrame) -> None:
        """Validate input shocks DataFrame format.

        Args:
            shocks_df: Input shocks DataFrame

        Raises:
            ValueError: If input format is invalid
        """
        required_columns = ["state", "bea_sector", "fiscal_year", "shock_amount"]
        missing = [col for col in required_columns if col not in shocks_df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Validate state codes are 2 letters
        if not shocks_df["state"].astype(str).str.len().eq(2).all():
            raise ValueError("State codes must be exactly 2 letters")

        # Validate shock amounts are non-negative
        if (shocks_df["shock_amount"] < 0).any():
            raise ValueError("Shock amounts must be non-negative")

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the model is available and configured.

        Returns:
            True if model can be used, False otherwise
        """
        pass

