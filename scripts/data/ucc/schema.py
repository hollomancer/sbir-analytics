"""Shared TypedDict + Enum schemas for UCC pilot artifacts."""

from enum import StrEnum
from typing import TypedDict


class FilingType(StrEnum):
    INITIAL = "initial"           # UCC-1 financing statement
    AMENDMENT = "amendment"       # UCC-3 amendment
    CONTINUATION = "continuation" # UCC-3 continuation
    ASSIGNMENT = "assignment"     # UCC-3 secured-party assignment
    TERMINATION = "termination"   # UCC-3 termination


class UCCStatus(StrEnum):
    ACTIVE = "active"
    TERMINATED = "terminated"
    LAPSED = "lapsed"
    UNKNOWN = "unknown"


class CohortRow(TypedDict):
    """Form D high-confidence cohort entry."""

    company_name: str
    state: str               # primary SBIR address state
    city: str                # SBIR city (consumed by matcher for address overlap)
    zip_code: str            # SBIR ZIP (5-digit prefix)
    agency: str
    first_award_year: int
    last_award_year: int
    total_award_amount: float
    form_d_filing_count: int
    form_d_total_raised: float


class UCCFiling(TypedDict):
    """One UCC filing row from the CA bizfileOnline extractor."""

    filing_number: str
    parent_filing_number: str | None  # None for INITIAL; populated for UCC-3s
    filing_date: str                  # ISO date YYYY-MM-DD
    filing_type: str                  # FilingType.value
    debtor_name: str
    debtor_address: str
    secured_party_name: str
    secured_party_address: str
    status_portal: str                # raw status reported by CA portal
    lapse_date: str | None            # ISO date or None
    source: str                       # "CA" for the pilot


class UCCLifecycle(TypedDict):
    """Reconstructed lifecycle for one UCC-1 initial filing."""

    initial_filing_number: str
    debtor_name: str
    secured_party_name: str        # latest, post-assignment
    status: str                    # UCCStatus.value
    terminated_on: str | None      # earliest termination date
    last_event_date: str
    assignment_chain: list[str]    # ordered secured-party history
    related_filing_count: int      # initial + UCC-3s
    status_portal: str             # raw portal status for cross-check


class UCCMatch(TypedDict):
    """UCC filing row joined to a cohort firm with match confidence."""

    filing: UCCFiling
    cohort_company_name: str
    match_confidence: str          # "high" | "medium" | "low"
    match_score: float             # jaro-winkler similarity, 0..1


class ClassifiedSecuredParty(TypedDict):
    """Secured party classified into a taxonomy category."""

    secured_party_name: str
    category: str  # venture_debt | equipment_finance | bank_depository |
                   # tax_authority | foreign | other | unknown
    is_foreign: bool
