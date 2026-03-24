from datetime import date

from pydantic import BaseModel, Field


class MAEvent(BaseModel):
    """Represents a potential Merger & Acquisition (M&A) event."""

    acquiring_company_name: str = Field(description="The name of the acquiring company.")
    acquired_company_name: str = Field(description="The name of the acquired company.")
    acquisition_date: date = Field(description="The date of the acquisition event.")
    source: str = Field(description="The source of the M&A event information.")
    confidence_score: float = Field(
        description="A score indicating the confidence in the M&A event."
    )
