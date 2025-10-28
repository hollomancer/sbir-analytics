"""
Federal Contracts Extractor from USAspending PostgreSQL dumps.

This module provides streaming extraction of federal contract data from
USAspending.gov PostgreSQL dump files (.dat.gz format), with vendor-based
filtering to extract only contracts relevant to SBIR awardees.

The extractor processes the transaction_normalized table, which contains
all federal spending transactions including contracts, grants, loans, etc.
We filter specifically for contract transactions (type code 'contract').
"""

import gzip
import json
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set
from datetime import date, datetime

import pandas as pd
from loguru import logger
from pydantic import ValidationError

from src.models.transition_models import FederalContract, CompetitionType


# USAspending transaction_normalized column mapping
# Based on USAspending data dictionary and observed structure
USASPENDING_COLUMNS = {
    # Core identifiers
    "transaction_id": 0,
    "generated_unique_award_id": 1,
    "action_date": 2,
    "fiscal_year": 3,
    "type": 4,  # 'A'=BPA, 'B'=Purchase Order, 'C'=Delivery Order, 'D'=Definitive Contract
    "action_type": 5,
    "action_type_description": 6,
    # Award description
    "award_description": 7,
    "modification_number": 8,
    "recipient_name": 9,  # Vendor name
    # Identifiers
    "piid": 26,  # Procurement Instrument ID
    # Vendor identifiers (approximate positions, may vary)
    "awardee_or_recipient_uei": 48,  # UEI
    "recipient_duns": 49,  # DUNS (legacy)
    "cage_code": 50,  # CAGE code
    # Agency info
    "awarding_agency_code": 11,
    "awarding_agency_name": 12,
    "awarding_sub_tier_agency_code": 13,
    "awarding_sub_tier_agency_name": 14,
    "funding_agency_code": 31,
    "funding_agency_name": 32,
    # Financial
    "federal_action_obligation": 27,  # Contract amount
    # Competition
    "extent_competed": 79,  # Competition type code
    # Dates
    "period_of_performance_start_date": 94,
    "period_of_performance_current_end_date": 95,
}


