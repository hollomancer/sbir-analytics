"""StateIO R package function wrappers for economic impact computation.

This module provides Python wrappers for StateIO and USEEIOR R package functions
used in fiscal returns analysis.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger

from ..exceptions import DependencyError
from ..utils.r_helpers import RFunctionError, call_r_function


# Conditional rpy2 import
try:
    import rpy2.robjects as ro
    from rpy2.robjects.conversion import localconverter

    RPY2_AVAILABLE = True
except ImportError:
    RPY2_AVAILABLE = False
    ro = None
    localconverter = None


def build_state_model(
    stateio_pkg: Any,
    state: str,
    year: int,
    specs: dict[str, Any] | None = None,
) -> Any:
    """Build a full two-region IO table for a state using StateIO.

    Args:
        stateio_pkg: StateIO R package object from importr()
        state: Two-letter state code (e.g., "CA", "NY")
        year: Year for the model
        specs: Model specifications (BaseIOSchema, etc.)

    Returns:
        R list object containing two-region IO tables

    Raises:
        RFunctionError: If model building fails
    """
    if not RPY2_AVAILABLE:
        raise DependencyError(
            "rpy2 is not available. Install with: poetry install --extras r",
            dependency_name="rpy2",
            component="transformer.r_stateio_functions",
            details={"install_command": "poetry install --extras r"},
        )

    if specs is None:
        specs = {"BaseIOSchema": "2017"}

    # Convert specs dict to R list
    r_specs = ro.ListVector(specs)

    try:
        model = call_r_function(
            stateio_pkg,
            "buildFullTwoRegionIOTable",
            state=state,
            year=year,
            iolevel="Summary",
            specs=r_specs,
        )

        logger.info(f"Built StateIO model for {state}, year {year}")
        return model

    except RFunctionError as e:
        logger.error(f"Failed to build StateIO model for {state}: {e}")
        raise


def get_state_value_added(
    stateio_pkg: Any,
    state: str,
    year: int,
    specs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Get state Gross Value Added components (wages, GOS, taxes).

    Args:
        stateio_pkg: StateIO R package object
        state: Two-letter state code
        year: Year for the data
        specs: Model specifications

    Returns:
        Dictionary with GVA components:
        - wages: Employee compensation
        - proprietor_income: Proprietor income (if available)
        - gos: Gross Operating Surplus
        - taxes: Tax data
    """
    if specs is None:
        specs = {"BaseIOSchema": "2017"}

    r_specs = ro.ListVector(specs)

    components = {}

    # Get employee compensation (wages)
    try:
        wages = call_r_function(
            stateio_pkg, "getStateEmpCompensation", state=state, year=year, specs=r_specs
        )
        components["wages"] = wages
    except RFunctionError as e:
        logger.warning(f"Could not get employee compensation for {state}: {e}")

    # Get Gross Operating Surplus
    try:
        gos = call_r_function(stateio_pkg, "getStateGOS", state=state, year=year, specs=r_specs)
        components["gos"] = gos
    except RFunctionError as e:
        logger.warning(f"Could not get GOS for {state}: {e}")

    # Get taxes
    try:
        taxes = call_r_function(stateio_pkg, "getStateTax", state=state, year=year, specs=r_specs)
        components["taxes"] = taxes
    except RFunctionError as e:
        logger.warning(f"Could not get taxes for {state}: {e}")

    # Try to get full GVA (includes all components)
    try:
        gva = call_r_function(stateio_pkg, "getStateGVA", state=state, year=year, specs=r_specs)
        components["gva"] = gva
    except RFunctionError as e:
        logger.debug(f"Could not get full GVA for {state}: {e}")

    return components


