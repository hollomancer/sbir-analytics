"""Normalized public SAM.gov contract-opportunity records."""

from datetime import UTC, date, datetime

from pydantic import BaseModel, ConfigDict, Field


class OpportunityContact(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    contact_type: str | None = None
    name: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None


class Opportunity(BaseModel):
    """Stable row contract for the SAM.gov Opportunities public API."""

    model_config = ConfigDict(str_strip_whitespace=True)

    notice_id: str
    notice_type: str
    notice_type_code: str | None = None
    base_notice_type: str | None = None
    solicitation_number: str | None = None
    title: str
    description: str | None = None
    active: bool = False
    status: str | None = None
    posted_date: date | None = None
    response_deadline: datetime | None = None
    archive_date: date | None = None
    agency: str | None = None
    agency_code: str | None = None
    sub_tier: str | None = None
    sub_tier_code: str | None = None
    office: str | None = None
    office_code: str | None = None
    full_parent_path_name: str | None = None
    full_parent_path_code: str | None = None
    naics_code: str | None = None
    classification_code: str | None = None
    psc_code: str | None = None
    set_aside_code: str | None = None
    set_aside_description: str | None = None
    awardee_uei: str | None = None
    awardee_name: str | None = None
    contacts: list[OpportunityContact] = Field(default_factory=list)
    description_url: str | None = None
    ui_url: str | None = None
    additional_info_url: str | None = None
    resource_urls: list[str] = Field(default_factory=list)
    source_url: str | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content_hash: str


__all__ = ["Opportunity", "OpportunityContact"]
