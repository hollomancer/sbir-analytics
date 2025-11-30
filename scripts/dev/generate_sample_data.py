"""
Generate sample data for local development.
Creates minimal valid CSV/Parquet files for the SBIR ETL pipeline.
"""

import shutil
import tempfile
import pandas as pd
import numpy as np
from pathlib import Path
from loguru import logger

# Configuration
DATA_ROOT = Path("data")
RAW_DIR = DATA_ROOT / "raw"
USASPENDING_DIR = DATA_ROOT / "usaspending"


def setup_directories():
    """Create necessary directories."""
    dirs = [
        RAW_DIR / "sbir",
        RAW_DIR / "sam_gov",
        RAW_DIR / "uspto",
        USASPENDING_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {d}")


def generate_sbir_awards():
    """Generate sample SBIR awards CSV."""
    output_path = RAW_DIR / "sbir" / "award_data.csv"
    if output_path.exists():
        logger.info(f"SBIR awards file already exists: {output_path}")
        return

    logger.info("Generating sample SBIR awards...")
    data = {
        "Award Title": [f"Sample Award {i}" for i in range(10)],
        "Agency": ["DOD", "DOE", "NASA", "NSF", "HHS"] * 2,
        "Branch": ["Air Force", "Navy", "Army", "N/A", "NIH"] * 2,
        "Phase": ["Phase I", "Phase II"] * 5,
        "Program": ["SBIR", "STTR"] * 5,
        "Agency Tracking Number": [f"N{i:05d}" for i in range(10)],
        "Contract": [f"C{i:05d}" for i in range(10)],
        "Proposal Award Date": pd.date_range(start="2023-01-01", periods=10).strftime("%m/%d/%Y"),
        "Contract End Date": pd.date_range(start="2024-01-01", periods=10).strftime("%m/%d/%Y"),
        "Solicitation Number": [f"SOL-{i}" for i in range(10)],
        "Solicitation Year": [2023] * 10,
        "Topic Code": [f"TOPIC-{i}" for i in range(10)],
        "Award Year": [2023] * 10,
        "Award Amount": np.random.randint(50000, 1500000, 10),
        "Duns": [f"12345678{i}" for i in range(10)],
        "UEI": [f"UEI{i}ABCDEF" for i in range(10)],
        "Hubzone Owned": ["N"] * 10,
        "Socially and Economically Disadvantaged": ["N"] * 10,
        "Woman Owned": ["N"] * 10,
        "Company": [f"Sample Company {i}" for i in range(10)],
        "Address1": ["123 Main St"] * 10,
        "Address2": [""] * 10,
        "City": ["Anytown"] * 10,
        "State": ["VA"] * 10,
        "Zip": ["22202"] * 10,
        "Contact Name": ["John Doe"] * 10,
        "Contact Title": ["PI"] * 10,
        "Contact Phone": ["555-1234"] * 10,
        "Contact Email": ["john@example.com"] * 10,
        "PI Name": ["Jane Smith"] * 10,
        "PI Title": ["Chief Scientist"] * 10,
        "PI Phone": ["555-5678"] * 10,
        "PI Email": ["jane@example.com"] * 10,
        "RI Name": ["Research Inst"] * 10,
        "RI POC Name": ["Dr. RI"] * 10,
        "RI POC Phone": ["555-9999"] * 10,
        "Research Keywords": ["AI, ML, Data"] * 10,
        "Abstract": ["Sample abstract text."] * 10,
    }
    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False)
    logger.success(f"Created {output_path}")


def generate_sam_gov_entities():
    """Generate sample SAM.gov entity records Parquet."""
    output_path = RAW_DIR / "sam_gov" / "sam_entity_records.parquet"
    if output_path.exists():
        logger.info(f"SAM.gov file already exists: {output_path}")
        return

    logger.info("Generating sample SAM.gov entities...")
    data = {
        "uei": [f"UEI{i}ABCDEF" for i in range(10)],
        "legal_business_name": [f"Sample Company {i}" for i in range(10)],
        "dba_name": [None] * 10,
        "physical_address_city": ["Anytown"] * 10,
        "physical_address_state_code": ["VA"] * 10,
        "physical_address_zip_code": ["22202"] * 10,
        "entity_structure": ["Corporate"] * 10,
        "business_type": ["Small Business"] * 10,
        "primary_naics": ["541715"] * 10,
        "registration_date": pd.date_range(start="2020-01-01", periods=10),
        "expiration_date": pd.date_range(start="2025-01-01", periods=10),
    }
    df = pd.DataFrame(data)
    df.to_parquet(output_path)
    logger.success(f"Created {output_path}")


def generate_uspto_patents():
    """Generate sample USPTO patent assignments CSV."""
    output_path = RAW_DIR / "uspto" / "patent_assignments.csv"
    if output_path.exists():
        logger.info(f"USPTO patents file already exists: {output_path}")
        return

    logger.info("Generating sample USPTO patents...")
    data = {
        "patent_number": [f"1000000{i}" for i in range(5)],
        "grant_date": pd.date_range(start="2023-01-01", periods=5).strftime("%Y-%m-%d"),
        "assignment_date": pd.date_range(start="2023-06-01", periods=5).strftime("%Y-%m-%d"),
        "assignor": [f"Inventor {i}" for i in range(5)],
        "assignee": [f"Sample Company {i}" for i in range(5)],
        "conveyance_text": ["Assignment of Assignors Interest"] * 5,
        "reel_no": [f"1234{i}" for i in range(5)],
        "frame_no": [f"000{i}" for i in range(5)],
    }
    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False)
    logger.success(f"Created {output_path}")


def generate_usaspending_dump():
    """Generate a dummy USAspending dump zip file compatible with the extractor."""
    output_path = USASPENDING_DIR / "usaspending-db_20251006.zip"
    if output_path.exists():
        logger.info(f"USAspending dump already exists: {output_path}")
        return

    logger.info("Generating dummy USAspending dump...")

    # Create a dummy dataframe for transaction_normalized
    # The extractor looks for OID 5420 for the main view
    data = {
        "transaction_id": range(10),
        "award_id": [f"CONT_AWD_{i}" for i in range(10)],
        "action_date": pd.date_range(start="2023-01-01", periods=10).strftime("%Y-%m-%d"),
        "federal_action_obligation": np.random.uniform(1000, 100000, 10),
        "awarding_agency_name": ["DOD"] * 10,
        "recipient_name": [f"Sample Company {i}" for i in range(10)],
        "recipient_uei": [f"UEI{i}ABCDEF" for i in range(10)],
    }
    df = pd.DataFrame(data)

    # Create temp directory for processing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # 1. Write as tab-delimited, no header (Postgres COPY format approximation)
        dat_file = temp_path / "5420.dat"
        df.to_csv(dat_file, sep="\t", index=False, header=False)

        # 2. Gzip it
        import gzip

        gz_file = temp_path / "5420.dat.gz"
        with open(dat_file, "rb") as f_in:
            with gzip.open(gz_file, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        # 3. Zip it into the final output
        import zipfile

        with zipfile.ZipFile(output_path, "w") as zf:
            zf.write(gz_file, arcname="5420.dat.gz")

    logger.success(f"Created {output_path}")


def main():
    setup_directories()
    generate_sbir_awards()
    generate_sam_gov_entities()
    generate_uspto_patents()
    generate_usaspending_dump()
    logger.success("Sample data generation complete.")


if __name__ == "__main__":
    main()