def convert_r_gva_to_dataframe(
    r_object: Any,
    converter: Any | None = None,
) -> pd.DataFrame | None:
    """Convert R GVA object to pandas DataFrame.

    Args:
        r_object: R object from StateIO GVA functions
        converter: Optional pandas2ri converter for rpy2 conversion

    Returns:
        DataFrame with GVA components by sector, or None if conversion fails
    """
    if not RPY2_AVAILABLE:
        logger.warning("rpy2 not available, cannot convert R GVA object")
        return None

    if r_object is None:
        return None

    try:
        # Try conversion with pandas2ri
        if converter is not None:
            from rpy2.robjects.conversion import localconverter

            with localconverter(ro.default_converter + converter):
                df = ro.conversion.rpy2py(r_object)
        else:
            # Fall back to direct pandas2ri conversion
            from rpy2.robjects import pandas2ri

            df = pandas2ri.rpy2py(r_object)

        # Ensure it's a DataFrame
        if not isinstance(df, pd.DataFrame):
            logger.warning(f"R GVA object converted to {type(df)}, not DataFrame")
            # Try to convert to DataFrame if it's a Series or array
            if hasattr(df, "to_frame"):
                df = df.to_frame()
            else:
                return None

        return df

    except Exception as e:
        logger.warning(f"Failed to convert R GVA object to DataFrame: {e}")
        return None


def calculate_value_added_ratios(
    va_components: dict[str, Any],
    converter: Any | None = None,
) -> pd.DataFrame:
    """Calculate value added ratios by sector from StateIO GVA components.

    This function converts R GVA objects to DataFrames and calculates ratios
    of each component (wages, GOS, taxes) relative to total industry output.

    Args:
        va_components: Dictionary of GVA components from get_state_value_added()
        converter: Optional pandas2ri converter for rpy2 conversion

    Returns:
        DataFrame with columns:
        - sector: BEA sector code
        - wage_ratio: Wage share of output
        - gos_ratio: GOS share of output
        - tax_ratio: Tax share of output
        - proprietor_income_ratio: Proprietor income share (if available)

    Note:
        If conversion fails or data is unavailable, returns empty DataFrame.
        Caller should use default ratios when this returns empty.
    """
    if not va_components:
        logger.debug("No value added components provided")
        return pd.DataFrame()

    try:
        # Convert each component to DataFrame
        wages_df = convert_r_gva_to_dataframe(va_components.get("wages"), converter)
        gos_df = convert_r_gva_to_dataframe(va_components.get("gos"), converter)
        taxes_df = convert_r_gva_to_dataframe(va_components.get("taxes"), converter)
        gva_df = convert_r_gva_to_dataframe(va_components.get("gva"), converter)

        # If we have GVA total, use it to calculate ratios
        if gva_df is not None and not gva_df.empty:
            # GVA DataFrame structure depends on StateIO API
            # Typically: sectors as index/column, values as data
            logger.debug(f"GVA DataFrame shape: {gva_df.shape}, columns: {gva_df.columns.tolist()}")

            # Try to identify sector column and value columns
            # StateIO typically returns DataFrames with BEA sector codes as index
            if wages_df is not None and gos_df is not None and taxes_df is not None:
                # Calculate ratios by sector
                ratios_data = []

                # Align DataFrames by sector (assuming sectors in index or a column)
                # This is a simplified approach - actual implementation may need adjustment
                sectors = None
                if hasattr(wages_df, "index"):
                    sectors = wages_df.index
                elif "sector" in wages_df.columns:
                    sectors = wages_df["sector"]
                elif "BEA" in wages_df.columns:
                    sectors = wages_df["BEA"]

                if sectors is not None:
                    for sector in sectors:
                        try:
                            # Extract values for this sector
                            # Assume first numeric column contains the values
                            wage_val = _extract_sector_value(wages_df, sector)
                            gos_val = _extract_sector_value(gos_df, sector)
                            tax_val = _extract_sector_value(taxes_df, sector)

                            # Calculate total value added for this sector
                            total_va = wage_val + gos_val + tax_val

                            # Calculate ratios (avoid division by zero)
                            if total_va > 0:
                                ratios_data.append(
                                    {
                                        "sector": str(sector),
                                        "wage_ratio": float(wage_val / total_va),
                                        "gos_ratio": float(gos_val / total_va),
                                        "tax_ratio": float(tax_val / total_va),
                                        "proprietor_income_ratio": 0.0,  # TODO: extract if available
                                    }
                                )
                        except Exception as e:
                            logger.debug(f"Could not calculate ratios for sector {sector}: {e}")
                            continue

                if ratios_data:
                    return pd.DataFrame(ratios_data)

        logger.debug("Could not calculate value added ratios from components")
        return pd.DataFrame()

    except Exception as e:
        logger.warning(f"Failed to calculate value added ratios: {e}")
        return pd.DataFrame()


