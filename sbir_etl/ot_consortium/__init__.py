"""OT consortium Phase III verification-tiering module.

Classifies OT (Other Transaction) consortium-linked SBIR→federal-award
transitions, and firm-reported covered-sales claims, into honest *verification
tiers* and emits a magnitude report.

The federal record for consortium OTs is structurally incomplete (CMF rollup
attribution, modification-based invisibility, partial Consortia fields,
out-of-band truth in Agreements Officer files). This module does not try to
defeat that opacity — it measures it. T2/T3/T4 are first-class results, not
failures, and their union is reported as a first-class "unverifiable share".

See ``docs/ot-consortium/tiers.md`` for the full tier logic and assumptions.
"""

from __future__ import annotations

from .classifier import assign_tier
from .models import (
    UNVERIFIABLE_TIERS,
    CoveredSalesClaim,
    FirmUEISource,
    MagnitudeReport,
    OTAward,
    TierAssignment,
    TierBucket,
    TierEvidenceItem,
    VerificationTier,
)
from .registry import CMFRecord, CMFRegistry

__all__ = [
    "UNVERIFIABLE_TIERS",
    "CMFRecord",
    "CMFRegistry",
    "CoveredSalesClaim",
    "FirmUEISource",
    "MagnitudeReport",
    "OTAward",
    "TierAssignment",
    "TierBucket",
    "TierEvidenceItem",
    "VerificationTier",
    "assign_tier",
]
