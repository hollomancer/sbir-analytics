"""
R StateIO adapter using rpy2 for EPA's USEEIO/StateIO R packages.

This module implements the EconomicModelInterface using rpy2 to call EPA's
StateIO R package for state-level input-output economic modeling.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from ..config.loader import get_config
from .economic_model_interface import EconomicImpactResult, EconomicModelInterface

# Conditional rpy2 import
try:
    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri
    from rpy2.robjects.packages import importr

    RPY2_AVAILABLE = True
except ImportError:
    RPY2_AVAILABLE = False
    ro = None  # type: ignore
    pandas2ri = None  # type: ignore
    importr = None  # type: ignore


@dataclass
class RCacheEntry:
    """Cache entry for R model results."""

    cache_key: str
    model_version: str
    shocks_hash: str
    result_data: dict[str, Any]
    created_at: str


class RStateIOAdapter(EconomicModelInterface):
    """R adapter for EPA StateIO/USEEIO packages via rpy2.

    This adapter calls EPA's StateIO R package through rpy2 to compute
    economic multiplier effects from SBIR spending shocks.
    """

    def __init__(
        self,
        config: Any | None = None,
        cache_enabled: bool = True,
        cache_dir: str | Path | None = None,
    ):
        """Initialize the R StateIO adapter.

        Args:
            config: Optional configuration override
            cache_enabled: Enable result caching
            cache_dir: Directory for cache storage
        """
        if not RPY2_AVAILABLE:
            raise ImportError(
                "rpy2 is not installed. Install with: poetry install --extras r"
            )

        self.config = config or get_config().fiscal_analysis
        self.model_version = getattr(
            self.config, "stateio_model_version", "v2.1"
        )

        # Initialize R interface
        self._init_r_interface()

        # Set up caching
        self.cache_enabled = cache_enabled
        if cache_dir is None:
            cache_dir = Path("data/processed/fiscal_cache")
        self.cache_dir = Path(cache_dir)
        if self.cache_enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._cache: dict[str, pd.DataFrame] = {}

    def _init_r_interface(self) -> None:
        """Initialize R interface and load required packages."""
        try:
            # Activate pandas conversion
            pandas2ri.activate()  # type: ignore

            # Load StateIO and USEEIO packages
            # Note: These must be installed in R first
            try:
                self.stateio = importr("stateior")  # type: ignore
                logger.info("Loaded StateIO R package")
            except Exception as e:
                logger.warning(f"Failed to load StateIO package: {e}")
                logger.warning(
                    "Install StateIO in R with: install.packages('stateior', repos='https://github.com/USEPA/stateior')"
                )
                self.stateio = None

            try:
                self.useeio = importr("useeior")  # type: ignore
                logger.info("Loaded USEEIO R package")
            except Exception as e:
                logger.warning(f"Failed to load USEEIO package: {e}")
                self.useeio = None

        except Exception as e:
            logger.error(f"Failed to initialize R interface: {e}")
            raise

    def _compute_shocks_hash(self, shocks_df: pd.DataFrame) -> str:
        """Compute hash of shocks DataFrame for caching.

        Args:
            shocks_df: Shocks DataFrame

        Returns:
            SHA256 hash string
        """
        # Sort by key columns for consistent hashing
        sorted_df = shocks_df.sort_values(["state", "bea_sector", "fiscal_year"])
        # Convert to JSON for stable hash
        json_str = sorted_df.to_json(orient="records")
        return hashlib.sha256(json_str.encode()).hexdigest()[:16]

    def _get_cache_key(
        self, shocks_df: pd.DataFrame, model_version: str | None = None
    ) -> str:
        """Generate cache key for shocks and model version.

        Args:
            shocks_df: Shocks DataFrame
            model_version: Optional model version override

        Returns:
            Cache key string
        """
        shocks_hash = self._compute_shocks_hash(shocks_df)
        version = model_version or self.model_version
        return f"stateio_{version}_{shocks_hash}"

    def _load_from_cache(self, cache_key: str) -> pd.DataFrame | None:
        """Load results from cache.

        Args:
            cache_key: Cache key

        Returns:
            Cached DataFrame or None
        """
        if not self.cache_enabled:
            return None

        # Check in-memory cache first
        if cache_key in self._cache:
            logger.debug(f"Cache hit (memory): {cache_key}")
            return self._cache[cache_key].copy()

        # Check file cache
        cache_file = self.cache_dir / f"{cache_key}.parquet"
        if cache_file.exists():
            try:
                df = pd.read_parquet(cache_file)
                # Store in memory cache
                self._cache[cache_key] = df
                logger.debug(f"Cache hit (file): {cache_key}")
                return df.copy()
            except Exception as e:
                logger.warning(f"Failed to load cache file {cache_file}: {e}")
                return None

        return None

    def _save_to_cache(self, cache_key: str, result_df: pd.DataFrame) -> None:
        """Save results to cache.

        Args:
            cache_key: Cache key
            result_df: Results DataFrame
        """
        if not self.cache_enabled:
            return

        # Save to memory cache
        self._cache[cache_key] = result_df.copy()

        # Save to file cache
        cache_file = self.cache_dir / f"{cache_key}.parquet"
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            result_df.to_parquet(cache_file, index=False)
            logger.debug(f"Cached results to {cache_file}")
        except Exception as e:
            logger.warning(f"Failed to save cache file {cache_file}: {e}")

    def _convert_shocks_to_r(self, shocks_df: pd.DataFrame) -> Any:
        """Convert pandas DataFrame to R data.frame.

        Args:
            shocks_df: Shocks DataFrame

        Returns:
            R data.frame object
        """
        # Select required columns and ensure proper types
        r_df = shocks_df[["state", "bea_sector", "fiscal_year", "shock_amount"]].copy()
        r_df["shock_amount"] = r_df["shock_amount"].astype(float)

        # Convert to R data.frame
        # pandas2ri.activate() enables automatic conversion
        r_dataframe = pandas2ri.py2rpy(r_df)  # type: ignore

        return r_dataframe

    def _convert_r_to_pandas(self, r_result: Any) -> pd.DataFrame:
        """Convert R data.frame to pandas DataFrame.

        Args:
            r_result: R data.frame object

        Returns:
            pandas DataFrame
        """
        # Convert R data.frame to pandas
        df = pandas2ri.rpy2py(r_result)  # type: ignore

        # Ensure Decimal types for monetary values
        monetary_cols = [
            "wage_impact",
            "proprietor_income_impact",
            "gross_operating_surplus",
            "consumption_impact",
            "tax_impact",
            "production_impact",
        ]
        for col in monetary_cols:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal("0"))

        return df

    def _compute_impacts_r(
        self, shocks_df: pd.DataFrame, model_version: str | None = None
    ) -> pd.DataFrame:
        """Compute impacts using R StateIO package.

        Args:
            shocks_df: Shocks DataFrame
            model_version: Optional model version override

        Returns:
            Results DataFrame
        """
        if self.stateio is None:
            raise RuntimeError(
                "StateIO R package not loaded. Install in R with: "
                "install.packages('stateior', repos='https://github.com/USEPA/stateior')"
            )

        # Convert shocks to R format
        r_shocks = self._convert_shocks_to_r(shocks_df)

        # Call StateIO model
        # This is a placeholder - actual R function calls depend on StateIO API
        # Example structure:
        # r_result = self.stateio.compute_impacts(
        #     shocks=r_shocks,
        #     model_version=model_version or self.model_version
        # )

        # For now, return a placeholder that matches expected structure
        logger.warning(
            "R StateIO computation not fully implemented. "
            "This requires StateIO R package API details."
        )

        # Placeholder: return shocks with basic multiplier
        # TODO: Replace with actual StateIO R package calls
        result_df = shocks_df.copy()
        multiplier = 2.0  # Placeholder multiplier
        result_df["wage_impact"] = result_df["shock_amount"] * Decimal("0.4") * multiplier
        result_df["proprietor_income_impact"] = result_df["shock_amount"] * Decimal("0.1") * multiplier
        result_df["gross_operating_surplus"] = result_df["shock_amount"] * Decimal("0.3") * multiplier
        result_df["consumption_impact"] = result_df["shock_amount"] * Decimal("0.2") * multiplier
        result_df["tax_impact"] = result_df["shock_amount"] * Decimal("0.15") * multiplier
        result_df["production_impact"] = result_df["shock_amount"] * multiplier
        result_df["model_version"] = model_version or self.model_version
        result_df["confidence"] = 0.75
        result_df["quality_flags"] = "placeholder_computation"

        return result_df

    def compute_impacts(
        self,
        shocks_df: pd.DataFrame,
        model_version: str | None = None,
    ) -> pd.DataFrame:
        """Compute economic impacts from spending shocks.

        Args:
            shocks_df: DataFrame with state, bea_sector, fiscal_year, shock_amount
            model_version: Optional model version override

        Returns:
            DataFrame with economic impact components
        """
        # Validate input
        self.validate_input(shocks_df)

        # Check cache
        cache_key = self._get_cache_key(shocks_df, model_version)
        cached_result = self._load_from_cache(cache_key)
        if cached_result is not None:
            logger.info(f"Using cached results for {cache_key}")
            return cached_result

        # Compute impacts
        logger.info(f"Computing impacts for {len(shocks_df)} shocks using R StateIO")
        result_df = self._compute_impacts_r(shocks_df, model_version)

        # Save to cache
        self._save_to_cache(cache_key, result_df)

        return result_df

    def get_model_version(self) -> str:
        """Get the model version string."""
        return self.model_version

    def validate_input(self, shocks_df: pd.DataFrame) -> None:
        """Validate input shocks DataFrame format."""
        super().validate_input(shocks_df)

    def is_available(self) -> bool:
        """Check if R adapter is available."""
        return RPY2_AVAILABLE and self.stateio is not None