def _extract_sector_value(df: pd.DataFrame, sector: str | int) -> float:
    """Extract numeric value for a sector from GVA DataFrame.

    Args:
        df: DataFrame with sector data
        sector: Sector code to extract

    Returns:
        Numeric value for the sector

    Raises:
        ValueError: If sector not found or value cannot be extracted
    """
    # Try index lookup first
    if sector in df.index:
        # Get the first numeric column value
        numeric_cols = df.select_dtypes(include=["number"]).columns
        if len(numeric_cols) > 0:
            return float(df.loc[sector, numeric_cols[0]])

    # Try column lookup
    if "sector" in df.columns or "BEA" in df.columns:
        sector_col = "sector" if "sector" in df.columns else "BEA"
        sector_row = df[df[sector_col] == sector]
        if not sector_row.empty:
            numeric_cols = sector_row.select_dtypes(include=["number"]).columns
            if len(numeric_cols) > 0:
                return float(sector_row[numeric_cols[0]].iloc[0])

    raise ValueError(f"Could not extract value for sector {sector}")


def build_useeior_state_models(
    useeior_pkg: Any,
    modelname: str,
    year: int | None = None,
    configpaths: list[str] | None = None,
    validate: bool = False,
) -> Any:
    """Build two-region USEEIOR models for all states.

    This is often easier than building StateIO models separately, as it
    integrates StateIO internally.

    Args:
        useeior_pkg: USEEIOR R package object from importr()
        modelname: Name of model specification (e.g., "USEEIO2012")
        year: Optional year for models
        configpaths: Optional paths to config files
        validate: If True, print validation results

    Returns:
        R list object with state models (indexed by state code)

    Raises:
        RFunctionError: If model building fails
    """
    kwargs = {
        "modelname": modelname,
        "validate": validate,
    }

    if year is not None:
        kwargs["year"] = year

    if configpaths is not None:
        kwargs["configpaths"] = ro.StrVector(configpaths)

    try:
        models = call_r_function(useeior_pkg, "buildTwoRegionModels", **kwargs)

        logger.info(f"Built USEEIOR two-region models for all states using {modelname}")
        return models

    except RFunctionError as e:
        logger.error(f"Failed to build USEEIOR state models: {e}")
        raise


def calculate_impacts_with_useeior(
    useeior_pkg: Any,
    model: Any,
    demand_vector: Any,
    perspective: str = "DIRECT",
    location: str | None = None,
    use_domestic_requirements: bool = False,
) -> Any:
    """Calculate economic and environmental impacts using USEEIOR.

    Args:
        useeior_pkg: USEEIOR R package object
        model: USEEIOR model object (state or national)
        demand_vector: Demand vector (can be R named vector or DataFrame)
        perspective: "DIRECT" or "FINAL"
        location: Location code for two-region models (e.g., "CA")
        use_domestic_requirements: Use domestic requirements matrix

    Returns:
        R list with calculation results containing:
        - N: Direct+indirect flows (LCI)
        - L: Total requirements matrix
        - H_r: Total impacts (DIRECT perspective)
        - H_l: Total impacts (FINAL perspective)

    Raises:
        RFunctionError: If calculation fails
    """
    kwargs = {
        "model": model,
        "perspective": perspective,
        "demand": demand_vector,
        "use_domestic_requirements": use_domestic_requirements,
    }

    if location is not None:
        kwargs["location"] = location

    try:
        result = call_r_function(useeior_pkg, "calculateEEIOModel", **kwargs)

        logger.info(
            f"Calculated impacts with USEEIOR (perspective={perspective}, " f"location={location})"
        )
        return result

    except RFunctionError as e:
        logger.error(f"Failed to calculate impacts with USEEIOR: {e}")
        raise


