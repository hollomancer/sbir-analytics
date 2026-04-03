"""BEA I-O adapter for economic impact computation.

Pure-Python replacement for the former RStateIOAdapter.  Fetches national
Input-Output tables from the BEA REST API and computes Leontief-based
economic multiplier impacts from SBIR spending shocks.

Drop-in replacement: the public interface (compute_impacts, validate_input,
is_available, get_model_version) is identical to the old RStateIOAdapter.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from ..config.loader import get_config
from ..exceptions import ConfigurationError
from .bea_api_client import BEAApiClient
from .bea_io_functions import (
    apply_demand_shocks,
    calculate_employment_coefficients,
    calculate_leontief_inverse,
    calculate_technical_coefficients,
    calculate_value_added_ratios,
    fetch_employment,
    fetch_industry_output,
    fetch_use_table,
    fetch_value_added,
)
from .economic_model_interface import validate_shocks_input


class BEAIOAdapter:
    """BEA I-O adapter for economic impact computation.

    Fetches national Use tables and Value-Added data from the BEA API,
    computes Leontief multipliers, and returns impact estimates broken
    down by wages, GOS, taxes, and production.

    Usage:
        >>> adapter = BEAIOAdapter()
        >>> shocks = pd.DataFrame({
        ...     "state": ["CA"],
        ...     "bea_sector": ["11"],
        ...     "fiscal_year": [2023],
        ...     "shock_amount": [Decimal("1000000")],
        ... })
        >>> impacts = adapter.compute_impacts(shocks)

    Environment:
        Requires BEA_API_KEY (register at https://apps.bea.gov/API/signup/).
    """

    def __init__(
        self,
        config: Any | None = None,
        cache_enabled: bool = True,
        cache_dir: str | Path | None = None,
        api_key: str | None = None,
    ):
        self.config = config or get_config().fiscal_analysis
        self.model_version = getattr(self.config, "stateio_model_version", "v2.1")

        # Initialize BEA API client
        try:
            self._client = BEAApiClient(api_key=api_key)
            self._api_available = True
        except ConfigurationError:
            logger.warning(
                "BEA_API_KEY not set. Adapter will use placeholder computation. "
                "Register at https://apps.bea.gov/API/signup/"
            )
            self._client = None  # type: ignore[assignment]
            self._api_available = False

        # Caching
        self.cache_enabled = cache_enabled
        if cache_dir is None:
            cache_dir = Path("data/processed/fiscal_cache")
        self.cache_dir = Path(cache_dir)
        if self.cache_enabled:
            from sbir_etl.utils.path_utils import ensure_dir

            ensure_dir(self.cache_dir)

        self._cache: dict[str, pd.DataFrame] = {}

        # In-memory cache for fetched BEA tables (avoid re-fetching per state)
        self._use_table_cache: dict[int, pd.DataFrame] = {}
        self._industry_output_cache: dict[int, pd.Series] = {}
        self._va_ratios_cache: dict[int, pd.DataFrame] = {}
        self._emp_coeff_cache: dict[int, pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _compute_shocks_hash(self, shocks_df: pd.DataFrame) -> str:
        sorted_df = shocks_df.sort_values(["state", "bea_sector", "fiscal_year"])
        json_str = sorted_df.to_json(orient="records")
        return hashlib.sha256(json_str.encode()).hexdigest()[:16]

    def _get_cache_key(self, shocks_df: pd.DataFrame, model_version: str | None = None) -> str:
        shocks_hash = self._compute_shocks_hash(shocks_df)
        version = model_version or self.model_version
        return f"bea_io_{version}_{shocks_hash}"

    def _load_from_cache(self, cache_key: str) -> pd.DataFrame | None:
        if not self.cache_enabled:
            return None
        if cache_key in self._cache:
            logger.debug(f"Cache hit (memory): {cache_key}")
            return self._cache[cache_key].copy()
        cache_file = self.cache_dir / f"{cache_key}.parquet"
        if cache_file.exists():
            try:
                df = pd.read_parquet(cache_file)
                self._cache[cache_key] = df
                logger.debug(f"Cache hit (file): {cache_key}")
                return df.copy()
            except Exception as e:
                logger.warning(f"Failed to load cache file {cache_file}: {e}")
        return None

    def _save_to_cache(self, cache_key: str, result_df: pd.DataFrame) -> None:
        if not self.cache_enabled:
            return
        self._cache[cache_key] = result_df.copy()
        cache_file = self.cache_dir / f"{cache_key}.parquet"
        try:
            from sbir_etl.utils.data.file_io import save_dataframe_parquet

            save_dataframe_parquet(result_df, cache_file, index=False)
            logger.debug(f"Cached results to {cache_file}")
        except Exception as e:
            logger.warning(f"Failed to save cache file {cache_file}: {e}")

    # ------------------------------------------------------------------
    # BEA table fetching (with per-year caching)
    # ------------------------------------------------------------------

    def _get_use_table(self, year: int) -> pd.DataFrame:
        if year not in self._use_table_cache:
            self._use_table_cache[year] = fetch_use_table(self._client, year)
        return self._use_table_cache[year]

    def _get_industry_output(self, year: int) -> pd.Series:
        if year not in self._industry_output_cache:
            use_table = self._get_use_table(year)
            self._industry_output_cache[year] = fetch_industry_output(use_table)
        return self._industry_output_cache[year]

    def _get_va_ratios(self, year: int) -> pd.DataFrame:
        if year not in self._va_ratios_cache:
            va_df = fetch_value_added(self._client, year)
            self._va_ratios_cache[year] = calculate_value_added_ratios(va_df)
        return self._va_ratios_cache[year]

    def _get_employment_coefficients(self, year: int) -> pd.DataFrame:
        if year not in self._emp_coeff_cache:
            emp_df = fetch_employment(self._client, year)
            output = self._get_industry_output(year)
            self._emp_coeff_cache[year] = calculate_employment_coefficients(emp_df, output)
        return self._emp_coeff_cache[year]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_bea_sectors(self, shocks_df: pd.DataFrame) -> None:
        if "bea_sector" not in shocks_df.columns:
            return
        sectors = shocks_df["bea_sector"].astype(str)
        invalid = []
        for sector in sectors.unique():
            sector = sector.strip()
            if sector.isdigit() and len(sector) in [1, 2, 3]:
                continue
            if "/" in sector or sector.endswith(("CA", "US", "NY", "TX")):
                continue
            invalid.append(sector)
        if invalid:
            logger.warning(
                f"Found {len(invalid)} potentially invalid BEA sector codes: {invalid[:10]}"
            )

    # ------------------------------------------------------------------
    # Impact computation
    # ------------------------------------------------------------------

    def _compute_impacts_bea(
        self, shocks_df: pd.DataFrame, model_version: str | None = None
    ) -> pd.DataFrame:
        """Compute impacts using BEA I-O tables.

        Falls back to placeholder computation if the BEA API is unavailable.
        """
        if not self._api_available:
            logger.warning(
                "BEA API not available — using placeholder computation. "
                "Set BEA_API_KEY for real I-O analysis."
            )
            return self._compute_placeholder_impacts(
                shocks_df, model_version or self.model_version
            )

        self._validate_bea_sectors(shocks_df)
        model_ver = model_version or self.model_version

        try:
            return self._compute_impacts_via_bea(shocks_df, model_ver)
        except Exception as e:
            logger.warning(f"BEA I-O computation failed: {e}. Falling back to placeholder.")
            return self._compute_placeholder_impacts(shocks_df, model_ver)

    def _compute_impacts_via_bea(
        self, shocks_df: pd.DataFrame, model_version: str
    ) -> pd.DataFrame:
        """Core Leontief computation using BEA Use tables."""
        year = int(shocks_df["fiscal_year"].iloc[0])

        # Fetch national I-O data (cached per year)
        use_table = self._get_use_table(year)
        industry_output = self._get_industry_output(year)

        if use_table.empty or industry_output.empty:
            raise ValueError(f"Could not fetch BEA Use table for year {year}")

        # Build Leontief inverse
        tech_coeff = calculate_technical_coefficients(use_table, industry_output)
        leontief_inv = calculate_leontief_inverse(tech_coeff)

        # Fetch VA ratios for distributing impacts
        va_ratios_df = self._get_va_ratios(year)

        # Process each state's shocks
        # NOTE: BEA national tables are used for all states; state-level
        # scaling could be added later using Regional GDP data.
        states = shocks_df["state"].unique().tolist()
        all_results = []

        for state in states:
            state_shocks = shocks_df[shocks_df["state"] == state].copy()

            try:
                production_by_sector = apply_demand_shocks(leontief_inv, state_shocks)

                for _, shock_row in state_shocks.iterrows():
                    sector = shock_row["bea_sector"]

                    if sector in production_by_sector.index:
                        production_impact = Decimal(str(float(production_by_sector[sector])))
                    else:
                        logger.warning(f"Sector {sector} not in production results, using zero")
                        production_impact = Decimal("0")

                    # Value-added breakdown
                    wage_ratio = Decimal("0.4")
                    gos_ratio = Decimal("0.3")
                    tax_ratio = Decimal("0.15")
                    proprietor_ratio = Decimal("0.0")
                    used_actual_ratios = False

                    if not va_ratios_df.empty:
                        sector_ratios = va_ratios_df[va_ratios_df["sector"] == str(sector)]
                        if not sector_ratios.empty:
                            wage_ratio = Decimal(str(sector_ratios["wage_ratio"].iloc[0]))
                            gos_ratio = Decimal(str(sector_ratios["gos_ratio"].iloc[0]))
                            tax_ratio = Decimal(str(sector_ratios["tax_ratio"].iloc[0]))
                            proprietor_ratio = Decimal(
                                str(sector_ratios["proprietor_income_ratio"].iloc[0])
                            )
                            used_actual_ratios = True

                    wage_impact = production_impact * wage_ratio
                    gos_impact = production_impact * gos_ratio
                    tax_impact = production_impact * tax_ratio
                    proprietor_impact = production_impact * proprietor_ratio

                    quality_flags = (
                        "bea_api_with_ratios"
                        if used_actual_ratios
                        else "bea_api_default_ratios"
                    )

                    all_results.append(
                        {
                            "state": state,
                            "bea_sector": sector,
                            "fiscal_year": shock_row["fiscal_year"],
                            "wage_impact": wage_impact,
                            "proprietor_income_impact": proprietor_impact,
                            "gross_operating_surplus": gos_impact,
                            "consumption_impact": production_impact * Decimal("0.2"),
                            "tax_impact": tax_impact,
                            "production_impact": production_impact,
                            "model_version": model_version,
                            "confidence": Decimal("0.85"),
                            "quality_flags": quality_flags,
                        }
                    )

                logger.info(f"Computed impacts for {state} using BEA I-O tables")

            except Exception as e:
                logger.error(f"Failed BEA I-O computation for {state}: {e}")
                for _, shock_row in state_shocks.iterrows():
                    all_results.append(
                        {
                            "state": state,
                            "bea_sector": shock_row["bea_sector"],
                            "fiscal_year": shock_row["fiscal_year"],
                            "wage_impact": Decimal("0"),
                            "proprietor_income_impact": Decimal("0"),
                            "gross_operating_surplus": Decimal("0"),
                            "consumption_impact": Decimal("0"),
                            "tax_impact": Decimal("0"),
                            "production_impact": Decimal("0"),
                            "model_version": model_version,
                            "confidence": Decimal("0.0"),
                            "quality_flags": f"bea_api_failed:{str(e)[:50]}",
                        }
                    )

        result_df = pd.DataFrame(all_results)
        return self._ensure_impact_columns(result_df, shocks_df, model_version)

    # ------------------------------------------------------------------
    # Column/type normalisation
    # ------------------------------------------------------------------

    def _ensure_impact_columns(
        self,
        result_df: pd.DataFrame,
        shocks_df: pd.DataFrame,
        model_version: str,
    ) -> pd.DataFrame:
        merge_cols = ["state", "bea_sector", "fiscal_year"]
        result_df = shocks_df[merge_cols + ["shock_amount"]].merge(
            result_df,
            on=merge_cols,
            how="left",
            suffixes=("_shock", "_impact"),
        )

        required_impact_cols = [
            "wage_impact",
            "proprietor_income_impact",
            "gross_operating_surplus",
            "consumption_impact",
            "tax_impact",
            "production_impact",
        ]

        for col in required_impact_cols:
            if col not in result_df.columns:
                result_df[col] = Decimal("0")

        for col in required_impact_cols:
            if col in result_df.columns:
                result_df[col] = result_df[col].apply(
                    lambda x: Decimal(str(x)) if pd.notna(x) else Decimal("0")
                )

        result_df["model_version"] = model_version
        if "confidence" not in result_df.columns:
            result_df["confidence"] = 0.85
        if "quality_flags" not in result_df.columns:
            result_df["quality_flags"] = "bea_api_computation"

        return result_df

    # ------------------------------------------------------------------
    # Placeholder fallback
    # ------------------------------------------------------------------

    def _compute_placeholder_impacts(
        self, shocks_df: pd.DataFrame, model_version: str
    ) -> pd.DataFrame:
        result_df = shocks_df.copy()
        multiplier = Decimal("2.0")

        result_df["wage_impact"] = result_df["shock_amount"] * Decimal("0.4") * multiplier  # type: ignore[operator]
        result_df["proprietor_income_impact"] = (
            result_df["shock_amount"] * Decimal("0.1") * multiplier  # type: ignore[operator]
        )
        result_df["gross_operating_surplus"] = (
            result_df["shock_amount"] * Decimal("0.3") * multiplier  # type: ignore[operator]
        )
        result_df["consumption_impact"] = result_df["shock_amount"] * Decimal("0.2") * multiplier  # type: ignore[operator]
        result_df["tax_impact"] = result_df["shock_amount"] * Decimal("0.15") * multiplier  # type: ignore[operator]
        result_df["production_impact"] = result_df["shock_amount"] * multiplier
        result_df["model_version"] = model_version
        result_df["confidence"] = Decimal("0.75")
        result_df["quality_flags"] = "placeholder_computation"

        return result_df

    # ------------------------------------------------------------------
    # Public interface (matches old RStateIOAdapter)
    # ------------------------------------------------------------------

    def compute_impacts(
        self,
        shocks_df: pd.DataFrame,
        model_version: str | None = None,
    ) -> pd.DataFrame:
        """Compute economic impacts from spending shocks.

        Args:
            shocks_df: DataFrame with state, bea_sector, fiscal_year, shock_amount.
            model_version: Optional model version override.

        Returns:
            DataFrame with economic impact components.
        """
        self.validate_input(shocks_df)

        cache_key = self._get_cache_key(shocks_df, model_version)
        cached_result = self._load_from_cache(cache_key)
        if cached_result is not None:
            logger.info(f"Using cached results for {cache_key}")
            return cached_result

        logger.info(f"Computing impacts for {len(shocks_df)} shocks using BEA I-O tables")
        result_df = self._compute_impacts_bea(shocks_df, model_version)

        self._save_to_cache(cache_key, result_df)
        return result_df

    def get_model_version(self) -> str:
        return self.model_version

    def validate_input(self, shocks_df: pd.DataFrame) -> None:
        validate_shocks_input(shocks_df)

    def is_available(self) -> bool:
        return self._api_available


# Backward-compatible alias so existing imports keep working
RStateIOAdapter = BEAIOAdapter
RPY2_AVAILABLE = True  # Always "available" — no R dependency needed
