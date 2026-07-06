from datetime import date

from pydantic import BaseModel, Field, model_validator


def _confidence_tier(score: float) -> str:
    """Map a numeric confidence_score to the low/medium/high tier used downstream.

    Matches the {"high", "medium"} keep-set in
    sbir_etl/capital_events/sources/ma_events.py.
    """
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


class MAEvent(BaseModel):
    """Represents a potential Merger & Acquisition (M&A) event."""

    acquiring_company_name: str = Field(description="The name of the acquiring company.")
    acquired_company_name: str = Field(description="The name of the acquired company.")
    acquisition_date: date = Field(description="The date of the acquisition event.")
    source: str = Field(description="The source of the M&A event information.")
    confidence_score: float = Field(
        description="A numerical score (0.0-1.0) indicating confidence in the event."
    )
    confidence: str | None = Field(
        default=None,
        description="Categorical confidence tier (low, medium, high). "
        "Derived from confidence_score when not supplied explicitly.",
    )

    @model_validator(mode="after")
    def _fill_confidence(self) -> "MAEvent":
        if self.confidence is None:
            self.confidence = _confidence_tier(self.confidence_score)
        return self