def format_demand_vector_from_shocks(
    useeior_pkg: Any,
    model: Any,
    shocks_df: pd.DataFrame,
    sector_col: str = "bea_sector",
    amount_col: str = "shock_amount",
) -> Any:
    """Format spending shocks DataFrame as USEEIOR demand vector.

    Args:
        useeior_pkg: USEEIOR R package object
        model: USEEIOR model object (for sector validation)
        shocks_df: DataFrame with sectors and shock amounts
        sector_col: Column name for BEA sector codes
        amount_col: Column name for shock amounts

    Returns:
        R named vector with sector codes as names and amounts as values

    Raises:
        RFunctionError: If formatting fails
    """
    if not RPY2_AVAILABLE:
        raise DependencyError(
            "rpy2 is not available. Install with: poetry install --extras r",
            dependency_name="rpy2",
            component="transformer.r_stateio_functions",
            details={"install_command": "poetry install --extras r"},
        )

    # Extract sectors and amounts
    sectors = shocks_df[sector_col].astype(str).tolist()
    amounts = shocks_df[amount_col].astype(float).tolist()

    # Create R named vector
    r_vector = ro.FloatVector(amounts)
    r_vector.names = ro.StrVector(sectors)

    # Try to format using USEEIOR function if available
    try:
        formatted = call_r_function(useeior_pkg, "formatDemandVector", model=model, demand=r_vector)
        return formatted
    except RFunctionError:
        # If formatting function not available, return the named vector as-is
        logger.debug("formatDemandVector not available, using raw named vector")
        return r_vector


def extract_economic_components_from_impacts(
    impacts_result: Any,
    model: Any,
    converter: Any,
) -> pd.DataFrame:
    """Extract economic impact components from USEEIOR calculation results.

    This function attempts to extract wage, income, tax, and production impacts
    from USEEIOR results. Note: USEEIOR primarily focuses on environmental impacts,
    so economic components may need to be derived from model matrices or value added data.

    Args:
        impacts_result: Result from calculateEEIOModel()
        model: USEEIOR model object (contains value added information)
        converter: pandas2ri converter for R-to-Python conversion

    Returns:
        DataFrame with impact components by sector
    """
    if not RPY2_AVAILABLE:
        raise DependencyError(
            "rpy2 is not available. Install with: poetry install --extras r",
            dependency_name="rpy2",
            component="transformer.r_stateio_functions",
            details={"install_command": "poetry install --extras r"},
        )

    # Extract production impacts from N matrix (commodity outputs)
    try:
        with localconverter(ro.default_converter + converter):
            n_matrix = ro.conversion.rpy2py(impacts_result.rx2("N"))

        # N matrix contains commodity outputs
        # Sum by sector to get production impacts
        if isinstance(n_matrix, pd.DataFrame):
            production_impacts = n_matrix.sum(axis=1)  # Sum across all commodities per sector
        else:
            # If it's a matrix, convert to DataFrame
            production_impacts = pd.Series(
                n_matrix.sum(axis=1) if hasattr(n_matrix, "sum") else n_matrix.flatten()
            )

    except Exception as e:
        logger.warning(f"Could not extract production impacts from N matrix: {e}")
        production_impacts = None

    # Extract value added components from model
    # This requires accessing model$ValueAdded or similar
    # Implementation depends on actual model structure

    # For now, return a basic structure
    result_data = {}

    if production_impacts is not None:
        result_data["production_impact"] = production_impacts

    # TODO: Extract actual wage, GOS, tax components from model value added tables
    # This may require additional StateIO function calls to get value added ratios

    return pd.DataFrame(result_data)


