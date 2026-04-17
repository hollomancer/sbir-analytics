"""Data models for SBIR/STTR benchmark eligibility evaluation.

Implements the statutory performance benchmarks established by the SBIR/STTR
Reauthorization Act and the SBIR/STTR Extension Act of 2022 (Pub. L. 117-183):

1. Phase I to Phase II Transition Rate Benchmark
   - Standard: ≥21 Phase I awards in 5-FY window → ≥0.25 ratio required
   - Increased (experienced firms): ≥51 Phase I awards → ≥0.50 ratio required

2. Commercialization Rate Benchmark
   - Standard: ≥16 Phase II awards in 10-FY window → ≥$100K avg sales/investment
     per Phase II OR ≥15% patents per Phase II
   - Increased Tier 1: ≥51 Phase II awards → ≥$250K avg, no patent path
   - Increased Tier 2: ≥101 Phase II awards → ≥$450K avg, no patent path

SBA evaluates benchmarks annually on June 1.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BenchmarkTier(str, Enum):
    """Tier of benchmark applicability."""

    NOT_SUBJECT = "not_subject"
    STANDARD = "standard"
    INCREASED_TIER1 = "increased_tier1"
    INCREASED_TIER2 = "increased_tier2"


class BenchmarkStatus(str, Enum):
    """Whether a company passes or fails a benchmark."""

    PASS = "pass"  # nosec B105 - enum value, not a credential
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class ConsequenceType(str, Enum):
    """Consequence of failing a benchmark."""

    NONE = "none"
    PHASE1_INELIGIBLE_1YR = "phase1_ineligible_1yr"
    CAPPED_20_AWARDS_PER_AGENCY = "capped_20_awards_per_agency"


def consequence_for_tier(tier: BenchmarkTier) -> ConsequenceType:
    """Return the statutory consequence for failing a benchmark at the given tier."""
    if tier == BenchmarkTier.STANDARD:
        return ConsequenceType.PHASE1_INELIGIBLE_1YR
    return ConsequenceType.CAPPED_20_AWARDS_PER_AGENCY


def _dataclass_to_dict(obj: Any) -> dict[str, Any]:
    """Convert a dataclass to dict, serializing enums to their .value."""
    result = {}
    for f in dataclasses.fields(obj):
        val = getattr(obj, f.name)
        if isinstance(val, Enum):
            val = val.value
        result[f.name] = val
    return result


@dataclass
class TransitionRateThresholds:
    """Thresholds for the Phase I→II transition rate benchmark."""

    lookback_years: int = 5
    phase1_exclude_recent_years: int = 1   # Exclude most recently completed FY
    phase2_exclude_recent_years: int = 0   # Phase II count includes most recent FY
    standard_min_phase1: int = 21
    standard_min_ratio: float = 0.25
    increased_min_phase1: int = 51
    increased_min_ratio: float = 0.50


@dataclass
class CommercializationRateThresholds:
    """Thresholds for the commercialization rate benchmark."""

    lookback_years: int = 10
    exclude_recent_years: int = 2          # Exclude 2 most recently completed FYs
    standard_min_phase2: int = 16
    standard_min_avg_sales: float = 100_000.0
    standard_min_patent_rate: float = 0.15  # Patents path only for standard tier
    increased_tier1_min_phase2: int = 51
    increased_tier1_min_avg_sales: float = 250_000.0
    increased_tier2_min_phase2: int = 101
    increased_tier2_min_avg_sales: float = 450_000.0


@dataclass
class FiscalYearWindow:
    """Defines the fiscal year range for a benchmark evaluation."""

    evaluation_fy: int
    start_fy: int
    end_fy: int
    exclude_recent_years: int

    @property
    def span(self) -> int:
        return self.end_fy - self.start_fy + 1

    def contains(self, fy: int) -> bool:
        return self.start_fy <= fy <= self.end_fy


@dataclass
class CompanyAwardCounts:
    """Award counts for a single company used in benchmark evaluation."""

    company_id: str
    company_name: str | None = None

    # Transition rate inputs
    phase1_count: int = 0
    phase2_count: int = 0

    # Commercialization rate inputs
    phase2_count_commercialization: int = 0
    total_sales_and_investment: float = 0.0
    patent_count: int = 0

    # Optional detail for debugging/reporting
    phase1_fiscal_years: list[int] = field(default_factory=list)
    phase2_fiscal_years: list[int] = field(default_factory=list)


@dataclass
class TransitionRateResult:
    """Result of evaluating the transition rate benchmark for one company."""

    company_id: str
    company_name: str | None
    tier: BenchmarkTier
    status: BenchmarkStatus
    consequence: ConsequenceType

    phase1_count: int
    phase2_count: int
    transition_ratio: float | None  # None if denominator is 0
    required_ratio: float | None  # None if not subject

    # Sensitivity fields
    phase1_awards_to_next_tier: int | None = None
    margin_from_threshold: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


@dataclass
class CommercializationRateResult:
    """Result of evaluating the commercialization rate benchmark for one company."""

    company_id: str
    company_name: str | None
    tier: BenchmarkTier
    status: BenchmarkStatus
    consequence: ConsequenceType

    phase2_count: int
    avg_sales_per_phase2: float | None
    patent_rate: float | None
    required_avg_sales: float | None
    required_patent_rate: float | None
    patents_path_available: bool

    # Sensitivity fields
    phase2_awards_to_next_tier: int | None = None
    margin_from_sales_threshold: float | None = None
    margin_from_patent_threshold: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


@dataclass
class SensitivityResult:
    """Sensitivity analysis for a company near benchmark thresholds."""

    company_id: str
    company_name: str | None

    # How close to becoming subject
    phase1_count: int
    phase1_to_standard_transition: int  # Awards needed to hit 21
    phase1_to_increased_transition: int  # Awards needed to hit 51
    phase2_count_for_commercialization: int
    phase2_to_standard_commercialization: int  # Awards needed to hit 16
    phase2_to_increased_tier1: int  # Awards needed to hit 51
    phase2_to_increased_tier2: int  # Awards needed to hit 101

    # If already subject, how close to failing
    transition_rate_margin: float | None = None
    commercialization_sales_margin: float | None = None
    commercialization_patent_margin: float | None = None

    # Risk categorization
    at_risk_transition: bool = False
    at_risk_commercialization: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _dataclass_to_dict(self)


@dataclass
class BenchmarkEvaluationSummary:
    """Full benchmark evaluation for a given fiscal year."""

    evaluation_fy: int
    determination_date: str  # e.g., "2025-06-01"

    transition_window: FiscalYearWindow
    transition_phase2_window: FiscalYearWindow
    commercialization_window: FiscalYearWindow

    total_companies_evaluated: int
    companies_subject_to_transition: int
    companies_subject_to_commercialization: int
    companies_failing_transition: int
    companies_failing_commercialization: int

    transition_results: list[TransitionRateResult] = field(default_factory=list)
    commercialization_results: list[CommercializationRateResult] = field(default_factory=list)
    sensitivity_results: list[SensitivityResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def _window(w: FiscalYearWindow) -> dict[str, int]:
            return {"start_fy": w.start_fy, "end_fy": w.end_fy}

        return {
            "evaluation_fy": self.evaluation_fy,
            "determination_date": self.determination_date,
            "transition_window": _window(self.transition_window),
            "transition_phase2_window": _window(self.transition_phase2_window),
            "commercialization_window": _window(self.commercialization_window),
            "total_companies_evaluated": self.total_companies_evaluated,
            "companies_subject_to_transition": self.companies_subject_to_transition,
            "companies_subject_to_commercialization": self.companies_subject_to_commercialization,
            "companies_failing_transition": self.companies_failing_transition,
            "companies_failing_commercialization": self.companies_failing_commercialization,
            "transition_results": [r.to_dict() for r in self.transition_results],
            "commercialization_results": [r.to_dict() for r in self.commercialization_results],
            "sensitivity_results": [r.to_dict() for r in self.sensitivity_results],
        }


__all__ = [
    "BenchmarkTier",
    "BenchmarkStatus",
    "ConsequenceType",
    "consequence_for_tier",
    "TransitionRateThresholds",
    "CommercializationRateThresholds",
    "FiscalYearWindow",
    "CompanyAwardCounts",
    "TransitionRateResult",
    "CommercializationRateResult",
    "SensitivityResult",
    "BenchmarkEvaluationSummary",
]
