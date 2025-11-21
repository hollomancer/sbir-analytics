from datetime import date
from pathlib import Path

import pandas as pd
import pytest


pytestmark = pytest.mark.fast

from src.extractors.sbir import SbirDuckDBExtractor
from src.models.award import RawAward


FIXTURE_CSV = Path("tests/fixtures/sbir_sample.csv")


def test_import_csv_returns_metadata_and_columns(tmp_path: Path):
    """Test CSV import returns valid metadata with correct structure and counts."""
    from tests.assertions import assert_valid_extraction_metadata

    assert FIXTURE_CSV.exists(), f"Expected fixture CSV at {FIXTURE_CSV} to exist"

    db_path = tmp_path / "sbir.duckdb"
    extractor = SbirDuckDBExtractor(
        csv_path=FIXTURE_CSV, duckdb_path=str(db_path), table_name="sbir_test"
    )

    metadata = extractor.import_csv(use_incremental=False)

    # Use custom assertion helper - validates structure, types, and expected counts
    assert_valid_extraction_metadata(
        metadata,
        expected_row_count=100,
        expected_column_count=42,
    )


def test_import_csv_raises_on_missing_columns(tmp_path: Path):
    """
    Create a deliberately malformed CSV (too few columns) and ensure the
    extractor raises a RuntimeError indicating column-count mismatch.
    """
    # Create a small CSV with only two columns to simulate a broken file
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("a,b\n1,2\n3,4\n")

    db_path = tmp_path / "bad.duckdb"
    extractor = SbirDuckDBExtractor(
        csv_path=bad_csv, duckdb_path=str(db_path), table_name="sbir_bad"
    )

    with pytest.raises(RuntimeError) as excinfo:
        extractor.import_csv(use_incremental=False)

    # Error message should indicate expected vs found columns
    msg = str(excinfo.value)
    assert "expected" in msg.lower() and "columns" in msg.lower()


# ============================================================================
# FACTORY-BASED TESTS (Refactored - replaces old hardcoded test)
# These tests provide better coverage with less code using factories
# ============================================================================


def test_rawaward_to_award_with_iso_date_format():
    """Test RawAward conversion with ISO date format and standard numeric values."""
    from tests.assertions import assert_award_fields_equal, assert_valid_award
    from tests.factories import RawAwardFactory

    raw = RawAwardFactory.create(
        award_id="C-2023-0001",
        company_name="Acme Innovations",
        company_address="123 Main St",
        company_city="Anytown",
        company_state="CA",
        company_zip="94105",
        award_amount="500000.00",
        award_date="2023-06-15",
        phase="Phase I",
        program="SBIR",
        company_uei="A1B2C3D4E5F6",
        company_duns="123456789",
        is_hubzone=False,
        is_woman_owned=False,
        is_socially_disadvantaged=True,
    )

    award = raw.to_award()

    assert_valid_award(award, require_uei=True, require_duns=True)
    assert_award_fields_equal(
        award,
        {
            "company_name": "Acme Innovations",
            "award_amount": 500000.0,
            "company_uei": "A1B2C3D4E5F6",
            "company_duns": "123456789",
            "is_hubzone": False,
            "is_socially_disadvantaged": True,
            "phase": "I",  # Normalized from "Phase I"
        },
    )
    assert award.award_date.year == 2023
    assert award.award_date.month == 6


@pytest.mark.parametrize(
    "date_string,expected_year,expected_month,expected_day",
    [
        ("2023-06-15", 2023, 6, 15),  # ISO format
        ("06/15/2023", 2023, 6, 15),  # MM/DD/YYYY
        ("06-15-2023", 2023, 6, 15),  # MM-DD-YYYY
    ],
    ids=["iso_format", "us_slash_format", "us_dash_format"],
)
def test_rawaward_date_parsing(date_string, expected_year, expected_month, expected_day):
    """Test that RawAward.to_award() correctly parses various date formats."""
    from tests.factories import RawAwardFactory

    raw = RawAwardFactory.create(award_date=date_string)
    award = raw.to_award()

    assert award.award_date.year == expected_year
    assert award.award_date.month == expected_month
    assert award.award_date.day == expected_day


@pytest.mark.parametrize(
    "amount_string,expected_float",
    [
        ("100000", 100000.0),
        ("100000.00", 100000.0),
        ("100,000.00", 100000.0),
        ("1,000,000.00", 1000000.0),
    ],
    ids=["no_comma_no_decimal", "no_comma_decimal", "comma_decimal", "large_amount"],
)
def test_rawaward_amount_parsing(amount_string, expected_float):
    """Test that RawAward.to_award() correctly parses various amount formats."""
    from tests.factories import RawAwardFactory

    raw = RawAwardFactory.create(award_amount=amount_string)
    award = raw.to_award()

    assert award.award_amount == expected_float


@pytest.mark.parametrize(
    "uei_input,duns_input,expected_uei,expected_duns",
    [
        ("A1B2C3D4E5F6", "123456789", "A1B2C3D4E5F6", "123456789"),
        ("a1b2c3d4e5f6", "123-456-789", "A1B2C3D4E5F6", "123456789"),  # Normalization
        ("A1B2-C3D4-E5F6", "123 456 789", "A1B2C3D4E5F6", "123456789"),  # Strip chars
    ],
    ids=["clean_input", "lowercase_dashes", "formatted_input"],
)
def test_rawaward_identifier_normalization(uei_input, duns_input, expected_uei, expected_duns):
    """Test that UEI and DUNS are normalized (uppercase, stripped of formatting)."""
    from tests.factories import RawAwardFactory

    raw = RawAwardFactory.create(company_uei=uei_input, company_duns=duns_input)
    award = raw.to_award()

    assert award.company_uei == expected_uei
    assert award.company_duns == expected_duns


def test_rawaward_with_missing_optional_fields():
    """Test that RawAward.to_award() handles missing optional fields gracefully."""
    from tests.assertions import assert_valid_award
    from tests.factories import RawAwardFactory

    raw = RawAwardFactory.create(
        company_address=None,
        company_city=None,
        contact_name=None,
        principal_investigator=None,
        contract_end_date=None,
    )

    award = raw.to_award()

    assert_valid_award(award)
    assert award.company_address is None
    assert award.company_city is None
    assert award.contact_name is None
    assert award.principal_investigator is None
    assert award.contract_end_date is None