def compute_impacts_via_useeior_state_models(
    useeior_pkg: Any,
    stateio_pkg: Any,
    shocks_df: pd.DataFrame,
    modelname: str = "USEEIO2012",
    year: int | None = None,
    perspective: str = "DIRECT",
) -> pd.DataFrame:
    """Compute economic impacts using USEEIOR state models.

    This is the recommended approach:
    1. Build USEEIOR two-region models (integrates StateIO)
    2. Format shocks as demand vectors
    3. Calculate impacts per state
    4. Extract economic components

    Args:
        useeior_pkg: USEEIOR R package object
        stateio_pkg: StateIO R package object (for value added extraction)
        shocks_df: DataFrame with state, bea_sector, fiscal_year, shock_amount
        modelname: USEEIOR model specification name
        year: Year for models (defaults to fiscal_year from shocks)
        perspective: "DIRECT" or "FINAL"

    Returns:
        DataFrame with impact components
    """
    if year is None:
        year = int(shocks_df["fiscal_year"].iloc[0])

    # Group shocks by state
    states = shocks_df["state"].unique()

    all_results = []

    for state in states:
        state_shocks = shocks_df[shocks_df["state"] == state].copy()

        try:
            # Build or get state model
            # For efficiency, could cache models
            logger.info(f"Building USEEIOR model for state: {state}")

            # Option 1: Build models for all states (may be expensive)
            # state_models = build_useeior_state_models(useeior_pkg, modelname, year)
            # state_model = state_models.rx2(state)

            # Option 2: Build single state model using StateIO (if available)
            # state_io_model = build_state_model(stateio_pkg, state, year)
            # Then convert to USEEIOR format or use directly

            # For now, try to use USEEIOR's buildTwoRegionModels and get state
            state_models = build_useeior_state_models(useeior_pkg, modelname, year)
            state_model = state_models.rx2(state)

            # Format shocks as demand vector
            demand = format_demand_vector_from_shocks(useeior_pkg, state_model, state_shocks)

            # Calculate impacts
            impacts = calculate_impacts_with_useeior(
                useeior_pkg,
                state_model,
                demand,
                perspective=perspective,
                location=state,
            )

            # Extract economic components
            # This requires the converter from adapter
            # For now, return basic structure
            logger.info(f"Computed impacts for {state}")

            # Get value added components from StateIO
            va_components = get_state_value_added(stateio_pkg, state, year)

            # TODO: Integrate value added components with impact calculations

            all_results.append(
                {
                    "state": state,
                    "impacts": impacts,
                    "va_components": va_components,
                }
            )

        except Exception as e:
            logger.error(f"Failed to compute impacts for {state}: {e}")
            continue

    # Convert results to DataFrame
    # This will be completed when we understand the exact result structure
    return pd.DataFrame(all_results)


def extract_use_table_from_model(
    model: Any,
    converter: Any | None = None,
) -> pd.DataFrame | None:
    """Extract Use table from StateIO model.

    Args:
        model: StateIO model object from buildFullTwoRegionIOTable()
        converter: Optional pandas2ri converter

    Returns:
        Use table as pandas DataFrame, or None if extraction fails
    """
    if not RPY2_AVAILABLE:
        logger.warning("rpy2 not available, cannot extract Use table")
        return None

    if model is None:
        return None

    try:
        # StateIO model is an R list with named components
        # Try to extract Use table (typically named "DomesticUseTransactions" or "UseTransactions")
        use_table = None

        # Try different possible names for the Use table
        possible_names = ["DomesticUseTransactions", "UseTransactions", "DomesticUse", "Use"]

        for name in possible_names:
            try:
                use_table = model.rx2(name)
                if use_table is not None:
                    logger.debug(f"Found Use table with name: {name}")
                    break
            except Exception:
                continue

        if use_table is None:
            logger.warning("Could not find Use table in StateIO model")
            return None

        # Convert to pandas DataFrame
        if converter is not None:
            from rpy2.robjects.conversion import localconverter

            with localconverter(ro.default_converter + converter):
                use_df = ro.conversion.rpy2py(use_table)
        else:
            from rpy2.robjects import pandas2ri

            use_df = pandas2ri.rpy2py(use_table)

        if not isinstance(use_df, pd.DataFrame):
            logger.warning(f"Use table converted to {type(use_df)}, not DataFrame")
            return None

        logger.debug(f"Extracted Use table with shape: {use_df.shape}")
        return use_df

    except Exception as e:
        logger.warning(f"Failed to extract Use table: {e}")
        return None


def extract_industry_output_from_model(
    model: Any,
    converter: Any | None = None,
) -> pd.Series | None:
    """Extract industry output vector from StateIO model.

    Args:
        model: StateIO model object
        converter: Optional pandas2ri converter

    Returns:
        Industry output as pandas Series, or None if extraction fails
    """
    if not RPY2_AVAILABLE:
        return None

    if model is None:
        return None

    try:
        # Try to extract industry output
        output = None
        possible_names = ["IndustryOutput", "Output", "x"]

        for name in possible_names:
            try:
                output = model.rx2(name)
                if output is not None:
                    logger.debug(f"Found industry output with name: {name}")
                    break
            except Exception:
                continue

        if output is None:
            logger.warning("Could not find industry output in model")
            return None

        # Convert to pandas Series
        if converter is not None:
            from rpy2.robjects.conversion import localconverter

            with localconverter(ro.default_converter + converter):
                output_series = ro.conversion.rpy2py(output)
        else:
            from rpy2.robjects import pandas2ri

            output_series = pandas2ri.rpy2py(output)

        # Ensure it's a Series
        if isinstance(output_series, pd.DataFrame):
            output_series = output_series.iloc[:, 0]
        elif not isinstance(output_series, pd.Series):
            output_series = pd.Series(output_series)

        return output_series

    except Exception as e:
        logger.warning(f"Failed to extract industry output: {e}")
        return None


