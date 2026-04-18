"""Economic model types and validation for fiscal returns analysis.

Provides the EconomicImpactResult dataclass and input validation
used by the BEAIOAdapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd

from ..exceptions import ValidationError


@dataclass
class EconomicImpactResult:
    """Result from economic model simulation."""

    state: str
    bea_sector: str
    fiscal_year: int

    wage_impact: Decimal
    proprietor_income_impact: Decimal
    gross_operating_surplus: Decimal
    consumption_impact: Decimal
    tax_impact: Decimal
    production_impact: Decimal

    model_version: str
    model_methodology: str
    multiplier_version: str | None
    confidence: float

    quality_flags: list[str]
    metadata: dict[str, Any]


def validate_shocks_input(shocks_df: pd.DataFrame) -> None:
    """Validate input shocks DataFrame format.

    Args:
        shocks_df: Input shocks DataFrame

    Raises:
        ValidationError: If input format is invalid
    """
    required_columns = ["state", "bea_sector", "fiscal_year", "shock_amount"]
    missing = [col for col in required_columns if col not in shocks_df.columns]
    if missing:
        raise ValidationError(
            f"Missing required columns: {missing}",
            component="transformer.economic_model",
            operation="validate_shocks_input",
            details={
                "missing_columns": missing,
                "required_columns": required_columns,
                "provided_columns": list(shocks_df.columns),
            },
        )

    if not shocks_df["state"].astype(str).str.len().eq(2).all():
        invalid_states = shocks_df[~shocks_df["state"].astype(str).str.len().eq(2)][
            "state"
        ].unique()
        raise ValidationError(
            "State codes must be exactly 2 letters",
            component="transformer.economic_model",
            operation="validate_shocks_input",
            details={"invalid_states": list(invalid_states[:10])},
        )

    if (shocks_df["shock_amount"] < 0).any():
        negative_count = (shocks_df["shock_amount"] < 0).sum()
        raise ValidationError(
            "Shock amounts must be non-negative",
            component="transformer.economic_model",
            operation="validate_shocks_input",
            details={
                "negative_count": int(negative_count),
                "total_rows": len(shocks_df),
            },
        )


# Backward compat: allow old import of the ABC name
EconomicModelInterface = None  # type: ignore[assignment]
