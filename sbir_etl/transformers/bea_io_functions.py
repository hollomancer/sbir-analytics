"""BEA I-O table functions for economic impact computation.

Pure-Python replacement for the former R/StateIO wrappers.  Fetches national
Use tables and Value-Added data from the BEA API, then performs Leontief
input-output analysis in NumPy/Pandas.

The matrix math functions (technical coefficients, Leontief inverse, demand
shocks) are unchanged from the prior implementation — only the *data source*
has moved from R to the BEA REST API.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from .bea_api_client import BEAApiClient, STATE_FIPS


# ---------------------------------------------------------------------------
# BEA API data retrieval (replaces R StateIO calls)
# ---------------------------------------------------------------------------


def fetch_use_table(client: BEAApiClient, year: int = 2020) -> pd.DataFrame:
    """Fetch and pivot the BEA Use table into a commodities × industries matrix.

    Args:
        client: Configured BEA API client.
        year: Data year.

    Returns:
        DataFrame with commodity rows and industry columns, values in millions $.
    """
    raw = client.get_use_table(year)
    if raw.empty:
        logger.warning(f"BEA Use table empty for year {year}")
        return pd.DataFrame()

    # BEA Use table rows: RowCode (commodity), ColCode (industry), DataValue
    df = raw.copy()
    df["DataValue"] = pd.to_numeric(df["DataValue"], errors="coerce").fillna(0.0)

    # Pivot to matrix form: rows = commodities, columns = industries
    use_matrix = df.pivot_table(
        index="RowCode",
        columns="ColCode",
        values="DataValue",
        aggfunc="sum",
        fill_value=0.0,
    )

    logger.debug(f"Fetched Use table ({use_matrix.shape[0]}×{use_matrix.shape[1]}) for {year}")
    return use_matrix


def fetch_industry_output(use_table: pd.DataFrame) -> pd.Series:
    """Derive industry total output from the Use table.

    Total output per industry = sum of all commodity inputs (column total).

    Args:
        use_table: Pivoted Use matrix (commodities × industries).

    Returns:
        Series indexed by industry code with total output values.
    """
    if use_table.empty:
        return pd.Series(dtype=float)

    # The "T001" row in BEA Use tables is "Total Intermediate" — but
    # we also include value-added rows.  For the Leontief model we want
    # the column sum of intermediate inputs only (exclude VA rows).
    # If the table already contains only intermediate rows, column sum works.
    # We'll use column sums as a proxy; the adapter can override with
    # explicit output data from the VA table if available.
    output = use_table.sum(axis=0)
    output.name = "industry_output"
    return output


def fetch_value_added(
    client: BEAApiClient,
    year: int = 2020,
) -> pd.DataFrame:
    """Fetch BEA Value-Added by Industry data.

    Returns a DataFrame with columns for compensation, GOS, taxes, etc.
    by BEA industry code.

    Args:
        client: BEA API client.
        year: Data year.

    Returns:
        DataFrame with industry-level value-added components.
    """
    raw = client.get_value_added_table(year)
    if raw.empty:
        logger.warning(f"BEA Value Added table empty for year {year}")
        return pd.DataFrame()

    df = raw.copy()
    df["DataValue"] = pd.to_numeric(df["DataValue"], errors="coerce").fillna(0.0)

    logger.debug(f"Fetched Value Added data with {len(df)} rows for {year}")
    return df


def fetch_employment(
    client: BEAApiClient,
    year: int = 2020,
) -> pd.DataFrame:
    """Fetch BEA Employment by Industry data.

    Args:
        client: BEA API client.
        year: Data year.

    Returns:
        DataFrame with employment counts by industry.
    """
    raw = client.get_employment_table(year)
    if raw.empty:
        logger.warning(f"BEA Employment table empty for year {year}")
        return pd.DataFrame()

    df = raw.copy()
    df["DataValue"] = pd.to_numeric(df["DataValue"], errors="coerce").fillna(0.0)

    logger.debug(f"Fetched Employment data with {len(df)} rows for {year}")
    return df


# ---------------------------------------------------------------------------
# Value-added ratio computation (replaces R StateIO GVA functions)
# ---------------------------------------------------------------------------


def calculate_value_added_ratios(
    va_df: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate value-added ratios (wages, GOS, taxes) by sector.

    Parses the BEA Value Added table to compute each component's share of
    total value added per industry.

    Args:
        va_df: Raw VA DataFrame from fetch_value_added().

    Returns:
        DataFrame with columns: sector, wage_ratio, gos_ratio, tax_ratio,
        proprietor_income_ratio.  Empty DataFrame if input is empty.
    """
    if va_df.empty:
        return pd.DataFrame()

    try:
        # BEA VA table has RowCode for component type, ColCode for industry
        # Common RowCode values:
        #   "1" or "VA" = Total Value Added
        #   "6" = Compensation of employees
        #   "7" = Taxes on production and imports
        #   "9" or "13" = Gross operating surplus
        # Exact codes depend on table version; we match by description keywords.

        # Build lookup: industry → {component: value}
        industry_va: dict[str, dict[str, float]] = {}

        for _, row in va_df.iterrows():
            industry = str(row.get("ColCode", row.get("RowCode", "")))
            desc = str(row.get("RowDescription", row.get("LineDescription", ""))).lower()
            value = float(row.get("DataValue", 0))

            if not industry:
                continue

            if industry not in industry_va:
                industry_va[industry] = {
                    "wages": 0.0,
                    "gos": 0.0,
                    "taxes": 0.0,
                    "proprietor_income": 0.0,
                    "total_va": 0.0,
                }

            if "compensation" in desc:
                industry_va[industry]["wages"] = value
            elif "gross operating surplus" in desc or "surplus" in desc:
                industry_va[industry]["gos"] = value
            elif "tax" in desc:
                industry_va[industry]["taxes"] = value
            elif "proprietor" in desc:
                industry_va[industry]["proprietor_income"] = value
            elif "value added" in desc or "total" in desc:
                industry_va[industry]["total_va"] = value

        # Compute ratios
        ratios_data = []
        for sector, components in industry_va.items():
            total = components["total_va"]
            if total <= 0:
                # Fall back to sum of known components
                total = (
                    components["wages"]
                    + components["gos"]
                    + components["taxes"]
                    + components["proprietor_income"]
                )
            if total <= 0:
                continue

            ratios_data.append(
                {
                    "sector": sector,
                    "wage_ratio": components["wages"] / total,
                    "gos_ratio": components["gos"] / total,
                    "tax_ratio": components["taxes"] / total,
                    "proprietor_income_ratio": components["proprietor_income"] / total,
                }
            )

        if ratios_data:
            return pd.DataFrame(ratios_data)

        logger.debug("Could not calculate value-added ratios from BEA data")
        return pd.DataFrame()

    except Exception as e:
        logger.warning(f"Failed to calculate value-added ratios: {e}")
        return pd.DataFrame()


