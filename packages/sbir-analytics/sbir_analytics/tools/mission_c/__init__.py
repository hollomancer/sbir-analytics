"""
Mission C: Fiscal Return Estimate tools.

Build last. Consumes everything from Phase 0, Mission A, and Mission B.
Adds only the economic modeling layer: BEA crosswalk, BEA I-O multipliers,
and tax estimation.

New tools (1 + 2 wrappers):
- tax_estimation: Federal tax receipt estimation from economic components
- naics_to_bea_crosswalk: NAICS → BEA sector mapping (wrapper)
- stateio_multipliers: BEA I-O economic multipliers (wrapper)
"""

from .naics_to_bea_crosswalk import NAICSToBEACrosswalkTool
from .stateio_multipliers import StateIOMultipliersTool
from .tax_estimation import TaxEstimationTool

__all__ = [
    "TaxEstimationTool",
    "NAICSToBEACrosswalkTool",
    "StateIOMultipliersTool",
]
