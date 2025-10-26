from datetime import date

import pytest

from src.models.sbir_award import SbirAward


def test_valid_sbir_award_minimal():
    """Create a minimal valid SbirAward and verify normalization."""
    award = SbirAward(
        company="Acme Corp",
        award_title="Innovative Widget",
        agency="DOD",
        phase="Phase I",
        program="sbir",
        award_amount=50000.0,
        award_year=2022,
        proposal_award_date=date(2022, 5, 1),
        contract_end_date=date(2022, 12, 31),
        agency_tracking_number="ATN-001",
        contract="C-2022-001",
    )
    assert award.company == "Acme Corp"
    # program should be normalized to uppercase SBIR
    assert award.program == "SBIR"
    # phase should remain as provided (Phase I)
    assert award.phase == "Phase I"
    # award_amount preserved
    assert award.award_amount == 50000.0


def test_invalid_phase_value():
    """Phase must be one of the allowed values."""
    with pytest.raises(ValueError):
        SbirAward(
            company="Bad Phase Co",
            award_title="Test",
            agency="NSF",
            phase="Phase IV",
            program="SBIR",
            award_amount=10000.0,
            award_year=2020,
            proposal_award_date=date(2020, 1, 1),
            agency_tracking_number="ATN-002",
            contract="C-2020-002",
        )


def test_program_validation_and_normalization():
    """Program must be SBIR or STTR and will be normalized to uppercase."""
    # invalid program
    with pytest.raises(ValueError):
        SbirAward(
            company="Bad Prog Co",
            award_title="Test",
            agency="DOE",
            phase="Phase I",
            program="INVALID",
            award_amount=10000.0,
            award_year=2020,
            proposal_award_date=date(2020, 1, 1),
            agency_tracking_number="ATN-003",
            contract="C-2020-003",
        )

    # lowercase accepted and normalized
    award = SbirAward(
        company="Good Prog Co",
        award_title="Test",
        agency="DOE",
        phase="Phase I",
        program="sttr",
        award_amount=20000.0,
        award_year=2021,
        proposal_award_date=date(2021, 6, 1),
        agency_tracking_number="ATN-004",
        contract="C-2021-004",
    )
    assert award.program == "STTR"


def test_state_and_zip_validation_and_normalization():
    """State must be 2 letters; ZIP must be 5 or ZIP+4 (10 chars with hyphen)."""
    # valid state lowercase -> normalized to uppercase
    award = SbirAward(
        company="Loc Co",
        award_title="Test Loc",
        agency="HHS",
        phase="Phase II",
        program="SBIR",
        award_amount=30000.0,
        award_year=2020,
        proposal_award_date=date(2020, 3, 1),
        agency_tracking_number="ATN-005",
        contract="C-2020-005",
        state="ca",
        zip="12345-6789",
    )
    assert award.state == "CA"
    assert award.zip == "12345-6789"

    # invalid state length
    with pytest.raises(ValueError):
        SbirAward(
            company="Bad State",
            award_title="Bad",
            agency="HHS",
            phase="Phase I",
            program="SBIR",
            award_amount=10000.0,
            award_year=2019,
            proposal_award_date=date(2019, 1, 1),
            agency_tracking_number="ATN-006",
            contract="C-2019-006",
            state="CAL",
            zip="12345",
        )

    # invalid zip format
    with pytest.raises(ValueError):
        SbirAward(
            company="Bad ZIP",
            award_title="Bad",
            agency="HHS",
            phase="Phase I",
            program="SBIR",
            award_amount=10000.0,
            award_year=2019,
            proposal_award_date=date(2019, 1, 1),
            agency_tracking_number="ATN-007",
            contract="C-2019-007",
            state="NY",
            zip="12-34",
        )


def test_uei_and_duns_validation():
    """UEI must be 12 chars if present; DUNS must be 9 digits if present."""
    # valid forms
    award = SbirAward(
        company="ID Co",
        award_title="IDs",
        agency="NSF",
        phase="Phase I",
        program="SBIR",
        award_amount=60000.0,
        award_year=2022,
        proposal_award_date=date(2022, 2, 2),
        agency_tracking_number="ATN-008",
        contract="C-2022-008",
        uei="ABCDEF123456",
        duns="123456789",
    )
    assert award.uei == "ABCDEF123456"
    assert award.duns == "123456789"

    # invalid UEI length
    with pytest.raises(ValueError):
        SbirAward(
            company="Bad UEI",
            award_title="Bad UEI",
            agency="NSF",
            phase="Phase I",
            program="SBIR",
            award_amount=10000.0,
            award_year=2021,
            proposal_award_date=date(2021, 1, 1),
            agency_tracking_number="ATN-009",
            contract="C-2021-009",
            uei="SHORTUEI",
        )

    # invalid duns
    with pytest.raises(ValueError):
        SbirAward(
            company="Bad DUNS",
            award_title="Bad DUNS",
            agency="NSF",
            phase="Phase I",
            program="SBIR",
            award_amount=10000.0,
            award_year=2021,
            proposal_award_date=date(2021, 1, 1),
            agency_tracking_number="ATN-010",
            contract="C-2021-010",
            duns="12-345",
        )


def test_award_amount_positive_and_range():
    """award_amount must be > 0 and reasonable values accepted."""
    # positive allowed
    SbirAward(
        company="Money Co",
        award_title="Funding",
        agency="DOE",
        phase="Phase II",
        program="SBIR",
        award_amount=1.0,
        award_year=2019,
        proposal_award_date=date(2019, 7, 1),
        agency_tracking_number="ATN-011",
        contract="C-2019-011",
    )

    # zero or negative should raise
    with pytest.raises(ValueError):
        SbirAward(
            company="NoMoney",
            award_title="None",
            agency="DOE",
            phase="Phase II",
            program="SBIR",
            award_amount=0.0,
            award_year=2019,
            proposal_award_date=date(2019, 7, 1),
            agency_tracking_number="ATN-012",
            contract="C-2019-012",
        )

    with pytest.raises(ValueError):
        SbirAward(
            company="NegMoney",
            award_title="Neg",
            agency="DOE",
            phase="Phase II",
            program="SBIR",
            award_amount=-500.0,
            award_year=2019,
            proposal_award_date=date(2019, 7, 1),
            agency_tracking_number="ATN-013",
            contract="C-2019-013",
        )


def test_contract_end_date_must_not_precede_award_date():
    """contract_end_date must be on or after proposal_award_date."""
    # valid ordering
    SbirAward(
        company="Order OK",
        award_title="Dates",
        agency="NASA",
        phase="Phase I",
        program="SBIR",
        award_amount=25000.0,
        award_year=2022,
        proposal_award_date=date(2022, 1, 1),
        contract_end_date=date(2022, 12, 31),
        agency_tracking_number="ATN-014",
        contract="C-2022-014",
    )

    # invalid ordering
    with pytest.raises(ValueError):
        SbirAward(
            company="Order Bad",
            award_title="Dates",
            agency="NASA",
            phase="Phase I",
            program="SBIR",
            award_amount=25000.0,
            award_year=2022,
            proposal_award_date=date(2022, 6, 1),
            contract_end_date=date(2022, 5, 1),
            agency_tracking_number="ATN-015",
            contract="C-2022-015",
        )
