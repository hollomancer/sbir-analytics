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


def test_extract_in_chunks_yields_expected_chunk_sizes(tmp_path: Path):
    """
    Import the sample fixture, then call extract_in_chunks with a small batch size
    and validate that chunks are yielded with lengths <= batch_size and that the
    total number of rows equals the table row count.
    """
    assert FIXTURE_CSV.exists(), f"Expected fixture CSV at {FIXTURE_CSV} to exist"

    db_path = tmp_path / "sbir_chunks.duckdb"
    extractor = SbirDuckDBExtractor(
        csv_path=FIXTURE_CSV, duckdb_path=str(db_path), table_name="sbir_chunks"
    )

    # Import CSV so table exists
    metadata = extractor.import_csv(use_incremental=False)
    total_rows = int(metadata["row_count"])
    assert total_rows == 100

    # Request chunks of size 10 -> expect 10 chunks of 10
    chunks = list(extractor.extract_in_chunks(batch_size=10))
    assert len(chunks) >= 1
    assert all(len(chunk) <= 10 for chunk in chunks)

    # Total rows across all chunks must equal the metadata row count
    concatenated = pd.concat(chunks, ignore_index=True) if len(chunks) > 0 else pd.DataFrame()
    assert len(concatenated) == total_rows

    # Verify chunking behavior (fixture has 100 rows, batch_size=10)
    lengths = [len(c) for c in chunks]
    # Should be 10 chunks of 10 each
    assert lengths == [10] * 10


