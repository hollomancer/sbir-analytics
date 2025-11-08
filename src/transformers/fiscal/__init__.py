"""
Fiscal transformers package for SBIR economic returns analysis.

This package contains modularized fiscal analysis transformers for computing
economic impacts, tax receipts, and ROI metrics from SBIR program investments.

Module Structure:
- components: Economic component extraction and validation
- shocks: Economic shock aggregation for StateIO model input
- taxes: Federal tax estimation from economic components
- roi: Return on investment calculation with NPV and payback period
- sensitivity: Parameter sweep and uncertainty quantification

Pipeline Stages:
1. Components: Extract tax base components from economic impacts
2. Shocks: Aggregate awards into state-by-sector-by-fiscal-year shocks
3. Taxes: Estimate federal tax receipts from economic components
4. ROI: Calculate ROI metrics with temporal discounting
5. Sensitivity: Perform sensitivity analysis with uncertainty quantification

Exported Classes:
- FiscalComponentCalculator: Component extraction and validation
- FiscalShockAggregator: Award-to-shock aggregation
- FiscalTaxEstimator: Tax receipt estimation
- FiscalROICalculator: ROI metric calculation
- FiscalParameterSweep: Parameter sweep scenario generation
- FiscalUncertaintyQuantifier: Uncertainty quantification

Exported Functions:
- calculate_fiscal_year: Convert award date to government fiscal year
"""

from __future__ import annotations

# Components module
from .components import (
    ComponentValidationResult,
    FiscalComponentCalculator,
)

# Shocks module
from .shocks import (
    FiscalShockAggregator,
    ShockAggregationStats,
    calculate_fiscal_year,
)

# Taxes module
from .taxes import (
    FiscalTaxEstimator,
    TaxEstimationStats,
)

# ROI module
from .roi import (
    FiscalROICalculator,
    ROICalculationResult,
)

# Sensitivity module
from .sensitivity import (
    FiscalParameterSweep,
    FiscalUncertaintyQuantifier,
    ParameterRange,
    ParameterScenario,
    UncertaintyResult,
)


__all__ = [
    # Components
    "FiscalComponentCalculator",
    "ComponentValidationResult",
    # Shocks
    "FiscalShockAggregator",
    "ShockAggregationStats",
    "calculate_fiscal_year",
    # Taxes
    "FiscalTaxEstimator",
    "TaxEstimationStats",
    # ROI
    "FiscalROICalculator",
    "ROICalculationResult",
    # Sensitivity
    "FiscalParameterSweep",
    "FiscalUncertaintyQuantifier",
    "ParameterRange",
    "ParameterScenario",
    "UncertaintyResult",
]
