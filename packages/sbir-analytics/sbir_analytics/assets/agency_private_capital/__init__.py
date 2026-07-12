"""SBIR vs. private-capital comparisons (agency-parameterized).

Produces a descriptive comparison artifact: SBIR cohort outcome rates for
the configured funding agency alongside published seed-VC / small-business-
survival baselines, with a reconciliation narrative attributing each delta.
NSF is the initial implementation target and the default agency. Mirrors
the posture of ``specs/archive/completed-features/follow-on-multiplier-analysis``: reconciliation matters
more than the match.

Phase 1 outputs (under ``data/processed/agency_private_capital/<agency_lower>/``):
    - ``agency_cohort_outcomes.parquet``
    - ``agency_vs_published_baselines.md``
    - ``agency_baseline_comparison.json``

Phase 2 outputs:
    - ``agency_vs_form_d_comparison.parquet``
    - ``agency_vs_form_d_matched_pairs.parquet``
    - ``agency_vs_form_d_comparison.md``
    - ``threats_to_validity.json``
"""

from .asset import AgencyPrivateCapitalConfig, agency_private_capital_baseline_comparison
from .baselines import PublishedBaseline, PublishedBaselineRegistry
from .cohort import AgencyCohortBuilder, NSFCohortBuilder, vintage_bucket
from .control_cohort import (
    AgencyAwardeeFilter,
    PrivateCapitalControlCohortBuilder,
    agency_leverage_cross_check,
)
from .form_d_matched_asset import (
    AgencyPrivateCapitalPhase2Config,
    agency_private_capital_form_d_matched_comparison,
)
from .matching import CohortMatcher
from .outcomes import OutcomeMetricsCalculator, wilson_interval
from .phase2_outcomes import MatchedCohortOutcomes
from .reconcile import ReconciliationNarrative, ReconciliationRecord
from .threats import ThreatsToValidity


__all__ = [
    "AgencyCohortBuilder",
    "AgencyAwardeeFilter",
    "AgencyPrivateCapitalConfig",
    "AgencyPrivateCapitalPhase2Config",
    "CohortMatcher",
    "MatchedCohortOutcomes",
    "NSFCohortBuilder",
    "OutcomeMetricsCalculator",
    "PrivateCapitalControlCohortBuilder",
    "PublishedBaseline",
    "PublishedBaselineRegistry",
    "ReconciliationNarrative",
    "ReconciliationRecord",
    "ThreatsToValidity",
    "agency_leverage_cross_check",
    "agency_private_capital_baseline_comparison",
    "agency_private_capital_form_d_matched_comparison",
    "vintage_bucket",
    "wilson_interval",
]
