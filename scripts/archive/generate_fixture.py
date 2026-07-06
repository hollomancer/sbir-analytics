#!/usr/bin/env python3
"""
sbir-analytics/scripts/generate_fixture.py

Generate a well-formed CSV fixture for SBIR ETL tests. The generated CSV will:
- Contain exactly 42 columns (header + rows)
- Use proper CSV quoting for fields that include commas (csv.writer handles this)
- Include numeric fields with commas where appropriate (as strings), and abstracts
  that contain commas so quoting is exercised.
- Write to `tests/fixtures/sbir_sample.csv` by default (creates directories as needed).

Usage:
    python sbir-analytics/scripts/generate_fixture.py
    python sbir-analytics/scripts/generate_fixture.py --output path/to/file.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


HEADER = [
    "Company",
    "Address1",
    "Address2",
    "City",
    "State",
    "Zip",
    "Company Website",
    "Number of Employees",
    "Award Title",
    "Abstract",
    "Agency",
    "Branch",
    "Phase",
    "Program",
    "Topic Code",
    "Award Amount",
    "Award Year",
    "Proposal Award Date",
    "Contract End Date",
    "Solicitation Close Date",
    "Proposal Receipt Date",
    "Date of Notification",
    "Agency Tracking Number",
    "Contract",
    "Solicitation Number",
    "Solicitation Year",
    "UEI",
    "Duns",
    "HUBZone Owned",
    "Socially and Economically Disadvantaged",
    "Woman Owned",
    "Contact Name",
    "Contact Title",
    "Contact Phone",
    "Contact Email",
    "PI Name",
    "PI Title",
    "PI Phone",
    "PI Email",
    "RI Name",
    "RI POC Name",
    "RI POC Phone",
]


SAMPLE_ROWS: list[dict[str, str]] = [
    {
        "Company": "Acme Innovations",
        "Address1": "123 Main St",
        "Address2": "",
        "City": "Anytown",
        "State": "CA",
        "Zip": "94105",
        "Company Website": "https://acme.example.com",
        "Number of Employees": "50",
        "Award Title": "Next-Gen Rocket Fuel",
        # contains a comma -> will be quoted by csv.writer
        "Abstract": "Research on high-efficiency rocket propellants, focusing on stability",
        "Agency": "NASA",
        "Branch": "Aerospace Research",
        "Phase": "Phase I",
        "Program": "SBIR",
        "Topic Code": "RX-101",
        "Award Amount": "500000.00",
        "Award Year": "2023",
        "Proposal Award Date": "2023-06-15",
        "Contract End Date": "2024-06-14",
        "Solicitation Close Date": "2023-03-01",
        "Proposal Receipt Date": "2023-02-15",
        "Date of Notification": "2023-06-01",
        "Agency Tracking Number": "ATN-0001",
        "Contract": "C-2023-0001",
        "Solicitation Number": "SOL-2023-01",
        "Solicitation Year": "2023",
        "UEI": "A1B2C3D4E5F6",  # 12 chars  # pragma: allowlist secret
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
        "Abstract": "Develop platform to rapidly identify antiviral compounds, validate in vitro",
        "Agency": "HHS",
        "Branch": "NIH",
        "Phase": "Phase II",
        "Program": "STTR",
        "Topic Code": "BT-22",
        # include comma in numeric string to exercise quoting
        "Award Amount": "1,500,000.50",
        "Award Year": "2021",
        "Proposal Award Date": "2021-08-01",
        "Contract End Date": "2023-08-01",
        "Solicitation Close Date": "2021-05-01",
        "Proposal Receipt Date": "2021-04-15",
        "Date of Notification": "2021-07-20",
        "Agency Tracking Number": "ATN-0002",
        "Contract": "C-2021-0420",
        "Solicitation Number": "SOL-2021-03",
        "Solicitation Year": "2021",
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
        "Address2": "",
        "City": "Cambridge",
        "State": "MA",
        "Zip": "02139",
        "Company Website": "",
        "Number of Employees": "25",
        "Award Title": "Nano-scale Sensors",
        "Abstract": "Development of nano-scale sensor technology",  # short, no comma here
        "Agency": "DOD",
        "Branch": "Army",
        "Phase": "Phase I",
        "Program": "SBIR",
        "Topic Code": "NW-001",
        "Award Amount": "75,000",  # include comma
        "Award Year": "2019",
        "Proposal Award Date": "2019-01-10",
        "Contract End Date": "2019-12-31",
        "Solicitation Close Date": "2019-01-05",
        "Proposal Receipt Date": "2019-01-05",
        "Date of Notification": "2019-01-05",
        "Agency Tracking Number": "ATN-0100",
        "Contract": "C-2019-0001",
        "Solicitation Number": "SOL-2019-01",
        "Solicitation Year": "2019",
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
        "Address2": "",
        "City": "Austin",
        "State": "TX",
        "Zip": "78701",
        "Company Website": "https://techstart.com",
        # numeric field with comma (quoted by csv.writer)
        "Number of Employees": "1,000",
        "Award Title": "AI for Healthcare",
        "Abstract": "Applying AI to medical diagnostics, evaluate on retrospective cohorts",
        "Agency": "NSF",
        "Branch": "",
        "Phase": "Phase I",
        "Program": "SBIR",
        "Topic Code": "TS-45",
        "Award Amount": "1,000,000.00",
        "Award Year": "2022",
        "Proposal Award Date": "05/15/2022",
        "Contract End Date": "05/14/2024",
        "Solicitation Close Date": "02/01/2022",
        "Proposal Receipt Date": "01/15/2022",
        "Date of Notification": "05/01/2022",
        "Agency Tracking Number": "ATN-0003",
        "Contract": "C-2022-0003",
        "Solicitation Number": "SOL-2022-05",
        "Solicitation Year": "2022",
        # Make UEI 12 characters for model expectations
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
        "Address2": "",
        "City": "Seattle",
        "State": "WA",
        "Zip": "98101",
        "Company Website": "",
        "Number of Employees": "500",
        "Award Title": "Sustainable Energy Solutions",
        "Abstract": "Developing renewable energy tech, prototypes and field trials",
        "Agency": "DOE",
        "Branch": "",
        "Phase": "Phase II",
        "Program": "SBIR",
        "Topic Code": "GE-10",
        "Award Amount": "2500000",
        "Award Year": "2020",
        "Proposal Award Date": "10-01-2020",
        "Contract End Date": "10-01-2022",
        "Solicitation Close Date": "07-01-2020",
        "Proposal Receipt Date": "06-15-2020",
        "Date of Notification": "09-20-2020",
        "Agency Tracking Number": "ATN-0004",
        "Contract": "C-2020-0004",
        "Solicitation Number": "SOL-2020-07",
        "Solicitation Year": "2020",
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
        "Address2": "",
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
        "Topic Code": "SX-01",
        "Award Amount": "100000",
        "Award Year": "2018",
        "Proposal Award Date": "2018-01-01",
        "Contract End Date": "",
        "Solicitation Close Date": "",
        "Proposal Receipt Date": "",
        "Date of Notification": "",
        "Agency Tracking Number": "ATN-0005",
        "Contract": "C-2018-0005",
        "Solicitation Number": "SOL-2018-01",
        "Solicitation Year": "2018",
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


def generate_csv(output_path: Path, rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Use newline='' and csv module to ensure proper quoting and line endings
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(HEADER)
        for r in rows:
            # create a row ordered according to HEADER to ensure exact 42 columns
            row = [r.get(col, "") for col in HEADER]
            # Defensive check: ensure exactly 42 values
            if len(row) != len(HEADER):
                raise RuntimeError(f"Row length mismatch (expected {len(HEADER)}): {row!r}")
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a well-formed SBIR CSV fixture.")
    parser.add_argument(
        "--output",
        "-o",
        default="tests/fixtures/sbir_sample.csv",
        help="Output CSV path (default: tests/fixtures/sbir_sample.csv)",
    )
    parser.add_argument(
        "--rows",
        "-r",
        type=int,
        default=len(SAMPLE_ROWS),
        help=f"How many sample rows to write (default: {len(SAMPLE_ROWS)})",
    )
    args = parser.parse_args()

    out_path = Path(args.output)
    rows_to_write = SAMPLE_ROWS[: args.rows]

    generate_csv(out_path, rows_to_write)

    # Quick verification: read back and report counts
    with out_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh, delimiter=",", quotechar='"')
        parsed_counts = [len(row) for row in reader]

    print(f"Wrote CSV to: {out_path}  (rows written including header: {len(parsed_counts)})")
    print(f"Unique parsed column counts in file: {sorted(set(parsed_counts))}")
    # show a simple success criterion
    if all(c == len(HEADER) for c in parsed_counts):
        print("Verification: OK — all rows have the expected number of columns.")
        return 0
    else:
        print("Verification: FAILED — inconsistent column counts found in generated CSV.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
