from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    LIKELY = "likely"
    POSSIBLE = "possible"


class CompetitionType(str, Enum):
    SOLE_SOURCE = "sole_source"
    LIMITED = "limited"
    FULL_AND_OPEN = "full_and_open"
    OTHER = "other"


class AgencySignal(BaseModel):
    """Evidence that a transition is connected to agency continuity / similarity."""

    same_agency: bool = Field(
        ...,
        description="True if the contract/award are with the same agency (highly indicative).",
    )
    same_department: bool | None = Field(
        None, description="True if the contract/award are within the same department (less strict)."
    )
    agency_score: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Normalized contribution to transition likelihood from agency continuity.",
    )


class TimingSignal(BaseModel):
    """Timing relationship between award completion and contract start that indicates likelihood."""

    days_between_award_and_contract: int | None = Field(
        None,
        description="Number of days between award completion and contract start (signed or effective date).",
    )
    months_between_award_and_contract: float | None = Field(
        None, description="Approximate months between award completion and contract start."
    )
    timing_score: float = Field(
        0.0, ge=0.0, le=1.0, description="Normalized timing contribution (closer -> higher)."
    )


class CompetitionSignal(BaseModel):
    """Signals derived from the contract competition type."""

    competition_type: CompetitionType = Field(
        CompetitionType.OTHER, description="Type of procurement competition for this contract."
    )
    competition_score: float = Field(
        0.0, ge=0.0, le=1.0, description="Normalized contribution based on competition type."
    )


class PatentSignal(BaseModel):
    """Patent-related signals used to support technology transition hypotheses."""

    patent_count: int = Field(
        0, ge=0, description="Number of related patents found for the vendor."
    )
    patents_pre_contract: int = Field(
        0,
        ge=0,
        description="Number of patents filed before the contract start date (supportive signal).",
    )
    patent_topic_similarity: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Similarity between patent text/topics and award/contract topic (0-1).",
    )
    patent_score: float = Field(
        0.0, ge=0.0, le=1.0, description="Normalized contribution coming from patent evidence."
    )


class CETSignal(BaseModel):
    """CET (technology area) alignment between award & contract."""

    award_cet: str | None = Field(None, description="CET area identifier for the award.")
    contract_cet: str | None = Field(None, description="Inferred CET area for the contract.")
    cet_alignment_score: float = Field(
        0.0, ge=0.0, le=1.0, description="Score indicating CET area alignment (1.0 = exact match)."
    )


class TransitionSignals(BaseModel):
    """Aggregate container of the different signal categories."""

    agency: AgencySignal | None = None
    timing: TimingSignal | None = None
    competition: CompetitionSignal | None = None
    patent: PatentSignal | None = None
    cet: CETSignal | None = None
    text_similarity_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Optional text similarity measure between award and contract descriptions.",
    )

    @field_validator("text_similarity_score")
    @classmethod
    def check_text_similarity(cls, v):
        if v is None:
            return v
        if not (0.0 <= v <= 1.0):
            raise ValueError("text_similarity_score must be between 0.0 and 1.0")
        return v


class EvidenceItem(BaseModel):
    """One piece of evidence that contributes to the detection."""

    source: str = Field(
        ..., description="Source system or provider (e.g., 'usaspending', 'patentsview')."
    )
    signal: str = Field(
        ..., description="Signal type (e.g., 'agency', 'timing', 'patent', 'cet', 'text')."
    )
    snippet: str | None = Field(None, description="Textual excerpt that supports the signal.")
    citation: str | None = Field(None, description="URL or canonical citation for the snippet.")
    score: float | None = Field(
        None, ge=0.0, le=1.0, description="Normalized score for this evidence item."
    )
    metadata: dict[str, object] = Field(
        default_factory=dict, description="Arbitrary structured metadata."
    )


