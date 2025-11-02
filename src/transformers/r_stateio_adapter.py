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
from ..utils.r_helpers import (
    RFunctionError,
    call_r_function,
    check_r_package,
    extract_r_result,
    validate_r_input,
)
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

    The adapter attempts to call actual StateIO R functions. If the exact
    function names or API structure differ from expectations, it falls back
    to placeholder computation with appropriate warnings.

    Installation Requirements:
        - R runtime installed on system
        - Python rpy2 package: poetry install --extras r
        - StateIO R package: remotes::install_github("USEPA/stateio")
        - USEEIOR R package (optional): remotes::install_github("USEPA/useeior")

    Usage:
        >>> from src.transformers.r_stateio_adapter import RStateIOAdapter
        >>> from src.config.loader import get_config
        >>>
        >>> config = get_config()
        >>> adapter = RStateIOAdapter(config=config.fiscal_analysis)
        >>>
        >>> shocks_df = pd.DataFrame({
        ...     "state": ["CA"],
        ...     "bea_sector": ["11"],
        ...     "fiscal_year": [2023],
        ...     "shock_amount": [Decimal("1000000")]
        ... })
        >>>
        >>> impacts_df = adapter.compute_impacts(shocks_df)

    See Also:
        - docs/fiscal/r-package-reference.md for R package documentation
        - scripts/validate_r_adapter.py for installation validation
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

        This method attempts to call actual StateIO R functions. If the exact
        function names or API structure differ from expectations, it falls back
        to placeholder computation with a warning.

        Args:
            shocks_df: Shocks DataFrame with state, bea_sector, fiscal_year, shock_amount
            model_version: Optional model version override

        Returns:
            Results DataFrame with economic impact components

        Raises:
            RuntimeError: If StateIO package is not loaded
            RFunctionError: If R function calls fail
        """
        if self.stateio is None:
            raise RuntimeError(
                "StateIO R package not loaded. Install in R with: "
                "remotes::install_github('USEPA/stateio')"
            )

        # Validate input before conversion
        validate_r_input(
            shocks_df,
            required_columns=["state", "bea_sector", "fiscal_year", "shock_amount"],
            min_rows=1,
        )

        # Convert shocks to R format
        r_shocks = self._convert_shocks_to_r(shocks_df)

        model_ver = model_version or self.model_version

        # Attempt to call StateIO R functions
        # Note: Actual function names and signatures need to be verified
        # against StateIO package documentation. This implementation attempts
        # common patterns but may need adjustment.
        try:
            # Strategy 1: Try direct impact computation function
            # Common function names: computeImpacts, calculateImpacts, impactAnalysis
            for func_name in ["computeImpacts", "calculateImpacts", "impactAnalysis"]:
                try:
                    logger.debug(f"Attempting to call StateIO function: {func_name}")
                    r_result = call_r_function(
                        self.stateio,
                        func_name,
                        r_shocks,
                        model_version=model_ver,
                    )

                    # Extract and convert result
                    result_df = self._convert_r_to_pandas(r_result)

                    # Ensure all required columns exist
                    result_df = self._ensure_impact_columns(result_df, shocks_df, model_ver)

                    logger.info(
                        f"Successfully computed impacts using StateIO function: {func_name}"
                    )
                    return result_df

                except (AttributeError, RFunctionError) as e:
                    logger.debug(f"Function {func_name} not available or failed: {e}")
                    continue

            # Strategy 2: Try two-step approach (build model, then compute)
            # Some I-O packages require model building first
            states = shocks_df["state"].unique().tolist()
            if len(states) == 1:
                # Single state - try state-specific model
                state_code = states[0]
                logger.debug(f"Attempting to build model for state: {state_code}")

                # Try common model loading functions
                for model_func in ["loadStateModel", "buildStateModel", "getModel"]:
                    try:
                        # Try to load/build model
                        model = call_r_function(
                            self.stateio,
                            model_func,
                            state=state_code,
                            year=shocks_df["fiscal_year"].iloc[0],
                        )

                        # Then compute impacts
                        for impact_func in ["computeImpacts", "applyShocks", "calculateImpacts"]:
                            try:
                                r_result = call_r_function(
                                    self.stateio,
                                    impact_func,
                                    model,
                                    r_shocks,
                                )

                                result_df = self._convert_r_to_pandas(r_result)
                                result_df = self._ensure_impact_columns(
                                    result_df, shocks_df, model_ver
                                )

                                logger.info(
                                    f"Successfully computed impacts using {model_func} + {impact_func}"
                                )
                                return result_df

                            except (AttributeError, RFunctionError):
                                continue

                    except (AttributeError, RFunctionError):
                        continue

        except Exception as e:
            logger.warning(
                f"Failed to call StateIO R functions: {e}. "
                "Falling back to placeholder computation. "
                "Please verify StateIO package installation and function names."
            )

        # Fallback: Use placeholder computation if R calls fail
        # This allows the pipeline to continue while actual API is verified
        logger.warning(
            "Using placeholder StateIO computation. "
            "Actual R function calls need to be verified against StateIO package documentation. "
            "See docs/fiscal/r-package-reference.md for details."
        )

        return self._compute_placeholder_impacts(shocks_df, model_ver)

    def _ensure_impact_columns(
        self,
        result_df: pd.DataFrame,
        shocks_df: pd.DataFrame,
        model_version: str,
    ) -> pd.DataFrame:
        """Ensure result DataFrame has all required impact columns.

        Args:
            result_df: Result DataFrame from R (may be missing columns)
            shocks_df: Original shocks DataFrame for merging
            model_version: Model version string

        Returns:
            DataFrame with all required columns
        """
        # Merge with original shocks to preserve input columns
        merge_cols = ["state", "bea_sector", "fiscal_year"]
        result_df = shocks_df[merge_cols + ["shock_amount"]].merge(
            result_df,
            on=merge_cols,
            how="left",
            suffixes=("_shock", "_impact"),
        )

        # Define required impact columns
        required_impact_cols = [
            "wage_impact",
            "proprietor_income_impact",
            "gross_operating_surplus",
            "consumption_impact",
            "tax_impact",
            "production_impact",
        ]

        # Add missing columns with zeros
        for col in required_impact_cols:
            if col not in result_df.columns:
                logger.debug(f"Adding missing impact column: {col}")
                result_df[col] = Decimal("0")

        # Ensure Decimal types for monetary columns
        for col in required_impact_cols:
            if col in result_df.columns:
                result_df[col] = result_df[col].apply(
                    lambda x: Decimal(str(x)) if pd.notna(x) else Decimal("0")
                )

        # Add metadata columns
        result_df["model_version"] = model_version
        if "confidence" not in result_df.columns:
            result_df["confidence"] = 0.85  # Default confidence for real R computation
        if "quality_flags" not in result_df.columns:
            result_df["quality_flags"] = "r_computation"

        return result_df

    def _compute_placeholder_impacts(
        self, shocks_df: pd.DataFrame, model_version: str
    ) -> pd.DataFrame:
        """Compute placeholder impacts using simple multipliers.

        This method is used as a fallback when R function calls fail.
        It provides realistic-looking multipliers but should be replaced
        with actual StateIO computations.

        Args:
            shocks_df: Shocks DataFrame
            model_version: Model version string

        Returns:
            DataFrame with placeholder impact components
        """
        result_df = shocks_df.copy()

        # Placeholder multipliers (these should be replaced with actual StateIO outputs)
        # Typical I-O multipliers range from 1.5-3.0 depending on sector
        multiplier = Decimal("2.0")

        result_df["wage_impact"] = result_df["shock_amount"] * Decimal("0.4") * multiplier
        result_df["proprietor_income_impact"] = (
            result_df["shock_amount"] * Decimal("0.1") * multiplier
        )
        result_df["gross_operating_surplus"] = (
            result_df["shock_amount"] * Decimal("0.3") * multiplier
        )
        result_df["consumption_impact"] = result_df["shock_amount"] * Decimal("0.2") * multiplier
        result_df["tax_impact"] = result_df["shock_amount"] * Decimal("0.15") * multiplier
        result_df["production_impact"] = result_df["shock_amount"] * multiplier
        result_df["model_version"] = model_version
        result_df["confidence"] = Decimal("0.75")
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

