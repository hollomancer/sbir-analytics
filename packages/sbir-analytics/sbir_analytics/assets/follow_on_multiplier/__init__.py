"""Pure follow-on funding multiplier analysis and production-input adapters.

Epistemic tier: exploratory. The calculator is deterministic, but which
obligations count as follow-on is a contestable attribution policy, so
multiplier readouts are non-citable.

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


EPISTEMIC_TIER = "exploratory"

__all__ = [
    "FollowOnMultiplierPolicy",
    "FollowOnMultiplierResult",
    "NASEM_DOD_BENCHMARK",
    "build_canonical_obligations",
    "calculate_follow_on_multipliers",
    "reconcile_nasem",
    "reconciliation_markdown",
]