def calculate_technical_coefficients(
    use_table: pd.DataFrame,
    industry_output: pd.Series,
) -> pd.DataFrame:
    """Calculate technical coefficients matrix from Use table.

    The technical coefficients matrix A is calculated as:
    A[i,j] = Use[i,j] / Output[j]

    Where A[i,j] represents the amount of commodity i needed to produce one unit of industry j.

    Args:
        use_table: Use table (commodities x industries)
        industry_output: Industry output vector

    Returns:
        Technical coefficients matrix A

    Raises:
        ValueError: If dimensions don't match or output contains zeros
    """
    if use_table.shape[1] != len(industry_output):
        raise ValueError(
            f"Use table columns ({use_table.shape[1]}) must match "
            f"industry output length ({len(industry_output)})"
        )

    # Avoid division by zero
    # Replace zero outputs with small epsilon
    output_safe = industry_output.copy()
    output_safe[output_safe == 0] = 1e-10

    # Calculate technical coefficients: A[i,j] = Use[i,j] / Output[j]
    # Divide each column by corresponding output
    tech_coeff = use_table.div(output_safe, axis=1)

    # Replace any infinities or NaNs with zeros
    tech_coeff = tech_coeff.replace([float("inf"), float("-inf")], 0).fillna(0)

    logger.debug(f"Calculated technical coefficients matrix with shape: {tech_coeff.shape}")

    return tech_coeff


