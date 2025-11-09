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