class ContractExtractor:
    """
    Extract federal contracts from USAspending PostgreSQL dump files.

    Features:
    - Streaming processing of large .dat.gz files
    - Vendor-based filtering (only extract SBIR vendor contracts)
    - Memory-efficient batch processing
    - Direct FederalContract model output

    Example:
        ```python
        extractor = ContractExtractor(vendor_filter_file="sbir_vendor_filters.json")

        # Extract from dump directory
        contracts = extractor.extract_from_dump(
            dump_dir="/path/to/pruned_data_store_api_dump",
            output_file="filtered_contracts.parquet"
        )
        ```
    """

    def __init__(
        self,
        vendor_filter_file: Optional[Path] = None,
        batch_size: int = 10000,
    ):
        """
        Initialize contract extractor.

        Args:
            vendor_filter_file: Path to JSON file with SBIR vendor filters
            batch_size: Number of records to process per batch
        """
        self.batch_size = batch_size
        self.vendor_filters = self._load_vendor_filters(vendor_filter_file)

        # Statistics
        self.stats = {
            "records_scanned": 0,
            "contracts_found": 0,
            "vendor_matches": 0,
            "records_extracted": 0,
        }

    def _load_vendor_filters(self, filter_file: Optional[Path]) -> Dict[str, Set[str]]:
        """Load vendor filter sets from JSON file."""
        if not filter_file or not Path(filter_file).exists():
            logger.warning("No vendor filter file provided, will extract all contracts")
            return {"uei": set(), "duns": set(), "company_names": set()}

        logger.info(f"Loading vendor filters from {filter_file}")
        with open(filter_file, "r") as f:
            data = json.load(f)

        filters = {
            "uei": set(data.get("uei", [])),
            "duns": set(data.get("duns", [])),
            "company_names": set(name.upper() for name in data.get("company_names", [])),
        }

        logger.info(
            f"Loaded {len(filters['uei'])} UEI, {len(filters['duns'])} DUNS, "
            f"{len(filters['company_names'])} company name filters"
        )

        return filters

    def _is_contract_type(self, type_code: str) -> bool:
        """Check if transaction type is a contract (not grant, loan, etc.)."""
        # Contract type codes: A, B, C, D, IDV types
        contract_types = {"A", "B", "C", "D", "02", "03", "04"}
        return type_code in contract_types if type_code else False

    def _matches_vendor_filter(self, row_data: List[str]) -> bool:
        """
        Check if transaction matches SBIR vendor filters.

        Args:
            row_data: List of column values from tab-delimited row

        Returns:
            True if vendor matches any filter
        """
        if not self.vendor_filters["uei"] and not self.vendor_filters["duns"]:
            # No filters loaded, accept all
            return True

        try:
            # Check UEI
            if len(row_data) > 48:
                uei = row_data[48].strip() if row_data[48] else ""
                if uei and uei in self.vendor_filters["uei"]:
                    return True

            # Check DUNS
            if len(row_data) > 49:
                duns = row_data[49].strip() if row_data[49] else ""
                if duns and duns in self.vendor_filters["duns"]:
                    return True

            # Fallback: check company name (fuzzy matching would be expensive)
            if len(row_data) > 9:
                company_name = row_data[9].strip().upper() if row_data[9] else ""
                if company_name and company_name in self.vendor_filters["company_names"]:
                    return True

        except (IndexError, AttributeError):
            pass

        return False

    def _parse_contract_row(self, row_data: List[str]) -> Optional[FederalContract]:
        """
        Parse tab-delimited row into FederalContract model.

        Args:
            row_data: List of column values

        Returns:
            FederalContract instance or None if parsing fails
        """
        try:
            # Helper to safely get column value
            def get_col(idx: int, default: Optional[str] = None) -> Optional[str]:
                try:
                    val = (
                        row_data[idx].strip() if idx < len(row_data) and row_data[idx] else default
                    )
                    return val if val and val != "\\N" else default
                except (IndexError, AttributeError):
                    return default

            # Parse competition type
            extent_competed = get_col(79, "")
            competition_map = {
                "A": CompetitionType.FULL_AND_OPEN,
                "B": CompetitionType.LIMITED,
                "C": CompetitionType.LIMITED,
                "D": CompetitionType.SOLE_SOURCE,
                "E": CompetitionType.SOLE_SOURCE,
                "F": CompetitionType.LIMITED,
                "G": CompetitionType.LIMITED,
            }
            competition_type = competition_map.get(
                extent_competed[:1] if extent_competed else "", CompetitionType.OTHER
            )

            # Parse dates
            def parse_date(date_str: Optional[str]) -> Optional[date]:
                if not date_str or date_str == "\\N":
                    return None
                try:
                    return datetime.strptime(date_str[:8], "%Y%m%d").date()
                except (ValueError, TypeError):
                    return None

            start_date = parse_date(get_col(94))
            end_date = parse_date(get_col(95))
            action_date = parse_date(get_col(2))

            # Parse amount
            obligation_str = get_col(27, "0")
            try:
                obligation_amount = float(obligation_str) if obligation_str else 0.0
            except (ValueError, TypeError):
                obligation_amount = 0.0

            # Create FederalContract
            contract = FederalContract(
                contract_id=get_col(
                    26, get_col(1, f"unknown_{row_data[0]}")
                ),  # PIID or generated ID
                agency=get_col(12),  # awarding_agency_name
                sub_agency=get_col(14),  # awarding_sub_tier_agency_name
                vendor_name=get_col(9),  # recipient_name
                vendor_uei=get_col(48),  # awardee_or_recipient_uei
                vendor_cage=get_col(50),  # cage_code
                vendor_duns=get_col(49),  # recipient_duns
                start_date=start_date or action_date,  # Use action_date as fallback
                end_date=end_date,
                obligation_amount=obligation_amount,
                competition_type=competition_type,
                description=get_col(7),  # award_description
                metadata={
                    "transaction_id": get_col(0),
                    "award_id": get_col(1),
                    "modification_number": get_col(8),
                    "action_date": action_date.isoformat() if action_date else None,
                    "funding_agency": get_col(32),
                },
            )

            return contract

        except (ValidationError, Exception) as e:
            logger.debug(f"Failed to parse contract row: {e}")
            return None

    def stream_dat_gz_file(
        self,
        dat_file: Path,
    ) -> Iterator[FederalContract]:
        """
        Stream and parse a single .dat.gz file.

        Args:
            dat_file: Path to .dat.gz file

        Yields:
            FederalContract instances that match vendor filters
        """
        logger.info(f"Processing {dat_file.name}...")

        with gzip.open(dat_file, "rt", encoding="utf-8", errors="replace") as f:
            for line_num, line in enumerate(f, 1):
                self.stats["records_scanned"] += 1

                # Progress logging
                if line_num % 100000 == 0:
                    logger.info(
                        f"  Processed {line_num:,} records, "
                        f"found {self.stats['records_extracted']} contracts"
                    )

                # Split tab-delimited row
                row_data = line.strip().split("\t")

                # Check if it's a contract type
                if len(row_data) > 4:
                    type_code = row_data[4]
                    if not self._is_contract_type(type_code):
                        continue

                    self.stats["contracts_found"] += 1

                # Check vendor filter
                if not self._matches_vendor_filter(row_data):
                    continue

                self.stats["vendor_matches"] += 1

                # Parse into FederalContract
                contract = self._parse_contract_row(row_data)
                if contract:
                    self.stats["records_extracted"] += 1
                    yield contract

        logger.info(
            f"Completed {dat_file.name}: {self.stats['records_extracted']} contracts extracted"
        )

    def extract_from_dump(
        self,
        dump_dir: Path,
        output_file: Path,
        table_files: Optional[List[str]] = None,
    ) -> int:
        """
        Extract contracts from PostgreSQL dump directory.

        Args:
            dump_dir: Path to pruned_data_store_api_dump directory
            output_file: Path to output Parquet file
            table_files: Specific .dat.gz files to process (default: largest file)

        Returns:
            Number of contracts extracted
        """
        dump_dir = Path(dump_dir)
        if not dump_dir.exists():
            raise FileNotFoundError(f"Dump directory not found: {dump_dir}")

        # Find data files
        if not table_files:
            # Find largest .dat.gz file (likely transaction_normalized)
            dat_files = sorted(
                dump_dir.glob("*.dat.gz"), key=lambda f: f.stat().st_size, reverse=True
            )
            if not dat_files:
                raise FileNotFoundError(f"No .dat.gz files found in {dump_dir}")
            table_files = [dat_files[0].name]  # Use only the largest file
            logger.info(
                f"Auto-selected largest file: {table_files[0]} ({dat_files[0].stat().st_size / 1e9:.1f} GB)"
            )

        # Process files and collect contracts
        all_contracts = []
        batch_contracts = []

        for table_file in table_files:
            dat_path = dump_dir / table_file

            for contract in self.stream_dat_gz_file(dat_path):
                batch_contracts.append(contract.model_dump())

                # Write batch to avoid memory issues
                if len(batch_contracts) >= self.batch_size:
                    all_contracts.extend(batch_contracts)
                    logger.info(f"Batch accumulated: {len(all_contracts):,} total contracts")
                    batch_contracts = []

        # Add remaining contracts
        if batch_contracts:
            all_contracts.extend(batch_contracts)

        # Write to Parquet
        if all_contracts:
            logger.info(f"Writing {len(all_contracts):,} contracts to {output_file}")
            df = pd.DataFrame(all_contracts)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(output_file, index=False, compression="snappy")
            logger.success(f"Contracts saved to {output_file}")
        else:
            logger.warning("No contracts extracted")

        # Log statistics
        logger.info("\n" + "=" * 60)
        logger.info("Extraction Statistics:")
        logger.info("=" * 60)
        for key, value in self.stats.items():
            logger.info(f"  {key}: {value:,}")
        logger.info("=" * 60)

        return len(all_contracts)


__all__ = ["ContractExtractor"]
