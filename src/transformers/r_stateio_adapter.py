"""
R StateIO adapter using rpy2 for EPA's StateIO R package.

This module implements the EconomicModelInterface using rpy2 to call EPA's
StateIO R package for state-level input-output economic modeling.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from ..config.loader import get_config
from ..exceptions import DependencyError
from ..utils.r_helpers import validate_r_input
from .economic_model_interface import EconomicModelInterface


# Try to import StateIO function wrappers (may not be available if import fails)
try:
    from .r_stateio_functions import (
        apply_demand_shocks,
        build_state_model,
        calculate_leontief_inverse,
        calculate_technical_coefficients,
        calculate_value_added_ratios,
        extract_industry_output_from_model,
        extract_use_table_from_model,
        get_state_value_added,
    )

    STATEIO_FUNCTIONS_AVAILABLE = True
except ImportError:
    STATEIO_FUNCTIONS_AVAILABLE = False
    # Define stubs to avoid NameError
    apply_demand_shocks = None  # type: ignore
    build_state_model = None  # type: ignore
    calculate_leontief_inverse = None  # type: ignore
    calculate_technical_coefficients = None  # type: ignore
    calculate_value_added_ratios = None  # type: ignore
    extract_industry_output_from_model = None  # type: ignore
    extract_use_table_from_model = None  # type: ignore
    get_state_value_added = None  # type: ignore

# Conditional rpy2 import
try:
    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri
    from rpy2.robjects.conversion import localconverter
    from rpy2.robjects.packages import importr

    RPY2_AVAILABLE = True
except ImportError:
    RPY2_AVAILABLE = False
    ro = None
    pandas2ri = None
    localconverter = None
    importr = None


@dataclass
class RCacheEntry:
    """Cache entry for R model results."""

    cache_key: str
    model_version: str
    shocks_hash: str
    result_data: dict[str, Any]
    created_at: str


class RStateIOAdapter(EconomicModelInterface):
    """R adapter for EPA StateIO package via rpy2.

    This adapter calls EPA's StateIO R package through rpy2 to compute
    economic multiplier effects from SBIR spending shocks.

    The adapter attempts to call actual StateIO R functions. If the exact
    function names or API structure differ from expectations, it falls back
    to placeholder computation with appropriate warnings.

    Installation Requirements:
        - R runtime installed on system
        - Python rpy2 package: poetry install --extras r
        - StateIO R package: remotes::install_github("USEPA/stateio")

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
            raise ImportError("rpy2 is not installed. Install with: poetry install --extras r")

        self.config = config or get_config().fiscal_analysis
        self.model_version = getattr(self.config, "stateio_model_version", "v2.1")

        # Initialize R interface
        self._init_r_interface()

        # Set up caching
        self.cache_enabled = cache_enabled
        if cache_dir is None:
            cache_dir = Path("data/processed/fiscal_cache")
        self.cache_dir = Path(cache_dir)
        if self.cache_enabled:
            from src.utils.common.path_utils import ensure_dir

            ensure_dir(self.cache_dir)

        self._cache: dict[str, pd.DataFrame] = {}

    def _init_r_interface(self) -> None:
        """Initialize R interface and load required packages."""
        try:
            # Set up pandas conversion (handle both old and new rpy2 APIs)
            try:
                # Try new API (rpy2 >= 3.5.0): use context manager pattern
                # pandas2ri.converter is available without activate
                self._pandas_converter = pandas2ri.converter
                logger.debug("Using rpy2 modern conversion API")
            except (AttributeError, TypeError):
                # Fall back to old API if needed
                try:
                    pandas2ri.activate()
                    self._pandas_converter = None
                    logger.debug("Using rpy2 legacy activate() method")
                except (DeprecationWarning, Exception) as deprecation_e:
                    # If activate() raises deprecation warning as exception
                    logger.warning(
                        f"pandas2ri.activate() deprecated, using converter directly: {deprecation_e}"
                    )
                    self._pandas_converter = (
                        pandas2ri.converter if hasattr(pandas2ri, "converter") else None
                    )

            # Load StateIO package
            # Note: This must be installed in R first
            try:
                self.stateio = importr("stateior")
                logger.info("Loaded StateIO R package")
            except Exception as e:
                logger.warning(f"Failed to load StateIO package: {e}")
                logger.warning(
                    "Install StateIO in R with: remotes::install_github('USEPA/stateio')"
                )
                self.stateio = None

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

    def _get_cache_key(self, shocks_df: pd.DataFrame, model_version: str | None = None) -> str:
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
            from src.utils.data.file_io import save_dataframe_parquet

            save_dataframe_parquet(result_df, cache_file, index=False)
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

        # Ensure string columns are proper strings (not object type)
        r_df["state"] = r_df["state"].astype(str)
        r_df["bea_sector"] = r_df["bea_sector"].astype(str)
        r_df["fiscal_year"] = r_df["fiscal_year"].astype(int)

        # Convert to R data.frame using appropriate conversion method
        if self._pandas_converter is not None:
            # Use modern rpy2 conversion with context manager
            from rpy2.robjects.conversion import localconverter

            with localconverter(ro.default_converter + self._pandas_converter):
                r_dataframe = ro.conversion.py2rpy(r_df)
        else:
            # Fall back to pandas2ri direct conversion
            r_dataframe = pandas2ri.py2rpy(r_df)

        return r_dataframe

    def _convert_r_to_pandas(self, r_result: Any) -> pd.DataFrame:
        """Convert R data.frame to pandas DataFrame.

        Args:
            r_result: R data.frame object

        Returns:
            pandas DataFrame
        """
        # Convert R data.frame to pandas using appropriate conversion method
        if self._pandas_converter is not None:
            # Use modern rpy2 conversion with context manager
            from rpy2.robjects.conversion import localconverter

            with localconverter(ro.default_converter + self._pandas_converter):
                df = ro.conversion.rpy2py(r_result)
        else:
            # Fall back to pandas2ri direct conversion
            df = pandas2ri.rpy2py(r_result)

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
            raise DependencyError(
                "StateIO R package not loaded. Install in R with: "
                "remotes::install_github('USEPA/stateio')",
                dependency_name="stateior",
                component="transformer.r_stateio_adapter",
                operation="calculate_impacts_stateio",
                details={"install_command": "remotes::install_github('USEPA/stateio')"},
            )

        # Validate input before conversion
        validate_r_input(
            shocks_df,
            required_columns=["state", "bea_sector", "fiscal_year", "shock_amount"],
            min_rows=1,
        )

        # Validate BEA sector codes format
        self._validate_bea_sectors(shocks_df)

        # Convert shocks to R format
        self._convert_shocks_to_r(shocks_df)

        model_ver = model_version or self.model_version

        # Use direct StateIO approach
        try:
            if self.stateio is not None and STATEIO_FUNCTIONS_AVAILABLE:
                try:
                    return self._compute_impacts_via_stateio(shocks_df, model_ver)
                except Exception as e:
                    logger.warning(f"Direct StateIO approach failed: {e}")

        except Exception as e:
            logger.warning(
                f"Failed to call R package functions: {e}. Falling back to placeholder computation."
            )

        # Fallback: Use placeholder computation if R calls fail
        # This allows the pipeline to continue while actual API is verified
        logger.warning(
            "Using placeholder StateIO computation. "
            "Actual R function calls need to be verified against StateIO package documentation. "
            "See docs/fiscal/r-package-reference.md for details."
        )

        return self._compute_placeholder_impacts(shocks_df, model_ver)

    def _compute_impacts_via_stateio(
        self, shocks_df: pd.DataFrame, model_version: str
    ) -> pd.DataFrame:
        """Compute impacts using direct StateIO functions.

        Args:
            shocks_df: Shocks DataFrame
            model_version: Model version string

        Returns:
            DataFrame with impact components
        """
        if not STATEIO_FUNCTIONS_AVAILABLE:
            raise ImportError("r_stateio_functions module not available")

        if self.stateio is None:
            raise DependencyError(
                "StateIO package not loaded",
                dependency_name="stateior",
                component="transformer.r_stateio_adapter",
                operation="_calculate_impacts_stateio_fallback",
                details={"install_command": "remotes::install_github('USEPA/stateio')"},
            )

        year = int(shocks_df["fiscal_year"].iloc[0])
        states = shocks_df["state"].unique().tolist()
        all_results = []

        for state in states:
            state_shocks = shocks_df[shocks_df["state"] == state].copy()

            try:
                logger.debug(f"Building StateIO model for state: {state}")

                # Build state IO table
                specs = {"BaseIOSchema": "2017"}
                state_model = build_state_model(self.stateio, state, year, specs)

                # Extract Use table and industry output from model
                use_table = extract_use_table_from_model(state_model, self._pandas_converter)
                industry_output = extract_industry_output_from_model(
                    state_model, self._pandas_converter
                )

                if use_table is None or industry_output is None:
                    logger.warning(
                        f"Could not extract Use table or industry output for {state}, "
                        "using placeholder"
                    )
                    raise ValueError("Missing Use table or industry output")

                # Calculate technical coefficients matrix A
                tech_coeff = calculate_technical_coefficients(use_table, industry_output)

                # Calculate Leontief inverse L = (I - A)^-1
                leontief_inv = calculate_leontief_inverse(tech_coeff)

                # Apply demand shocks to get production impacts
                production_by_sector = apply_demand_shocks(leontief_inv, state_shocks)

                # Get value added components and calculate ratios
                va_components = get_state_value_added(self.stateio, state, year, specs)
                va_ratios_df = calculate_value_added_ratios(
                    va_components, converter=self._pandas_converter
                )

                # Build result rows for each sector shock
                for _, shock_row in state_shocks.iterrows():
                    sector = shock_row["bea_sector"]

                    # Get production impact for this sector
                    if sector in production_by_sector.index:
                        production_impact = Decimal(str(float(production_by_sector[sector])))
                    else:
                        logger.warning(f"Sector {sector} not in production results, using zero")
                        production_impact = Decimal("0")

                    # Get value added ratios for this sector
                    wage_ratio = Decimal("0.4")  # Default
                    gos_ratio = Decimal("0.3")  # Default
                    tax_ratio = Decimal("0.15")  # Default
                    proprietor_ratio = Decimal("0.0")  # Default
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

                    # Calculate value added components
                    wage_impact = production_impact * wage_ratio
                    gos_impact = production_impact * gos_ratio
                    tax_impact = production_impact * tax_ratio
                    proprietor_impact = production_impact * proprietor_ratio

                    quality_flags = (
                        "stateio_direct_with_ratios"
                        if used_actual_ratios
                        else "stateio_direct_default_ratios"
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

                logger.info(f"Computed impacts for {state} using direct StateIO matrix calculation")

            except Exception as e:
                logger.error(f"Failed StateIO computation for {state}: {e}")
                # Add placeholder results for failed state
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
                            "quality_flags": f"stateio_failed:{str(e)[:50]}",
                        }
                    )
                continue

        result_df = pd.DataFrame(all_results)
        return self._ensure_impact_columns(result_df, shocks_df, model_version)

    def _validate_bea_sectors(self, shocks_df: pd.DataFrame) -> None:
        """Validate BEA sector codes format.

        StateIO expects BEA sector codes in specific formats:
        - Summary level: "11", "21", "22", etc. (2-digit codes)
        - Detail level: "111CA", "111US", etc. (with location suffix for two-region models)
        - Standard format: 2-digit numeric codes for Summary level

        Args:
            shocks_df: Shocks DataFrame with bea_sector column

        Raises:
            ValueError: If sector codes are invalid
        """
        if "bea_sector" not in shocks_df.columns:
            return

        sectors = shocks_df["bea_sector"].astype(str)

        # Check for invalid formats
        invalid = []

        for sector in sectors.unique():
            # Remove whitespace
            sector = sector.strip()

            # Check if it's a valid BEA Summary code (2 digits)
            if not sector.isdigit() or len(sector) not in [1, 2, 3]:
                # Allow codes with location suffix (e.g., "111CA", "11/CA")
                if "/" in sector or sector.endswith(("CA", "US", "NY", "TX")):
                    # Likely a detail code or location-suffixed code
                    continue
                elif sector.isdigit() and len(sector) in [1, 2, 3]:
                    # Valid numeric code
                    continue
                else:
                    invalid.append(sector)

        if invalid:
            logger.warning(
                f"Found {len(invalid)} potentially invalid BEA sector codes: {invalid[:10]}"
            )
            # Don't raise error - let R packages validate
            # They may accept formats we don't recognize

    def _normalize_bea_sector(self, sector: str, state: str | None = None) -> str:
        """Normalize BEA sector code to format expected by StateIO.

        Args:
            sector: BEA sector code (may include leading zeros or location suffixes)
            state: Optional state code for two-region models

        Returns:
            Normalized sector code
        """
        sector = str(sector).strip()

        # Remove leading zeros for numeric codes (e.g., "011" -> "11")
        if sector.isdigit():
            sector = str(int(sector))

        return sector

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