def calculate_leontief_inverse(
    tech_coeff: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate Leontief inverse matrix from technical coefficients.

    The Leontief inverse L is calculated as:
    L = (I - A)^(-1)

    Where:
    - I is the identity matrix
    - A is the technical coefficients matrix
    - L represents the total (direct + indirect) requirements per unit of final demand

    Args:
        tech_coeff: Technical coefficients matrix A

    Returns:
        Leontief inverse matrix L

    Raises:
        ValueError: If matrix is singular and cannot be inverted
    """
    try:
        import numpy as np

        # Create identity matrix
        identity = np.eye(tech_coeff.shape[0])

        # Calculate (I - A)
        i_minus_a = identity - tech_coeff.values

        # Compute inverse
        leontief_inv = np.linalg.inv(i_minus_a)

        # Convert back to DataFrame with same index/columns
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
    """Apply demand shocks using Leontief inverse to calculate production impacts.

    Computes: production = L * demand

    Where:
    - L is the Leontief inverse matrix
    - demand is the shock vector
    - production is the resulting production impact vector

    Args:
        leontief_inv: Leontief inverse matrix
        shocks_df: DataFrame with sector codes and shock amounts
        sector_col: Column name for sector codes
        amount_col: Column name for shock amounts

    Returns:
        Production impact by sector as pandas Series
    """
    try:
        # Create demand vector aligned with Leontief matrix
        demand_vector = pd.Series(0.0, index=leontief_inv.columns)

        # Fill in shock amounts for specified sectors
        for _, row in shocks_df.iterrows():
            sector = str(row[sector_col])
            amount = float(row[amount_col])

            if sector in demand_vector.index:
                demand_vector[sector] += amount
            else:
                logger.warning(f"Sector {sector} not found in Leontief matrix, skipping")

        # Apply Leontief inverse: production = L * demand
        production = leontief_inv.dot(demand_vector)

        logger.debug(
            f"Applied shocks to {len(shocks_df)} sectors, "
            f"got production for {len(production)} sectors"
        )

        return production

    except Exception as e:
        logger.error(f"Failed to apply demand shocks: {e}")
        raise


def get_state_employment_data(
    stateio_pkg: Any,
    state: str,
    year: int,
    specs: dict[str, Any] | None = None,
) -> pd.DataFrame | None:
    """Get state employment data by sector from StateIO.

    Args:
        stateio_pkg: StateIO R package object
        state: Two-letter state code
        year: Year for the data
        specs: Model specifications

    Returns:
        DataFrame with employment by sector, or None if unavailable
    """
    if not RPY2_AVAILABLE:
        logger.warning("rpy2 not available, cannot get employment data")
        return None

    if specs is None:
        specs = {"BaseIOSchema": "2017"}

    r_specs = ro.ListVector(specs)

    try:
        # Try to get employment data
        # StateIO may have getStateEmployment or similar function
        employment = call_r_function(
            stateio_pkg,
            "getStateEmployment",
            state=state,
            year=year,
            specs=r_specs,
        )

        # Convert to DataFrame
        employment_df = convert_r_gva_to_dataframe(employment)

        if employment_df is not None:
            logger.debug(f"Retrieved employment data for {state}: {employment_df.shape}")
            return employment_df

    except RFunctionError as e:
        logger.debug(f"Could not get employment data for {state}: {e}")

    return None


def calculate_employment_coefficients(
    employment_data: pd.DataFrame | None,
    industry_output: pd.Series,
) -> pd.DataFrame:
    """Calculate employment coefficients (jobs per dollar of output).

    Args:
        employment_data: Employment by sector (from getStateEmployment)
        industry_output: Industry output by sector

    Returns:
        DataFrame with columns:
        - sector: BEA sector code
        - employment: Employment count
        - employment_coefficient: Jobs per million dollars of output
    """
    if employment_data is None or employment_data.empty:
        logger.debug("No employment data available, returning empty DataFrame")
        return pd.DataFrame()

    try:
        coefficients = []

        # Assume employment_data has sectors in index or column
        if hasattr(employment_data, "index"):
            sectors = employment_data.index
        elif "sector" in employment_data.columns:
            sectors = employment_data["sector"]
        else:
            logger.warning("Cannot identify sectors in employment data")
            return pd.DataFrame()

        for sector in sectors:
            try:
                # Extract employment count
                emp_val = _extract_sector_value(employment_data, sector)

                # Get corresponding output
                if sector in industry_output.index:
                    output_val = float(industry_output[sector])

                    # Calculate coefficient: jobs per million dollars
                    if output_val > 0:
                        coeff = (emp_val / output_val) * 1_000_000

                        coefficients.append(
                            {
                                "sector": str(sector),
                                "employment": emp_val,
                                "employment_coefficient": coeff,
                            }
                        )
            except Exception as e:
                logger.debug(f"Could not calculate employment coefficient for {sector}: {e}")
                continue

        return pd.DataFrame(coefficients)

    except Exception as e:
        logger.warning(f"Failed to calculate employment coefficients: {e}")
        return pd.DataFrame()


def calculate_employment_from_production(
    production_by_sector: pd.Series,
    employment_coefficients: pd.DataFrame,
) -> pd.Series:
    """Calculate jobs created from production impacts.

    Args:
        production_by_sector: Production impact by sector (in dollars)
        employment_coefficients: Employment coefficients by sector

    Returns:
        Jobs created by sector
    """
    if employment_coefficients.empty:
        logger.debug("No employment coefficients, using default multiplier")
        # Fallback: rough estimate of 10 jobs per $1M output
        return production_by_sector / 100_000

    try:
        jobs_by_sector = pd.Series(0.0, index=production_by_sector.index)

        for sector in production_by_sector.index:
            production_val = production_by_sector[sector]

            # Look up employment coefficient
            sector_coeff = employment_coefficients[employment_coefficients["sector"] == str(sector)]

            if not sector_coeff.empty:
                coeff = sector_coeff["employment_coefficient"].iloc[0]
                # Jobs = (production in dollars / 1,000,000) * jobs_per_million
                jobs = (production_val / 1_000_000) * coeff
                jobs_by_sector[sector] = jobs
            else:
                # Fallback to default multiplier
                jobs_by_sector[sector] = production_val / 100_000

        return jobs_by_sector

    except Exception as e:
        logger.error(f"Failed to calculate employment: {e}")
        # Return fallback estimate
        return production_by_sector / 100_000
