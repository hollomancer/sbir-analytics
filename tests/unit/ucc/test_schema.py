"""Schema sanity tests — confirm TypedDict structure compiles and parses."""

from sbir_etl.ucc.schema import (
    CohortRow,
    FilingType,
    UCCFiling,
    UCCStatus,
)


def test_filing_type_enum_values():
    assert FilingType.INITIAL.value == "initial"
    assert FilingType.TERMINATION.value == "termination"
    assert FilingType.AMENDMENT.value == "amendment"
    assert FilingType.CONTINUATION.value == "continuation"
    assert FilingType.ASSIGNMENT.value == "assignment"


def test_ucc_status_enum_values():
    assert UCCStatus.ACTIVE.value == "active"
    assert UCCStatus.TERMINATED.value == "terminated"
    assert UCCStatus.LAPSED.value == "lapsed"
    assert UCCStatus.UNKNOWN.value == "unknown"


def test_ucc_filing_can_round_trip_as_json():
    import json

    row: UCCFiling = {
        "filing_number": "197728978614",
        "parent_filing_number": None,
        "filing_date": "2019-08-20",
        "filing_type": FilingType.INITIAL.value,
        "debtor_name": "INHIBRX, INC.",
        "debtor_address": "11025 N TORREY PINES RD STE 200, LA JOLLA, CA 920371030",
        "secured_party_name": "EMPLOYMENT DEVELOPMENT DEPARTMENT",
        "secured_party_address": "722 CAPITOL MALL, SACRAMENTO, CA 95814",
        "status_portal": "Active",
        "lapse_date": "2029-08-20",
        "source": "CA",
    }
    parsed = json.loads(json.dumps(row))
    assert parsed["filing_number"] == "197728978614"


def test_cohort_row_minimum_fields():
    row: CohortRow = {
        "company_name": "Acme Inc",
        "state": "CA",
        "agency": "Department of Defense",
        "first_award_year": 2019,
        "last_award_year": 2023,
        "total_award_amount": 1_249_992.0,
        "form_d_filing_count": 1,
        "form_d_total_raised": 7_000_000.0,
    }
    assert row["company_name"] == "Acme Inc"
