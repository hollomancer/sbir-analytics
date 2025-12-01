#!/usr/bin/env python3
"""Generate realistic USAspending test data matching the real schema."""

import gzip
import io
import zipfile
from pathlib import Path

# recipient_lookup table columns (from USAspending Django model)
RECIPIENT_LOOKUP_COLUMNS = [
    "id",
    "recipient_hash",
    "legal_business_name",
    "duns",
    "uei",
    "parent_uei",
    "parent_duns",
    "parent_legal_business_name",
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "zip5",
    "zip4",
    "country_code",
    "congressional_district",
    "business_types_codes",
    "update_date",
    "source",
    "alternate_names",
]

# Test companies that match SBIR test data patterns
TEST_RECIPIENTS = [
    {
        "id": 1,
        "recipient_hash": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "legal_business_name": "QUANTUM DYNAMICS INC",
        "duns": "123456789",
        "uei": "QD12ABCDEF00",
        "parent_uei": None,
        "parent_duns": None,
        "parent_legal_business_name": None,
        "address_line_1": "123 Innovation Drive",
        "address_line_2": "Suite 100",
        "city": "Boston",
        "state": "MA",
        "zip5": "02101",
        "zip4": "1234",
        "country_code": "USA",
        "congressional_district": "MA-07",
        "business_types_codes": "{2X,27}",
        "update_date": "2024-01-15 10:30:00",
        "source": "sam",
        "alternate_names": "{Quantum Dynamics,QD Inc}",
    },
    {
        "id": 2,
        "recipient_hash": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
        "legal_business_name": "NEURAL NETWORKS LLC",
        "duns": "234567890",
        "uei": "NN34GHIJKL00",
        "parent_uei": None,
        "parent_duns": None,
        "parent_legal_business_name": None,
        "address_line_1": "456 AI Boulevard",
        "address_line_2": None,
        "city": "San Francisco",
        "state": "CA",
        "zip5": "94102",
        "zip4": None,
        "country_code": "USA",
        "congressional_district": "CA-12",
        "business_types_codes": "{2X}",
        "update_date": "2024-02-20 14:45:00",
        "source": "sam",
        "alternate_names": None,
    },
    {
        "id": 3,
        "recipient_hash": "c3d4e5f6-a7b8-9012-cdef-345678901234",
        "legal_business_name": "BIOMED SOLUTIONS CORP",
        "duns": "345678901",
        "uei": "BS56MNOPQR00",
        "parent_uei": "PARENT123456",
        "parent_duns": "999888777",
        "parent_legal_business_name": "BIOMED HOLDINGS INC",
        "address_line_1": "789 Research Park",
        "address_line_2": "Building C",
        "city": "Research Triangle Park",
        "state": "NC",
        "zip5": "27709",
        "zip4": "5678",
        "country_code": "USA",
        "congressional_district": "NC-04",
        "business_types_codes": "{2X,A2}",
        "update_date": "2024-03-10 09:15:00",
        "source": "fpds",
        "alternate_names": "{Biomed Solutions,BSC}",
    },
    {
        "id": 4,
        "recipient_hash": "d4e5f6a7-b8c9-0123-defa-456789012345",
        "legal_business_name": "AI ROBOTICS SYSTEMS INC",
        "duns": "456789012",
        "uei": "AR78STUVWX00",
        "parent_uei": None,
        "parent_duns": None,
        "parent_legal_business_name": None,
        "address_line_1": "321 Automation Way",
        "address_line_2": None,
        "city": "Pittsburgh",
        "state": "PA",
        "zip5": "15213",
        "zip4": "9012",
        "country_code": "USA",
        "congressional_district": "PA-18",
        "business_types_codes": "{2X,23}",
        "update_date": "2024-04-05 16:20:00",
        "source": "sam",
        "alternate_names": "{AI Robotics,AIRS}",
    },
    {
        "id": 5,
        "recipient_hash": "e5f6a7b8-c9d0-1234-efab-567890123456",
        "legal_business_name": "ADVANCED MATERIALS TECH LLC",
        "duns": "567890123",
        "uei": "AM90YZABCD00",
        "parent_uei": None,
        "parent_duns": None,
        "parent_legal_business_name": None,
        "address_line_1": "555 Materials Science Blvd",
        "address_line_2": "Floor 3",
        "city": "Austin",
        "state": "TX",
        "zip5": "78701",
        "zip4": None,
        "country_code": "USA",
        "congressional_district": "TX-25",
        "business_types_codes": "{2X}",
        "update_date": "2024-05-12 11:00:00",
        "source": "sam",
        "alternate_names": None,
    },
]


def format_value(val) -> str:
    """Format value for PostgreSQL COPY format."""
    if val is None:
        return "\\N"
    return str(val).replace("\t", " ").replace("\n", " ")


def generate_recipient_lookup_data() -> str:
    """Generate tab-separated data for recipient_lookup table."""
    lines = []
    for recipient in TEST_RECIPIENTS:
        row = [format_value(recipient.get(col)) for col in RECIPIENT_LOOKUP_COLUMNS]
        lines.append("\t".join(row))
    return "\n".join(lines)


def create_test_dump(output_path: Path):
    """Create a test USAspending dump ZIP file with recipient_lookup data."""
    # OID 5419 is typically recipient_lookup in USAspending dumps
    # (5420 is transaction_normalized)
    recipient_data = generate_recipient_lookup_data()

    # Compress the data
    compressed = gzip.compress(recipient_data.encode("utf-8"))

    # Create ZIP file
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add recipient_lookup as 5419.dat.gz
        zf.writestr("5419.dat.gz", compressed)

    print(f"Created test dump: {output_path}")
    print(f"  - 5419.dat.gz (recipient_lookup): {len(TEST_RECIPIENTS)} records")
    print(f"  - Columns: {len(RECIPIENT_LOOKUP_COLUMNS)}")


if __name__ == "__main__":
    output_dir = Path("data/usaspending")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "usaspending-db-test_recipient_lookup.zip"
    create_test_dump(output_file)

    # Also show sample data
    print("\nSample data (first 2 rows):")
    data = generate_recipient_lookup_data()
    for line in data.split("\n")[:2]:
        print(f"  {line[:100]}...")