class EvidenceBundle(BaseModel):
    """Comprehensive audit trail for a detection result."""

    items: list[EvidenceItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    summary: str | None = Field(None, description="Human-readable short summary of the bundle.")

    def add_item(self, item: EvidenceItem) -> None:
        self.items.append(item)

    def total_score(self) -> float:
        # Compute a simple aggregated score if item scores available (mean of present scores)
        scores = [i.score for i in self.items if i.score is not None]
        if not scores:
            return 0.0
        return float(sum(scores) / len(scores))


class VendorMatch(BaseModel):
    """Result of vendor/company resolution for a contract."""

    vendor_id: str | None = Field(
        None, description="Canonical vendor ID (e.g., company node id or UEI)."
    )
    method: str = Field(
        ..., description="How the match was determined ('uei', 'cage', 'duns', 'name_fuzzy', ...)."
    )
    score: float = Field(0.0, ge=0.0, le=1.0, description="Confidence score for the vendor match.")
    matched_name: str | None = Field(None, description="Matched vendor canonical name.")
    metadata: dict[str, object] = Field(default_factory=dict)


class FederalContract(BaseModel):
    """Model capturing the contract information relevant for transition detection."""

    contract_id: str = Field(..., description="Contract identifier (e.g., PIID).")
    agency: str | None = Field(None, description="Agency code or name (e.g., 'DOD', 'NASA').")
    sub_agency: str | None = Field(None, description="Sub-agency or office.")
    vendor_name: str | None = Field(None, description="Vendor name string as present on contract.")
    vendor_uei: str | None = Field(None, description="Vendor UEI if available.")
    vendor_cage: str | None = Field(None, description="Vendor CAGE code if available.")
    vendor_duns: str | None = Field(None, description="Vendor DUNS if available (legacy).")
    start_date: date | None = Field(None, description="Contract start/award effective date.")
    end_date: date | None = Field(None, description="Contract end date (if present).")
    obligation_amount: float | None = Field(
        None, ge=0.0, description="Contract obligation/award amount."
    )
    competition_type: CompetitionType | None = Field(
        None, description="Competition type for the award."
    )
    description: str | None = Field(None, description="Free-text contract description.")
    matched_vendor: VendorMatch | None = Field(
        None, description="Vendor match result to canonical entity."
    )
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def parse_dates(cls, v):
        if v is None:
            return None
        if isinstance(v, date | datetime):
            return v.date() if isinstance(v, datetime) else v
        # attempt ISO parse
        try:
            return date.fromisoformat(str(v))
        except Exception:
            raise ValueError("Dates must be ISO-formatted strings or date objects")


class Transition(BaseModel):
    """High-level transition detection result tied to an award and (candidate) contract(s)."""

    transition_id: str = Field(..., description="Unique transition detection id.")
    award_id: str | None = Field(
        None, description="Canonical award id associated with the detection."
    )
    detected_at: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp when detection was created."
    )
    likelihood_score: float = Field(
        ..., ge=0.0, le=1.0, description="Composite likelihood score for this detection."
    )
    confidence: ConfidenceLevel = Field(
        ..., description="Categorical confidence derived from thresholds."
    )
    primary_contract: FederalContract | None = Field(
        None, description="Primary contract candidate associated with this detection (if any)."
    )
    signals: TransitionSignals | None = Field(
        None, description="Detailed per-signal contributions."
    )
    evidence: EvidenceBundle | None = Field(
        None, description="Evidence bundle documenting the detection."
    )
    metadata: dict[str, object] = Field(
        default_factory=dict, description="Additional, implementation-specific metadata."
    )

    @field_validator("likelihood_score")
    @classmethod
    def validate_score(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError("likelihood_score must be between 0.0 and 1.0")
        return float(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def derive_confidence(cls, v, info):
        # If confidence provided, validate; otherwise derive from likelihood_score if available in data
        if v is None:
            # cannot derive without context; the caller should set confidence
            return v
        # pydantic will coerce to Enum automatically if possible
        return v


class TransitionProfile(BaseModel):
    """Aggregated, company-level transition profile."""

    company_id: str = Field(..., description="Canonical company identifier (node id or UEI).")
    total_awards: int = Field(0, ge=0, description="Number of awards considered for this profile.")
    total_transitions: int = Field(
        0, ge=0, description="Total detected transitions for the company."
    )
    success_rate: float = Field(
        0.0, ge=0.0, le=1.0, description="Fraction of awards that transitioned."
    )
    avg_likelihood_score: float = Field(
        0.0, ge=0.0, le=1.0, description="Average likelihood across detections."
    )
    avg_time_to_transition_days: float | None = Field(
        None,
        ge=0.0,
        description="Average time in days from award completion to contract start for transitions.",
    )
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("success_rate", "avg_likelihood_score")
    @classmethod
    def validate_ratios(cls, v):
        if v is None:
            return v
        if not (0.0 <= v <= 1.0):
            raise ValueError("ratios must be between 0.0 and 1.0")
        return float(v)

    @property
    def to_summary(self) -> dict[str, object]:
        return {
            "company_id": self.company_id,
            "total_awards": self.total_awards,
            "total_transitions": self.total_transitions,
            "success_rate": round(self.success_rate, 4),
            "avg_likelihood_score": round(self.avg_likelihood_score, 4)
            if self.avg_likelihood_score is not None
            else None,
            "avg_time_to_transition_days": self.avg_time_to_transition_days,
            "last_updated": self.last_updated.isoformat(),
        }


__all__ = [
    "ConfidenceLevel",
    "CompetitionType",
    "AgencySignal",
    "TimingSignal",
    "CompetitionSignal",
    "PatentSignal",
    "CETSignal",
    "TransitionSignals",
    "EvidenceItem",
    "EvidenceBundle",
    "VendorMatch",
    "FederalContract",
    "Transition",
    "TransitionProfile",
]
