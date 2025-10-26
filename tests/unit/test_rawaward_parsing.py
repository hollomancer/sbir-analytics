import pytest
from datetime import date

from src.models import RawAward, Award


def test_to_award_parses_iso_and_date_strings():
    """RawAward.to_award should parse ISO and YYYY-MM-DD date strings into date objects."""
    raw = RawAward(
        award_id="R-ISO-1",
        company_name="ParseCo",
        award_amount="1000.00",
        award_date="2023-01-02T12:34:56",  # ISO with time
        proposal_award_date="2023-06-01",  # plain YYYY-MM-DD
        contract_end_date="2023-12-31",  # plain YYYY-MM-DD
        program="SBIR",
    )

    award = raw.to_award()
    assert isinstance(award, Award)
    assert award.award_date == date(2023, 1, 2)
    assert award.proposal_award_date == date(2023, 6, 1)
    assert award.contract_end_date == date(2023, 12, 31)


def test_to_award_coerces_numeric_strings_for_amount_and_employees():
    """Numeric-ish strings should be coerced to the correct numeric types."""
    raw = RawAward(
        award_id="R-NUM-1",
        company_name="NumCo",
        award_amount="1,234.56",
        award_date="2023-02-02",
        number_of_employees="1,234",
        program="SBIR",
    )

    award = raw.to_award()
    # award_amount should be coerced to float
    assert isinstance(award.award_amount, float)
    assert abs(award.award_amount - 1234.56) < 1e-6
    # number_of_employees should be coerced to int
    assert isinstance(award.number_of_employees, int)
    assert award.number_of_employees == 1234


def test_to_award_raises_on_unparseable_award_amount():
    """If award_amount is a non-numeric string, to_award should raise a ValueError."""
    raw = RawAward(
        award_id="R-BAD-AMT",
        company_name="BadAmtCo",
        award_amount="not-a-number",
        award_date="2023-03-03",
        program="SBIR",
    )

    with pytest.raises(ValueError, match="award_amount must be numeric"):
        raw.to_award()


def test_to_award_contract_date_before_proposal_raises():
    """to_award should parse dates and then Award validation should reject inconsistent dates."""
    raw = RawAward(
        award_id="R-DATE-BAD",
        company_name="DateCo",
        award_amount="2000",
        award_date="2023-01-01",
        proposal_award_date="2023-06-01",
        contract_end_date="2023-05-01",  # earlier than proposal_award_date
        program="SBIR",
    )

    with pytest.raises(
        ValueError, match="contract_end_date must be on or after proposal_award_date"
    ):
        raw.to_award()
