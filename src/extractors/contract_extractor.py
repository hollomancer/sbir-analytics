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
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from loguru import logger
from pydantic import ValidationError

from src.models.transition_models import CompetitionType, FederalContract


# USAspending transaction_normalized column mapping
# Based on actual .dat.gz file structure observed from subset database
# File 5530.dat.gz contains the transaction_normalized table
#
# IMPORTANT: The transaction_normalized table contains BOTH procurement contracts
# and assistance/grants. Type codes 'A' and 'B' include both categories.
# Procurement-specific fields (CAGE, extent_competed) may not be present in
# all records, especially assistance/grant transactions.
USASPENDING_COLUMNS = {
    # Core identifiers
    "transaction_id": 0,
    "generated_unique_award_id": 1,
    "action_date": 2,  # Format: YYYYMMDD
    "type": 3,  # 'A'=Contract, 'B'=IDV Contract, 'C'=Grant, 'D'=Direct Payment
    "action_type": 4,  # New, Revision, etc.
    "award_type_code": 5,
    "action_type_description": 6,
    # Award description
    "award_description": 7,
    "modification_number": 8,
    "recipient_name": 9,  # Vendor name
    "recipient_unique_id": 10,  # UEI or DUNS (older records) - legacy format
    # Agency info
    "awarding_agency_code": 11,
    "awarding_agency_name": 12,
    "awarding_sub_tier_agency_code": 13,
    "awarding_sub_tier_agency_name": 14,
    "awarding_toptier_agency_code": 15,
    "awarding_toptier_agency_name": 16,
    # Business categories
    "business_categories": 17,  # Array of categories (e.g., {higher_education,...})
    # Identifiers
    "piid": 28,  # Procurement Instrument ID
    "federal_action_obligation": 29,  # Contract amount
    # Funding agency
    "funding_agency_code": 31,
    "funding_agency_name": 32,
    "funding_sub_tier_agency_code": 33,
    "funding_sub_tier_agency_name": 34,
    # Location
    "recipient_state_code": 63,  # State abbreviation (e.g., 'NY', 'CA')
    "recipient_state_name": 64,  # State full name
    # Performance period
    "period_of_performance_current_end_date": 70,  # Format: YYYYMMDD
    "period_of_performance_start_date": 71,  # Format: YYYYMMDD
    # Additional identifiers
    "recipient_uei": 96,  # UEI in 12-character format (newer, preferred)
    "parent_uei": 97,  # Parent organization UEI
    # Procurement-specific fields (may be NULL for assistance/grants)
    "cage_code": 98,  # CAGE code (procurement contracts only)
    "extent_competed": 99,  # Competition type: A&A, CDO, NDO, FSS, etc.
    "contract_award_type": 100,  # Contract type: A, B, C, D (IDV, BPA, etc.)
    "referenced_idv_agency_iden": 101,  # Parent IDV identifier
    "referenced_idv_piid": 102,  # Parent IDV PIID
    # Note: These fields may be NULL (\N) for assistance/grant transactions
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
        vendor_filter_file: Path | None = None,
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
            "parent_relationships": 0,
            "child_relationships": 0,
            "idv_parents": 0,
            "unique_parent_ids": 0,
            "unique_idv_parents": 0,
        }
        self._parent_ids_seen: set[str] = set()
        self._idv_parent_ids_seen: set[str] = set()

    def _load_vendor_filters(self, filter_file: Path | None) -> dict[str, set[str]]:
        """Load vendor filter sets from JSON file."""
        if not filter_file or not Path(filter_file).exists():
            logger.warning("No vendor filter file provided, will extract all contracts")
            return {"uei": set(), "duns": set(), "company_names": set()}

        logger.info(f"Loading vendor filters from {filter_file}")
        with open(filter_file) as f:
            data = json.load(f)

        filters = {
            "uei": set(data.get("uei", [])),
            "duns": set(data.get("duns", [])),
            "company_names": {name.upper() for name in data.get("company_names", [])},
        }

        logger.info(
            f"Loaded {len(filters['uei'])} UEI, {len(filters['duns'])} DUNS, "
            f"{len(filters['company_names'])} company name filters"
        )

        return filters

    def _is_contract_type(self, type_code: str, award_type_code: str = None) -> bool:
        """
        Check if transaction type is a contract (not grant, loan, etc.).

        USAspending type codes (column 4):
        - 'A': Award (mixed - could be contract or grant)
        - 'B': IDV (Indefinite Delivery Vehicle - contract)
        - 'C': Grant/Assistance (NOT a contract)
        - 'D': Direct Payment (NOT a contract)

        USAspending award_type_code (column 6):
        - '02', '03', '04', '05': Grants/assistance
        - 'A', 'B', 'C', 'D': Procurement contracts
        - 'IDV-A', 'IDV-B', etc.: IDV contracts

        Returns True only for procurement contracts.
        """
        if not type_code:
            return False

        # Type 'B' is always IDV (contract)
        if type_code == "B":
            return True

        # Type 'C' and 'D' are grants/assistance
        if type_code in {"C", "D"}:
            return False

        # Type 'A' is mixed - check award_type_code
        if type_code == "A" and award_type_code:
            # Award type codes starting with digits are grants
            if award_type_code and award_type_code[0].isdigit():
                return False
            # Award type codes that are letters or contain 'IDV' are contracts
            if award_type_code.startswith(("A", "B", "C", "D", "IDV")):
                return True

        # Default to False for safety (only include confirmed contracts)
        return False

    def _parse_competition_type(self, extent_competed: str) -> CompetitionType:
        """
        Parse USAspending extent_competed field to CompetitionType enum.

        USAspending extent_competed codes:
        - 'A&A': Full and open competition after exclusion of sources
        - 'CDO': Competitive Delivery Order
        - 'FSS': Full and open competition (Federal Supply Schedule)
        - 'FULL': Full and open competition
        - 'NDO': Non-competitive Delivery Order
        - 'NONE': Not competed
        - 'Not Available': Unknown
        - NULL/empty: Unknown

        Returns:
            CompetitionType enum value
        """
        if not extent_competed or extent_competed == "\\N" or extent_competed == "Not Available":
            return CompetitionType.OTHER

        extent_competed = extent_competed.strip().upper()

        # Full and open competition
        if extent_competed in {"FULL", "FSS", "A&A", "CDO"}:
            return CompetitionType.FULL_AND_OPEN

        # No competition (sole source)
        if extent_competed in {"NONE", "NDO"}:
            return CompetitionType.SOLE_SOURCE

        # Limited competition patterns
        if "LIMITED" in extent_competed or "RESTRICTED" in extent_competed:
            return CompetitionType.LIMITED

        return CompetitionType.OTHER

    def _matches_vendor_filter(self, row_data: list[str]) -> bool:
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
            # Check UEI/DUNS in column 10 (recipient_unique_id)
            # This column contains UEI for newer records, DUNS for older records
            if len(row_data) > 10:
                unique_id = row_data[10].strip() if row_data[10] else ""
                if unique_id and unique_id != "\\N":
                    # Try matching as UEI first
                    if unique_id in self.vendor_filters["uei"]:
                        return True
                    # Try matching as DUNS
                    if unique_id in self.vendor_filters["duns"]:
                        return True

            # Fallback: check company name (fuzzy matching would be expensive)
            if len(row_data) > 9:
                company_name = row_data[9].strip().upper() if row_data[9] else ""
                if company_name and company_name in self.vendor_filters["company_names"]:
                    return True

        except (IndexError, AttributeError):
            pass

        return False

    def _parse_contract_row(self, row_data: list[str]) -> FederalContract | None:
        """
        Parse tab-delimited row into FederalContract model.

        Args:
            row_data: List of column values

        Returns:
            FederalContract instance or None if parsing fails
        """
        try:
            # Helper to safely get column value
            def get_col(idx: int, default: str | None = None) -> str | None:
                try:
                    val = (
                        row_data[idx].strip() if idx < len(row_data) and row_data[idx] else default
                    )
                    return val if val and val != "\\N" else default
                except (IndexError, AttributeError):
                    return default

            # Parse competition type from extent_competed field
            extent_competed = get_col(99)  # Column 99: extent_competed
            competition_type = self._parse_competition_type(extent_competed)

            # Parse dates using centralized utility with 8-digit format support
            from src.utils.date_utils import parse_date
            
            action_date = parse_date(get_col(2), allow_8digit=True, strict=False)
            start_date = parse_date(get_col(71), allow_8digit=True, strict=False)  # period_of_performance_start_date
            end_date = parse_date(get_col(70), allow_8digit=True, strict=False)  # period_of_performance_current_end_date

            # Fallback to action_date if start_date missing
            if not start_date:
                start_date = action_date

            # Parse amount
            obligation_str = get_col(29, "0")  # Column 29 is federal_action_obligation
            try:
                obligation_amount = float(obligation_str) if obligation_str else 0.0
            except (ValueError, TypeError):
                obligation_amount = 0.0

            # Get vendor identifiers
            # Priority: column 96 (12-char UEI) > column 10 (legacy UEI/DUNS)
            uei_primary = get_col(96)  # Preferred 12-character UEI format
            recipient_id_legacy = get_col(10)  # Legacy format (UEI or DUNS)
            parent_uei = get_col(97)  # Parent organization UEI
            cage_code = get_col(98)  # CAGE code (procurement contracts only)

            # Determine best UEI/DUNS values
            vendor_uei = None
            vendor_duns = None

            if uei_primary and len(uei_primary) == 12:
                vendor_uei = uei_primary
            elif recipient_id_legacy:
                if len(recipient_id_legacy) == 12:
                    vendor_uei = recipient_id_legacy
                elif len(recipient_id_legacy) == 9 and recipient_id_legacy.isdigit():
                    vendor_duns = recipient_id_legacy

            # Get parent contract/IDV information for handling relationships
            parent_idv_piid = get_col(102)  # Referenced IDV PIID
            contract_award_type = get_col(100)  # Contract type (A, B, C, D, IDV-*)
            parent_idv_agency = get_col(101)  # Referenced IDV agency identifier

            relationship_type = "standalone"
            if parent_idv_piid:
                relationship_type = "child_of_idv"
                self.stats["parent_relationships"] += 1
                self.stats["child_relationships"] += 1
                self._parent_ids_seen.add(parent_idv_piid)
            elif contract_award_type:
                award_type_normalized = contract_award_type.strip().upper()
                if award_type_normalized.startswith("IDV") or award_type_normalized in {
                    "BPA",
                    "BOA",
                    "IDIQ",
                }:
                    relationship_type = "idv_parent"
                    self.stats["idv_parents"] += 1

            # Create FederalContract
            contract_id_value = get_col(28, get_col(1, f"unknown_{row_data[0]}"))  # PIID (col 28)
            contract = FederalContract(
                contract_id=contract_id_value,
                agency=get_col(12),  # awarding_agency_name
                sub_agency=get_col(14),  # awarding_sub_tier_agency_name
                vendor_name=get_col(9),  # recipient_name
                vendor_uei=vendor_uei,
                vendor_cage=cage_code,  # CAGE code from column 98
                vendor_duns=vendor_duns,
                start_date=start_date,
                end_date=end_date,
                obligation_amount=obligation_amount,
                is_deobligation=(obligation_amount < 0),  # Flag negative amounts
                competition_type=competition_type,
                description=get_col(7),  # award_description
                parent_contract_id=parent_idv_piid,
                parent_contract_agency=parent_idv_agency,
                contract_award_type=contract_award_type,
                metadata={
                    "transaction_id": get_col(0),
                    "award_id": get_col(1),
                    "modification_number": get_col(8),
                    "action_date": action_date.isoformat() if action_date else None,
                    "funding_agency": get_col(32),
                    "parent_uei": parent_uei,
                    "recipient_state": get_col(63),  # State code
                    "business_categories": get_col(17),  # Business type categories
                    "extent_competed": extent_competed,  # Raw competition field
                    "contract_award_type": contract_award_type,  # Contract type
                    "parent_idv_piid": parent_idv_piid,  # Parent IDV for task orders
                    "referenced_idv_agency": parent_idv_agency,
                    "parent_relationship_type": relationship_type,
                },
            )
            if relationship_type == "idv_parent" and contract.contract_id:
                self._idv_parent_ids_seen.add(contract.contract_id)

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

                # Check if it's a contract type (columns 4 and 6)
                if len(row_data) > 5:
                    type_code = row_data[3]  # Column 4: type
                    award_type_code = row_data[5]  # Column 6: award_type_code
                    if not self._is_contract_type(type_code, award_type_code):
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
        table_files: list[str] | None = None,
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
            from src.utils.data.file_io import save_dataframe_parquet
            
            save_dataframe_parquet(df, output_file, index=False, compression="snappy")
            logger.success(f"Contracts saved to {output_file}")
        else:
            logger.warning("No contracts extracted")

        # Log statistics
        self.stats["unique_parent_ids"] = len(self._parent_ids_seen)
        self.stats["unique_idv_parents"] = len(self._idv_parent_ids_seen)
        logger.info("\n" + "=" * 60)
        logger.info("Extraction Statistics:")
        logger.info("=" * 60)
        for key, value in self.stats.items():
            logger.info(f"  {key}: {value:,}")
        logger.info("=" * 60)

        return len(all_contracts)


__all__ = ["ContractExtractor"]
