"""SBIR CSV data extractor.

This module provides functionality to extract SBIR award data from CSV files.
"""

import pandas as pd
from pathlib import Path
from typing import Optional

from ..config.loader import get_config
from ..utils import log_with_context


def extract_sbir_csv(
    file_path: Path,
    date_format: str = "%m/%d/%Y",
    encoding: str = "utf-8",
    chunk_size: Optional[int] = None
) -> pd.DataFrame:
    """Extract SBIR award data from CSV file.

    Args:
        file_path: Path to the CSV file
        date_format: Date format string for parsing dates
        encoding: File encoding
        chunk_size: Number of rows to read at once (None for all)

    Returns:
        DataFrame containing extracted SBIR data

    Raises:
        FileNotFoundError: If the CSV file doesn't exist
        pd.errors.EmptyDataError: If the CSV file is empty
        ValueError: If required columns are missing
    """
    with log_with_context(stage="extract", run_id="sbir_csv") as logger:
        logger.info(f"Extracting SBIR data from {file_path}")

        if not file_path.exists():
            raise FileNotFoundError(f"SBIR CSV file not found: {file_path}")

        # Read CSV file
        try:
            if chunk_size:
                # Read in chunks for large files
                chunks = []
                for chunk in pd.read_csv(
                    file_path,
                    encoding=encoding,
                    chunksize=chunk_size,
                    low_memory=False
                ):
                    chunks.append(chunk)
                df = pd.concat(chunks, ignore_index=True)
            else:
                df = pd.read_csv(file_path, encoding=encoding, low_memory=False)

        except pd.errors.EmptyDataError:
            raise ValueError(f"SBIR CSV file is empty: {file_path}")

        logger.info(f"Loaded {len(df)} rows from SBIR CSV")

        # Basic validation
        if df.empty:
            raise ValueError("No data found in SBIR CSV file")

        # Parse dates if present
        date_columns = ["Award Date", "award_date"]
        for date_col in date_columns:
            if date_col in df.columns:
                try:
                    df[date_col] = pd.to_datetime(df[date_col], format=date_format, errors='coerce')
                    logger.info(f"Parsed dates in column '{date_col}'")
                except Exception as e:
                    logger.warning(f"Failed to parse dates in column '{date_col}': {e}")

        # Standardize column names (convert to snake_case)
        df.columns = df.columns.str.lower().str.replace(' ', '_')

        logger.info(f"Extracted {len(df)} SBIR records with columns: {list(df.columns)}")
        return df


def extract_sbir_from_config(
    data_dir: Optional[Path] = None,
    filename: str = "sbir_awards.csv"
) -> pd.DataFrame:
    """Extract SBIR data using configuration settings.

    Args:
        data_dir: Directory containing data files (uses config if None)
        filename: Name of the SBIR CSV file

    Returns:
        DataFrame containing extracted SBIR data
    """
    config = get_config()

    if data_dir is None:
        data_dir = Path("data/raw")

    file_path = data_dir / filename

    extraction_config = config.extraction.sbir

    return extract_sbir_csv(
        file_path=file_path,
        date_format=extraction_config.get("date_format", "%m/%d/%Y"),
        encoding=extraction_config.get("encoding", "utf-8"),
        chunk_size=int(extraction_config.get("chunk_size", 0)) or None
    )