def calculate_employment_coefficients(
    emp_df: pd.DataFrame,
    industry_output: pd.Series,
) -> pd.DataFrame:
    """Calculate employment coefficients (jobs per $1M output) by sector.

    Args:
        emp_df: Employment DataFrame from fetch_employment().
        industry_output: Industry output Series.

    Returns:
        DataFrame with columns: sector, employment, employment_coefficient.
    """
    if emp_df.empty or industry_output.empty:
        return pd.DataFrame()

    try:
        coefficients = []
        for _, row in emp_df.iterrows():
            sector = str(row.get("ColCode", row.get("RowCode", "")))
            emp_val = float(row.get("DataValue", 0))

            if sector in industry_output.index:
                output_val = float(industry_output[sector])
                if output_val > 0:
                    coeff = (emp_val / output_val) * 1_000_000
                    coefficients.append(
                        {
                            "sector": sector,
                            "employment": emp_val,
                            "employment_coefficient": coeff,
                        }
                    )

        return pd.DataFrame(coefficients)
    except Exception as e:
        logger.warning(f"Failed to calculate employment coefficients: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Matrix math (unchanged from prior R-era implementation)
# ---------------------------------------------------------------------------


def calculate_technical_coefficients(
    use_table: pd.DataFrame,
    industry_output: pd.Series,
) -> pd.DataFrame:
    """Calculate technical coefficients matrix A from Use table.

    A[i,j] = Use[i,j] / Output[j]

    Args:
        use_table: Use table (commodities × industries).
        industry_output: Industry output vector.

    Returns:
        Technical coefficients matrix A.

    Raises:
        ValueError: If dimensions don't match.
    """
    if use_table.shape[1] != len(industry_output):
        raise ValueError(
            f"Use table columns ({use_table.shape[1]}) must match "
            f"industry output length ({len(industry_output)})"
        )

    output_safe = industry_output.astype(float).copy()
    output_safe[output_safe == 0] = 1e-10

    tech_coeff = use_table.div(output_safe, axis=1)
    tech_coeff = tech_coeff.replace([float("inf"), float("-inf")], 0).fillna(0)

    logger.debug(f"Calculated technical coefficients matrix with shape: {tech_coeff.shape}")
    return tech_coeff


def calculate_leontief_inverse(
    tech_coeff: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate Leontief inverse L = (I - A)^{-1}.

    Args:
        tech_coeff: Technical coefficients matrix A.

    Returns:
        Leontief inverse matrix L.

    Raises:
        ValueError: If matrix is singular.
    """
    try:
        identity = np.eye(tech_coeff.shape[0])
        i_minus_a = identity - tech_coeff.values
        leontief_inv = np.linalg.inv(i_minus_a)

        leontief_df = pd.DataFrame(
            leontief_inv,
            index=tech_coeff.index,
            columns=tech_coeff.columns,
        )
        logger.debug(f"Calculated Leontief inverse with shape: {leontief_df.shape}")
        return leontief_df
    except Exception as e:
        raise ValueError(f"Failed to compute Leontief inverse: {e}") from e


def apply_demand_shocks(
    leontief_inv: pd.DataFrame,
    shocks_df: pd.DataFrame,
    sector_col: str = "bea_sector",
    amount_col: str = "shock_amount",
) -> pd.Series:
    """Apply demand shocks using Leontief inverse: production = L × demand.

    Args:
        leontief_inv: Leontief inverse matrix.
        shocks_df: DataFrame with sector codes and shock amounts.
        sector_col: Column name for sector codes.
        amount_col: Column name for shock amounts.

    Returns:
        Production impact by sector as pandas Series.
    """
    try:
        demand_vector = pd.Series(0.0, index=leontief_inv.columns)

        for _, row in shocks_df.iterrows():
            sector = str(row[sector_col])
            amount = float(row[amount_col])

            if sector in demand_vector.index:
                demand_vector[sector] += amount
            else:
                logger.warning(f"Sector {sector} not found in Leontief matrix, skipping")

        production = leontief_inv.dot(demand_vector)

        logger.debug(
            f"Applied shocks to {len(shocks_df)} sectors, "
            f"got production for {len(production)} sectors"
        )
        return production
    except Exception as e:
        logger.error(f"Failed to apply demand shocks: {e}")
        raise


def calculate_employment_from_production(
    production_by_sector: pd.Series,
    employment_coefficients: pd.DataFrame,
) -> pd.Series:
    """Calculate jobs created from production impacts.

    Args:
        production_by_sector: Production impact by sector (dollars).
        employment_coefficients: Employment coefficients by sector.

    Returns:
        Jobs created by sector.
    """
    if employment_coefficients.empty:
        logger.debug("No employment coefficients, using default multiplier")
        return production_by_sector / 100_000

    try:
        jobs_by_sector = pd.Series(0.0, index=production_by_sector.index)

        for sector in production_by_sector.index:
            production_val = production_by_sector[sector]
            sector_coeff = employment_coefficients[
                employment_coefficients["sector"] == str(sector)
            ]

            if not sector_coeff.empty:
                coeff = sector_coeff["employment_coefficient"].iloc[0]
                jobs = (production_val / 1_000_000) * coeff
                jobs_by_sector[sector] = jobs
            else:
                jobs_by_sector[sector] = production_val / 100_000

        return jobs_by_sector
    except Exception as e:
        logger.error(f"Failed to calculate employment: {e}")
        return production_by_sector / 100_000
