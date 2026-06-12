"""Pure leverage-ratio analysis and production-input adapters.

Dagster wiring lives in :mod:`sbir_analytics.assets.leverage_ratio.asset` so importing the
pure calculator does not require orchestration dependencies.
"""

from .analysis import LeverageRatioPolicy, LeverageRatioResult, calculate_leverage_ratios
from .integration import build_canonical_obligations
from .reconcile import NASEM_DOD_BENCHMARK, reconcile_nasem, reconciliation_markdown

__all__ = [
    "LeverageRatioPolicy",
    "LeverageRatioResult",
    "NASEM_DOD_BENCHMARK",
    "build_canonical_obligations",
    "calculate_leverage_ratios",
    "reconcile_nasem",
    "reconciliation_markdown",
]
