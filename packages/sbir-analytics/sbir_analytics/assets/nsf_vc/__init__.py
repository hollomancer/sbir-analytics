"""NSF SBIR vs. published-VC-baseline comparison (Phase 1).

Produces a descriptive comparison artifact: NSF SBIR cohort outcome rates
alongside published seed-VC / small-business-survival baselines, with a
reconciliation narrative attributing each delta. Mirrors the posture of
``specs/leverage-ratio-analysis``: reconciliation matters more than the
match.

Outputs:
    - ``data/processed/nsf_vc/nsf_cohort_outcomes.parquet``
    - ``data/processed/nsf_vc/nsf_vs_published_baselines.md``
    - ``data/processed/nsf_vc/nsf_baseline_comparison.json``
"""

from .asset import nsf_vc_published_baseline_comparison
from .baselines import PublishedBaseline, PublishedBaselineRegistry
from .cohort import NSFCohortBuilder, vintage_bucket
from .outcomes import OutcomeMetricsCalculator, wilson_interval
from .reconcile import ReconciliationNarrative, ReconciliationRecord


__all__ = [
    "NSFCohortBuilder",
    "OutcomeMetricsCalculator",
    "PublishedBaseline",
    "PublishedBaselineRegistry",
    "ReconciliationNarrative",
    "ReconciliationRecord",
    "nsf_vc_published_baseline_comparison",
    "vintage_bucket",
    "wilson_interval",
]
