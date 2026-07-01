"""Pure follow-on funding multiplier analysis and production-input adapters.

Dagster wiring lives in :mod:`sbir_analytics.assets.follow_on_multiplier.asset` so importing the
pure calculator does not require orchestration dependencies.
"""

from .analysis import (
    FollowOnMultiplierPolicy,
    FollowOnMultiplierResult,
    calculate_follow_on_multipliers,
)
from .integration import build_canonical_obligations
from .reconcile import NASEM_DOD_BENCHMARK, reconcile_nasem, reconciliation_markdown

__all__ = [
    "FollowOnMultiplierPolicy",
    "FollowOnMultiplierResult",
    "NASEM_DOD_BENCHMARK",
    "build_canonical_obligations",
    "calculate_follow_on_multipliers",
    "reconcile_nasem",
    "reconciliation_markdown",
]
