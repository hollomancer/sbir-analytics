"""Shared fixtures for capital_events tests."""

import pytest


@pytest.fixture
def cohort() -> list[dict]:
    """Three synthetic cohort firms covering common test cases.

    - ACME INC: vanilla CA biotech, has SBIR + Form D + MA + patents
    - BORING LLC: SBIR-only, no Form D or MA
    - OUT-OF-STATE CORP: MA firm with diverse events
    """
    return [
        {
            "company_name": "ACME INC",
            "state": "California",
            "city": "SAN DIEGO",
            "zip_code": "92101",
            "agency": "Department of Defense",
            "first_award_year": 2018,
            "last_award_year": 2023,
            "total_award_amount": 1_500_000.0,
            "form_d_filing_count": 1,
            "form_d_total_raised": 25_000_000.0,
        },
        {
            "company_name": "BORING LLC",
            "state": "Texas",
            "city": "AUSTIN",
            "zip_code": "73301",
            "agency": "National Science Foundation",
            "first_award_year": 2020,
            "last_award_year": 2021,
            "total_award_amount": 250_000.0,
            "form_d_filing_count": 0,
            "form_d_total_raised": 0.0,
        },
        {
            "company_name": "OUT-OF-STATE CORP",
            "state": "Massachusetts",
            "city": "CAMBRIDGE",
            "zip_code": "02139",
            "agency": "Department of Health and Human Services",
            "first_award_year": 2015,
            "last_award_year": 2022,
            "total_award_amount": 3_200_000.0,
            "form_d_filing_count": 2,
            "form_d_total_raised": 75_000_000.0,
        },
    ]
