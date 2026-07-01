"""SBIR vs. published-VC-baseline comparison (agency-parameterized, Phase 1).

Produces a descriptive comparison artifact: SBIR cohort outcome rates for
the configured funding agency alongside published seed-VC / small-business-
survival baselines, with a reconciliation narrative attributing each delta.
NSF is the initial implementation target and the default agency. Mirrors
the posture of ``specs/follow-on-multiplier-analysis``: reconciliation matters
more than the match.

Outputs (under ``data/processed/agency_private_capital/<agency_lower>/``):
    - ``agency_cohort_outcomes.parquet``
    - ``agency_vs_published_baselines.md``
    - ``agency_baseline_comparison.json``
"""

from .asset import AgencyPrivateCapitalConfig, agency_private_capital_baseline_comparison
from .baselines import PublishedBaseline, PublishedBaselineRegistry
from .cohort import AgencyCohortBuilder, NSFCohortBuilder, vintage_bucket
from .outcomes import OutcomeMetricsCalculator, wilson_interval
from .reconcile import ReconciliationNarrative, ReconciliationRecord


__all__ = [
    "AgencyCohortBuilder",
    "AgencyPrivateCapitalConfig",
    "NSFCohortBuilder",
    "OutcomeMetricsCalculator",
    "PublishedBaseline",
    "PublishedBaselineRegistry",
    "ReconciliationNarrative",
    "ReconciliationRecord",
    "agency_private_capital_baseline_comparison",
    "vintage_bucket",
    "wilson_interval",
]
