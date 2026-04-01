"""Pydantic models for SBIR/STTR benchmark eligibility evaluation.

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

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BenchmarkType(str, Enum):
    """Type of SBIR/STTR performance benchmark."""

    TRANSITION_RATE = "transition_rate"
    COMMERCIALIZATION_RATE = "commercialization_rate"


class BenchmarkTier(str, Enum):
    """Tier of benchmark applicability."""

    NOT_SUBJECT = "not_subject"
    STANDARD = "standard"
    INCREASED_TIER1 = "increased_tier1"
    INCREASED_TIER2 = "increased_tier2"


class BenchmarkStatus(str, Enum):
    """Whether a company passes or fails a benchmark."""

    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class ConsequenceType(str, Enum):
    """Consequence of failing a benchmark."""

    NONE = "none"
    PHASE1_INELIGIBLE_1YR = "phase1_ineligible_1yr"
    CAPPED_20_AWARDS_PER_AGENCY = "capped_20_awards_per_agency"


# ─── Transition Rate Benchmark Constants ──────────────────────────────
TRANSITION_LOOKBACK_YEARS = 5
TRANSITION_PHASE1_EXCLUDE_RECENT_YEARS = 1  # Exclude most recently completed FY for Phase I count
TRANSITION_PHASE2_EXCLUDE_RECENT_YEARS = 0  # Phase II count includes most recent FY

TRANSITION_STANDARD_MIN_PHASE1 = 21
TRANSITION_STANDARD_MIN_RATIO = 0.25

TRANSITION_INCREASED_MIN_PHASE1 = 51
TRANSITION_INCREASED_MIN_RATIO = 0.50

# ─── Commercialization Rate Benchmark Constants ───────────────────────
COMMERCIALIZATION_LOOKBACK_YEARS = 10
COMMERCIALIZATION_EXCLUDE_RECENT_YEARS = 2  # Exclude 2 most recently completed FYs

COMMERCIALIZATION_STANDARD_MIN_PHASE2 = 16
COMMERCIALIZATION_STANDARD_MIN_AVG_SALES = 100_000.0  # $100K avg per Phase II
COMMERCIALIZATION_STANDARD_MIN_PATENT_RATE = 0.15  # 15% patents per Phase II

COMMERCIALIZATION_INCREASED_TIER1_MIN_PHASE2 = 51
COMMERCIALIZATION_INCREASED_TIER1_MIN_AVG_SALES = 250_000.0  # $250K avg per Phase II
COMMERCIALIZATION_INCREASED_TIER2_MIN_PHASE2 = 101
COMMERCIALIZATION_INCREASED_TIER2_MIN_AVG_SALES = 450_000.0  # $450K avg per Phase II
# Patents path is NOT available for increased tiers


@dataclass
class TransitionRateThresholds:
    """Thresholds for the Phase I→II transition rate benchmark."""

    lookback_years: int = TRANSITION_LOOKBACK_YEARS
    phase1_exclude_recent_years: int = TRANSITION_PHASE1_EXCLUDE_RECENT_YEARS
    phase2_exclude_recent_years: int = TRANSITION_PHASE2_EXCLUDE_RECENT_YEARS
    standard_min_phase1: int = TRANSITION_STANDARD_MIN_PHASE1
    standard_min_ratio: float = TRANSITION_STANDARD_MIN_RATIO
    increased_min_phase1: int = TRANSITION_INCREASED_MIN_PHASE1
    increased_min_ratio: float = TRANSITION_INCREASED_MIN_RATIO


@dataclass
class CommercializationRateThresholds:
    """Thresholds for the commercialization rate benchmark."""

    lookback_years: int = COMMERCIALIZATION_LOOKBACK_YEARS
    exclude_recent_years: int = COMMERCIALIZATION_EXCLUDE_RECENT_YEARS
    standard_min_phase2: int = COMMERCIALIZATION_STANDARD_MIN_PHASE2
    standard_min_avg_sales: float = COMMERCIALIZATION_STANDARD_MIN_AVG_SALES
    standard_min_patent_rate: float = COMMERCIALIZATION_STANDARD_MIN_PATENT_RATE
    increased_tier1_min_phase2: int = COMMERCIALIZATION_INCREASED_TIER1_MIN_PHASE2
    increased_tier1_min_avg_sales: float = COMMERCIALIZATION_INCREASED_TIER1_MIN_AVG_SALES
    increased_tier2_min_phase2: int = COMMERCIALIZATION_INCREASED_TIER2_MIN_PHASE2
    increased_tier2_min_avg_sales: float = COMMERCIALIZATION_INCREASED_TIER2_MIN_AVG_SALES


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
        return {
            "company_id": self.company_id,
            "company_name": self.company_name,
            "tier": self.tier.value,
            "status": self.status.value,
            "consequence": self.consequence.value,
            "phase1_count": self.phase1_count,
            "phase2_count": self.phase2_count,
            "transition_ratio": self.transition_ratio,
            "required_ratio": self.required_ratio,
            "phase1_awards_to_next_tier": self.phase1_awards_to_next_tier,
            "margin_from_threshold": self.margin_from_threshold,
        }


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
        return {
            "company_id": self.company_id,
            "company_name": self.company_name,
            "tier": self.tier.value,
            "status": self.status.value,
            "consequence": self.consequence.value,
            "phase2_count": self.phase2_count,
            "avg_sales_per_phase2": self.avg_sales_per_phase2,
            "patent_rate": self.patent_rate,
            "required_avg_sales": self.required_avg_sales,
            "required_patent_rate": self.required_patent_rate,
            "patents_path_available": self.patents_path_available,
            "phase2_awards_to_next_tier": self.phase2_awards_to_next_tier,
            "margin_from_sales_threshold": self.margin_from_sales_threshold,
            "margin_from_patent_threshold": self.margin_from_patent_threshold,
        }


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
        return {
            "company_id": self.company_id,
            "company_name": self.company_name,
            "phase1_count": self.phase1_count,
            "phase1_to_standard_transition": self.phase1_to_standard_transition,
            "phase1_to_increased_transition": self.phase1_to_increased_transition,
            "phase2_count_for_commercialization": self.phase2_count_for_commercialization,
            "phase2_to_standard_commercialization": self.phase2_to_standard_commercialization,
            "phase2_to_increased_tier1": self.phase2_to_increased_tier1,
            "phase2_to_increased_tier2": self.phase2_to_increased_tier2,
            "transition_rate_margin": self.transition_rate_margin,
            "commercialization_sales_margin": self.commercialization_sales_margin,
            "commercialization_patent_margin": self.commercialization_patent_margin,
            "at_risk_transition": self.at_risk_transition,
            "at_risk_commercialization": self.at_risk_commercialization,
        }


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
        return {
            "evaluation_fy": self.evaluation_fy,
            "determination_date": self.determination_date,
            "transition_window": {
                "start_fy": self.transition_window.start_fy,
                "end_fy": self.transition_window.end_fy,
            },
            "transition_phase2_window": {
                "start_fy": self.transition_phase2_window.start_fy,
                "end_fy": self.transition_phase2_window.end_fy,
            },
            "commercialization_window": {
                "start_fy": self.commercialization_window.start_fy,
                "end_fy": self.commercialization_window.end_fy,
            },
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
    "BenchmarkType",
    "BenchmarkTier",
    "BenchmarkStatus",
    "ConsequenceType",
    "TransitionRateThresholds",
    "CommercializationRateThresholds",
    "FiscalYearWindow",
    "CompanyAwardCounts",
    "TransitionRateResult",
    "CommercializationRateResult",
    "SensitivityResult",
    "BenchmarkEvaluationSummary",
]