def test_end_to_end_rawaward_to_award_parsing(tmp_path: Path):
    """
    End-to-end test: Use hardcoded sample data to convert each row to RawAward,
    call to_award(), and assert successful parsing/validation.

    Tests various date formats (ISO, MM/DD/YYYY, MM-DD-YYYY), numeric coercions,
    UEI/DUNS normalization, and missing fields.
    """
    # Hardcoded sample data representing CSV rows with various formats
    sample_rows = [
        {
            "Company": "Acme Innovations",
            "Address1": "123 Main St",
            "City": "Anytown",
            "State": "CA",
            "Zip": "94105",
            "Company Website": "https://acme.example.com",
            "Number of Employees": "50",
            "Award Title": "Next-Gen Rocket Fuel",
            "Abstract": "Research on high-efficiency rocket propellants.",
            "Agency": "NASA",
            "Branch": "Aerospace Research",
            "Phase": "Phase I",
            "Program": "SBIR",
            "Award Amount": "500000.00",
            "Award Year": "2023",
            "Proposal Award Date": "2023-06-15",
            "Contract End Date": "2024-06-14",
            "Solicitation Close Date": "2023-03-01",
            "Agency Tracking Number": "ATN-0001",
            "Contract": "C-2023-0001",
            "Solicitation Number": "SOL-2023-01",
            "UEI": "A1B2C3D4E5F6",
            "Duns": "123456789",
            "HUBZone Owned": "N",
            "Socially and Economically Disadvantaged": "Y",
            "Woman Owned": "N",
            "Contact Name": "Jane Doe",
            "Contact Title": "CEO",
            "Contact Phone": "555-123-4567",
            "Contact Email": "jane.doe@acme.example.com",
            "PI Name": "Dr. Alan Smith",
            "PI Title": "Lead Scientist",
            "PI Phone": "555-987-6543",
            "PI Email": "alan.smith@acme.example.com",
            "RI Name": "",
            "RI POC Name": "",
            "RI POC Phone": "",
        },
        {
            "Company": "BioTech Labs",
            "Address1": "456 Bio Rd",
            "Address2": "Suite 200",
            "City": "Bioville",
            "State": "MD",
            "Zip": "21201-1234",
            "Company Website": "http://biotech.example.org",
            "Number of Employees": "120",
            "Award Title": "Novel Antiviral Platform",
            "Abstract": "Develop platform to rapidly identify antiviral compounds.",
            "Agency": "HHS",
            "Branch": "NIH",
            "Phase": "Phase II",
            "Program": "STTR",
            "Award Amount": "1500000.50",
            "Award Year": "2021",
            "Proposal Award Date": "2021-08-01",
            "Contract End Date": "2023-08-01",
            "Solicitation Close Date": "2021-05-01",
            "Agency Tracking Number": "ATN-0002",
            "Contract": "C-2021-0420",
            "Solicitation Number": "SOL-2021-03",
            "UEI": "Z9Y8X7W6V5U4",
            "Duns": "987654321",
            "HUBZone Owned": "Y",
            "Socially and Economically Disadvantaged": "N",
            "Woman Owned": "Y",
            "Contact Name": "Sam Biotech",
            "Contact Title": "CTO",
            "Contact Phone": "410-555-0199",
            "Contact Email": "contact@biotech.example.org",
            "PI Name": "Dr. Susan Lee",
            "PI Title": "Principal Investigator",
            "PI Phone": "410-555-0200",
            "PI Email": "susan.lee@biotech.example.org",
            "RI Name": "Bio Research Institute",
            "RI POC Name": "Alice Researcher",
            "RI POC Phone": "410-555-0210",
        },
        {
            "Company": "NanoWorks",
            "Address1": "456 Nano Way",
            "City": "Cambridge",
            "State": "MA",
            "Zip": "02139",
            "Company Website": "",
            "Number of Employees": "25",
            "Award Title": "Nano-scale Sensors",
            "Abstract": "Development of nano-scale sensor technology.",
            "Agency": "DOD",
            "Branch": "Army",
            "Phase": "Phase I",
            "Program": "SBIR",
            "Award Amount": "75000",
            "Award Year": "2019",
            "Proposal Award Date": "2019-01-10",
            "Contract End Date": "2019-12-31",
            "Solicitation Close Date": "2019-01-05",
            "Agency Tracking Number": "ATN-0100",
            "Contract": "C-2019-0001",
            "Solicitation Number": "SOL-2019-01",
            "UEI": "NWUEI0000000",
            "Duns": "000000001",
            "HUBZone Owned": "N",
            "Socially and Economically Disadvantaged": "N",
            "Woman Owned": "N",
            "Contact Name": "Tom Inventor",
            "Contact Title": "Founder",
            "Contact Phone": "555-000-0000",
            "Contact Email": "tom@nanoworks.example.com",
            "PI Name": "",
            "PI Title": "",
            "PI Phone": "",
            "PI Email": "",
            "RI Name": "",
            "RI POC Name": "",
            "RI POC Phone": "",
        },
        {
            "Company": "TechStart Inc",
            "Address1": "789 Tech Blvd",
            "City": "Austin",
            "State": "TX",
            "Zip": "78701",
            "Company Website": "https://techstart.com",
            "Number of Employees": "1,000",
            "Award Title": "AI for Healthcare",
            "Abstract": "Applying AI to medical diagnostics.",
            "Agency": "NSF",
            "Branch": "",
            "Phase": "Phase I",
            "Program": "SBIR",
            "Award Amount": "1,000,000.00",
            "Award Year": "2022",
            "Proposal Award Date": "05/15/2022",
            "Contract End Date": "05/14/2024",
            "Solicitation Close Date": "02/01/2022",
            "Agency Tracking Number": "ATN-0003",
            "Contract": "C-2022-0003",
            "Solicitation Number": "SOL-2022-05",
            "UEI": "TSUEI1234567",
            "Duns": "123-456-789",
            "HUBZone Owned": "Y",
            "Socially and Economically Disadvantaged": "Y",
            "Woman Owned": "Y",
            "Contact Name": "John Tech",
            "Contact Title": "Founder",
            "Contact Phone": "512-555-0123",
            "Contact Email": "john@techstart.com",
            "PI Name": "Dr. Jane AI",
            "PI Title": "AI Researcher",
            "PI Phone": "512-555-0124",
            "PI Email": "jane@techstart.com",
            "RI Name": "",
            "RI POC Name": "",
            "RI POC Phone": "",
        },
        {
            "Company": "GreenEnergy Corp",
            "Address1": "101 Green St",
            "City": "Seattle",
            "State": "WA",
            "Zip": "98101",
            "Company Website": "",
            "Number of Employees": "500",
            "Award Title": "Sustainable Energy Solutions",
            "Abstract": "Developing renewable energy tech.",
            "Agency": "DOE",
            "Branch": "",
            "Phase": "Phase II",
            "Program": "SBIR",
            "Award Amount": "2500000",
            "Award Year": "2020",
            "Proposal Award Date": "10-01-2020",
            "Contract End Date": "10-01-2022",
            "Solicitation Close Date": "07-01-2020",
            "Agency Tracking Number": "ATN-0004",
            "Contract": "C-2020-0004",
            "Solicitation Number": "SOL-2020-07",
            "UEI": "GREENUEI0000",
            "Duns": "987654321",
            "HUBZone Owned": "N",
            "Socially and Economically Disadvantaged": "N",
            "Woman Owned": "N",
            "Contact Name": "",
            "Contact Title": "",
            "Contact Phone": "",
            "Contact Email": "",
            "PI Name": "",
            "PI Title": "",
            "PI Phone": "",
            "PI Email": "",
            "RI Name": "",
            "RI POC Name": "",
            "RI POC Phone": "",
        },
        {
            "Company": "StartupXYZ",
            "Address1": "",
            "City": "",
            "State": "",
            "Zip": "",
            "Company Website": "",
            "Number of Employees": "10",
            "Award Title": "Innovative Widget",
            "Abstract": "Building the next big thing.",
            "Agency": "DOD",
            "Branch": "Army",
            "Phase": "Phase I",
            "Program": "SBIR",
            "Award Amount": "100000",
            "Award Year": "2018",
            "Proposal Award Date": "2018-01-01",
            "Contract End Date": "",
            "Solicitation Close Date": "",
            "Agency Tracking Number": "ATN-0005",
            "Contract": "C-2018-0005",
            "Solicitation Number": "SOL-2018-01",
            "UEI": "XYZUEI000001",
            "Duns": "000000002",
            "HUBZone Owned": "Y",
            "Socially and Economically Disadvantaged": "N",
            "Woman Owned": "N",
            "Contact Name": "",
            "Contact Title": "",
            "Contact Phone": "",
            "Contact Email": "",
            "PI Name": "",
            "PI Title": "",
            "PI Phone": "",
            "PI Email": "",
            "RI Name": "",
            "RI POC Name": "",
            "RI POC Phone": "",
        },
    ]

    # Mapping from CSV column names to RawAward field names
    column_mapping = {
        "Company": "company_name",
        "Address1": "company_address",
        "City": "company_city",
        "State": "company_state",
        "Zip": "company_zip",
        "Company Website": "company_website",
        "Number of Employees": "number_of_employees",
        "Award Title": "award_title",
        "Abstract": "abstract",
        "Agency": "agency",
        "Branch": "branch",
        "Phase": "phase",
        "Program": "program",
        "Award Amount": "award_amount",
        "Award Year": "award_year",
        "Proposal Award Date": "award_date",  # Map to award_date for the award date
        "Contract End Date": "contract_end_date",
        "Solicitation Close Date": "solicitation_date",
        "Agency Tracking Number": "agency_tracking_number",
        "Contract": "contract",
        "Solicitation Number": "solicitation_number",
        "UEI": "company_uei",
        "Duns": "company_duns",
        "HUBZone Owned": "is_hubzone",
        "Socially and Economically Disadvantaged": "is_socially_disadvantaged",
        "Woman Owned": "is_woman_owned",
        "Contact Name": "contact_name",
        "Contact Phone": "contact_phone",
        "Contact Email": "contact_email",
        "PI Name": "principal_investigator",
        "RI Name": "research_institution",
    }

    awards = []
    for row_dict in sample_rows:
        # Map and clean data
        raw_data = {}
        for csv_col, raw_field in column_mapping.items():
            value = row_dict.get(csv_col)
            if value is not None and str(value).strip() == "":
                value = None
            if raw_field == "phase" and isinstance(value, str):
                # Normalize phase to I, II, III
                value = value.replace("Phase ", "").strip()
            if raw_field in ["is_hubzone", "is_socially_disadvantaged", "is_woman_owned"]:
                # Convert Y/N to bool
                if isinstance(value, str):
                    value = value.upper() == "Y"
                elif value is None:
                    value = None
                else:
                    value = bool(value)
            raw_data[raw_field] = value

        # Set proposal_award_date to the same as award_date since they are the same in this data
        raw_data["proposal_award_date"] = raw_data["award_date"]

        # Use Contract as award_id if available, else generate
        raw_data["award_id"] = row_dict.get("Contract") or f"test-{len(awards)}"

        # Create RawAward and convert to Award
        if len(awards) == 2:  # Debug the failing row
            print(f"raw_data for failing row: {raw_data}")
        raw_award = RawAward(**raw_data)
        try:
            award = raw_award.to_award()
        except Exception as e:
            print(f"Failed on row {len(awards)}: {e}")
            raise
        awards.append(award)

    # Assert we got 6 awards
    assert len(awards) == 6

    # Assert specific examples
    # First row: Acme Innovations
    acme = awards[0]
    assert acme.company_name == "Acme Innovations"
    assert acme.award_amount == 500000.00
    assert acme.award_date.year == 2023
    assert acme.program == "SBIR"
    assert acme.company_uei == "A1B2C3D4E5F6"
    assert acme.company_duns == "123456789"
    assert acme.is_hubzone is False
    assert acme.is_woman_owned is False
    assert acme.is_socially_disadvantaged is True

    # Fourth row: TechStart Inc - tests MM/DD/YYYY dates and comma in numbers
    techstart = awards[3]
    assert techstart.company_name == "TechStart Inc"
    assert techstart.award_amount == 1000000.00  # coerced from "1,000,000.00"
    assert techstart.number_of_employees == 1000  # coerced from "1,000"
    assert techstart.proposal_award_date.month == 5 and techstart.proposal_award_date.day == 15
    assert techstart.company_uei == "TSUEI1234567"  # normalized
    assert techstart.company_duns == "123456789"  # normalized from "123-456-789"
    assert techstart.is_hubzone is True
    assert techstart.is_woman_owned is True
    assert techstart.is_socially_disadvantaged is True

    # Fifth row: GreenEnergy Corp - MM-DD-YYYY dates
    green = awards[4]
    assert green.company_name == "GreenEnergy Corp"
    assert green.award_amount == 2500000.0
    assert green.proposal_award_date.month == 10 and green.proposal_award_date.day == 1
    assert green.contract_end_date.year == 2022
    assert green.company_uei == "GREENUEI0000"
    assert green.company_duns == "987654321"

    # Sixth row: StartupXYZ - many missing fields
    startup = awards[5]
    assert startup.company_name == "StartupXYZ"
    assert startup.award_amount == 100000.0
    assert startup.company_address is None
    assert startup.company_city is None
    assert startup.contact_name is None
    assert startup.is_hubzone is True
    assert startup.number_of_employees == 10

    # All awards should have required fields
    for award in awards:
        assert isinstance(award.award_id, str)
        assert isinstance(award.company_name, str)
        assert isinstance(award.award_amount, float)
        assert award.award_amount > 0
        assert isinstance(award.award_date, date)
        assert award.program in ["SBIR", "STTR"]


# ============================================================================
# NEW FACTORY-BASED TESTS (refactored from test_end_to_end_rawaward_to_award_parsing)
# TODO: After verifying these pass, remove test_end_to_end_rawaward_to_award_parsing above
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
