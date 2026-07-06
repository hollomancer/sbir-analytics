"""Shared schema for capital-event timeline records."""

from enum import StrEnum
from typing import TypedDict


class EventType(StrEnum):
    SBIR_AWARD = "sbir_award"
    FORM_D_FILING = "form_d_filing"
    MA_EVENT = "ma_event"
    USASPENDING_CONTRACT = "usaspending_contract"
    PATENT_GRANT = "patent_grant"
    UCC_FILING = "ucc_filing"


class CapitalEvent(TypedDict):
    """One capital event for one firm, projected to the common schema."""

    company_name: str
    event_date: str
    event_type: str
    event_subtype: str | None
    amount_usd: float | None
    counterparty: str | None
    source_id: str
    metadata: str


EVENT_TABLE_COLUMNS: tuple[str, ...] = (
    "company_name",
    "event_date",
    "event_type",
    "event_subtype",
    "amount_usd",
    "counterparty",
    "source_id",
    "metadata",
)
