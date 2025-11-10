"""Integration tests for ContractExtractor.

Tests cover end-to-end extraction scenarios:
- Streaming from .dat.gz files
- Full extract_from_dump pipeline
- Statistics tracking across large batches
- Parquet output validation
- Parent/child relationship tracking
"""

import gzip
import json

import pandas as pd
import pytest

from src.extractors.contract_extractor import ContractExtractor


pytestmark = pytest.mark.integration


@pytest.fixture
def sample_dat_gz_file(tmp_path):
    """Create a sample .dat.gz file with test contract data."""
    data_file = tmp_path / "test_contracts.dat.gz"

    # Create sample rows (tab-delimited)
    rows = []

    # Row 1: Valid contract matching filter
    row1 = ["\\N"] * 103
    row1[0] = "1001"  # transaction_id
    row1[1] = "CONT_AWD_TEST_001"
    row1[2] = "20230115"  # action_date
    row1[3] = "A"  # type (contract)
    row1[5] = "A"  # award_type_code
    row1[9] = "TEST CONTRACTOR ONE"  # recipient_name
    row1[10] = "TEST123456789"  # recipient_unique_id
    row1[12] = "Department of Defense"
    row1[28] = "CONT001"  # piid
    row1[29] = "100000.00"  # obligation
    row1[96] = "TEST123456789"  # recipient_uei
    row1[99] = "FULL"  # extent_competed
    rows.append("\t".join(row1))

    # Row 2: Grant (should be filtered out)
    row2 = ["\\N"] * 103
    row2[0] = "1002"
    row2[1] = "GRANT_AWD_TEST_001"
    row2[2] = "20230120"
    row2[3] = "C"  # type (grant - NOT a contract)
    row2[5] = "02"
    row2[9] = "GRANT RECIPIENT"
    row2[96] = "GRANT123456789"
    row2[29] = "50000.00"
    rows.append("\t".join(row2))

    # Row 3: IDV parent contract
    row3 = ["\\N"] * 103
    row3[0] = "1003"
    row3[1] = "IDV_PARENT_TEST_001"
    row3[2] = "20230125"
    row3[3] = "B"  # type (IDV)
    row3[5] = "IDV-A"
    row3[9] = "TEST CONTRACTOR TWO"
    row3[10] = "TEST987654321"
    row3[28] = "IDV001"  # piid
    row3[29] = "5000000.00"
    row3[96] = "TEST987654321"
    row3[99] = "FULL"
    row3[100] = "IDV-A"  # contract_award_type
    rows.append("\t".join(row3))

    # Row 4: Child task order referencing IDV parent
    row4 = ["\\N"] * 103
    row4[0] = "1004"
    row4[1] = "TASK_ORDER_TEST_001"
    row4[2] = "20230201"
    row4[3] = "A"
    row4[5] = "A"
    row4[9] = "TEST CONTRACTOR TWO"
    row4[10] = "TEST987654321"
    row4[28] = "TASK001"  # piid
    row4[29] = "250000.00"
    row4[96] = "TEST987654321"
    row4[99] = "CDO"  # Competitive Delivery Order
    row4[100] = "A"
    row4[101] = "9700"  # referenced_idv_agency_iden
    row4[102] = "IDV001"  # referenced_idv_piid (parent)
    rows.append("\t".join(row4))

    # Row 5: Contract with deobligation (negative amount)
    row5 = ["\\N"] * 103
    row5[0] = "1005"
    row5[1] = "DEOBLIG_TEST_001"
    row5[2] = "20230210"
    row5[3] = "A"
    row5[5] = "A"
    row5[9] = "TEST CONTRACTOR THREE"
    row5[10] = "TEST111222333"
    row5[28] = "DEOB001"
    row5[29] = "-25000.00"  # Negative amount
    row5[96] = "TEST111222333"
    rows.append("\t".join(row5))

    # Row 6: Contract not matching filter
    row6 = ["\\N"] * 103
    row6[0] = "1006"
    row6[1] = "NOMATCH_TEST_001"
    row6[2] = "20230215"
    row6[3] = "A"
    row6[5] = "A"
    row6[9] = "DIFFERENT CONTRACTOR"
    row6[10] = "NOMATCH000000"  # Won't match filter
    row6[28] = "NOMAT001"
    row6[29] = "10000.00"
    row6[96] = "NOMATCH000000"
    rows.append("\t".join(row6))

    # Write compressed file
    with gzip.open(data_file, "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(row + "\n")

    return data_file


@pytest.fixture
def vendor_filter_file(tmp_path):
    """Create vendor filter file for integration tests."""
    filter_data = {
        "uei": ["TEST123456789", "TEST987654321", "TEST111222333"],
        "duns": [],
        "company_names": ["TEST CONTRACTOR ONE", "TEST CONTRACTOR TWO"],
    }
    filter_file = tmp_path / "integration_filters.json"
    with open(filter_file, "w") as f:
        json.dump(filter_data, f)
    return filter_file


class TestContractExtractorStreaming:
    """Tests for streaming data extraction from .dat.gz files."""

    def test_stream_dat_gz_file(self, sample_dat_gz_file, vendor_filter_file):
        """Test streaming and parsing a .dat.gz file."""
        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)

        contracts = list(extractor.stream_dat_gz_file(sample_dat_gz_file))

        # Should extract 4 contracts (1, 3, 4, 5):
        # - Row 1: Valid contract, matches filter
        # - Row 2: Grant (filtered out)
        # - Row 3: IDV parent, matches filter
        # - Row 4: Task order, matches filter
        # - Row 5: Deobligation, matches filter
        # - Row 6: Valid contract, but doesn't match filter
        assert len(contracts) == 4

        # Verify first contract
        assert contracts[0].contract_id == "CONT001"
        assert contracts[0].vendor_name == "TEST CONTRACTOR ONE"
        assert contracts[0].obligation_amount == 100000.00
        assert contracts[0].is_deobligation is False

        # Verify IDV parent
        idv_contract = next(c for c in contracts if c.contract_id == "IDV001")
        assert idv_contract.metadata["parent_relationship_type"] == "idv_parent"

        # Verify child task order
        task_contract = next(c for c in contracts if c.contract_id == "TASK001")
        assert task_contract.parent_contract_id == "IDV001"
        assert task_contract.metadata["parent_relationship_type"] == "child_of_idv"

        # Verify deobligation
        deob_contract = next(c for c in contracts if c.contract_id == "DEOB001")
        assert deob_contract.obligation_amount == -25000.00
        assert deob_contract.is_deobligation is True

    def test_stream_without_vendor_filter(self, sample_dat_gz_file):
        """Test streaming without vendor filter (accepts all)."""
        extractor = ContractExtractor(vendor_filter_file=None)

        contracts = list(extractor.stream_dat_gz_file(sample_dat_gz_file))

        # Without filter, should get all valid contracts (not grants)
        # Rows 1, 3, 4, 5, 6 are contracts (row 2 is grant)
        assert len(contracts) == 5

    def test_stream_statistics_tracking(self, sample_dat_gz_file, vendor_filter_file):
        """Test that statistics are properly tracked during streaming."""
        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)

        list(extractor.stream_dat_gz_file(sample_dat_gz_file))

        # Verify statistics
        assert extractor.stats["records_scanned"] == 6  # Total rows processed
        assert extractor.stats["contracts_found"] >= 5  # Contracts (not grants)
        assert extractor.stats["vendor_matches"] == 4  # Matching filter
        assert extractor.stats["records_extracted"] == 4  # Successfully parsed

    def test_stream_parent_child_tracking(self, sample_dat_gz_file, vendor_filter_file):
        """Test parent/child relationship tracking."""
        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)

        list(extractor.stream_dat_gz_file(sample_dat_gz_file))

        # Verify relationship statistics
        assert extractor.stats["parent_relationships"] == 1  # One child→parent link
        assert extractor.stats["child_relationships"] == 1  # One child contract
        assert extractor.stats["idv_parents"] == 1  # One IDV parent

        # Verify ID tracking
        assert "IDV001" in extractor._parent_ids_seen
        assert "IDV001" in extractor._idv_parent_ids_seen


class TestExtractFromDump:
    """Tests for complete extract_from_dump pipeline."""

    def test_extract_from_dump_end_to_end(
        self, tmp_path, sample_dat_gz_file, vendor_filter_file
    ):
        """Test complete extraction pipeline with Parquet output."""
        output_file = tmp_path / "output" / "contracts.parquet"

        extractor = ContractExtractor(
            vendor_filter_file=vendor_filter_file, batch_size=2  # Small batch for testing
        )

        # Move sample file to dump_dir structure
        dump_dir = tmp_path / "dump"
        dump_dir.mkdir()
        target_file = dump_dir / "test_data.dat.gz"
        import shutil

        shutil.copy(sample_dat_gz_file, target_file)

        # Extract
        count = extractor.extract_from_dump(
            dump_dir=dump_dir,
            output_file=output_file,
            table_files=["test_data.dat.gz"],
        )

        # Verify count
        assert count == 4

        # Verify output file exists
        assert output_file.exists()

        # Load and verify Parquet
        df = pd.read_parquet(output_file)
        assert len(df) == 4
        assert "contract_id" in df.columns
        assert "vendor_name" in df.columns
        assert "obligation_amount" in df.columns

        # Verify data integrity
        assert "CONT001" in df["contract_id"].values
        assert "IDV001" in df["contract_id"].values
        assert "TASK001" in df["contract_id"].values
        assert "DEOB001" in df["contract_id"].values

    def test_extract_from_dump_statistics(self, tmp_path, sample_dat_gz_file, vendor_filter_file):
        """Test statistics reporting after extraction."""
        output_file = tmp_path / "output" / "stats_test.parquet"
        dump_dir = tmp_path / "dump"
        dump_dir.mkdir()

        import shutil

        target_file = dump_dir / "stats_data.dat.gz"
        shutil.copy(sample_dat_gz_file, target_file)

        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)
        extractor.extract_from_dump(
            dump_dir=dump_dir,
            output_file=output_file,
            table_files=["stats_data.dat.gz"],
        )

        # Verify final statistics
        assert extractor.stats["records_scanned"] == 6
        assert extractor.stats["records_extracted"] == 4
        assert extractor.stats["unique_parent_ids"] == 1
        assert extractor.stats["unique_idv_parents"] == 1

    def test_extract_from_dump_batch_processing(
        self, tmp_path, sample_dat_gz_file, vendor_filter_file
    ):
        """Test batch processing with small batch size."""
        output_file = tmp_path / "output" / "batch_test.parquet"
        dump_dir = tmp_path / "dump"
        dump_dir.mkdir()

        import shutil

        target_file = dump_dir / "batch_data.dat.gz"
        shutil.copy(sample_dat_gz_file, target_file)

        # Use batch_size=1 to force multiple batches
        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file, batch_size=1)
        count = extractor.extract_from_dump(
            dump_dir=dump_dir,
            output_file=output_file,
            table_files=["batch_data.dat.gz"],
        )

        assert count == 4

        # Verify output is still correct despite batching
        df = pd.read_parquet(output_file)
        assert len(df) == 4

    def test_extract_from_dump_no_files(self, tmp_path, vendor_filter_file):
        """Test handling of empty dump directory."""
        dump_dir = tmp_path / "empty_dump"
        dump_dir.mkdir()
        output_file = tmp_path / "output" / "empty.parquet"

        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)

        with pytest.raises(FileNotFoundError):
            extractor.extract_from_dump(
                dump_dir=dump_dir,
                output_file=output_file,
            )

    def test_extract_from_dump_auto_selects_largest(
        self, tmp_path, sample_dat_gz_file, vendor_filter_file
    ):
        """Test that extract_from_dump auto-selects largest file."""
        dump_dir = tmp_path / "dump"
        dump_dir.mkdir()
        output_file = tmp_path / "output" / "auto_select.parquet"

        import shutil

        # Create two files, one larger
        file1 = dump_dir / "small.dat.gz"
        file2 = dump_dir / "large.dat.gz"

        # Copy sample to both
        shutil.copy(sample_dat_gz_file, file1)
        shutil.copy(sample_dat_gz_file, file2)

        # Make file2 larger by appending data
        with gzip.open(file2, "at", encoding="utf-8") as f:
            f.write("\t".join(["\\N"] * 103) + "\n")  # Add extra row

        # Don't specify table_files, should auto-select largest
        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)
        extractor.extract_from_dump(
            dump_dir=dump_dir,
            output_file=output_file,
        )

        # Should have selected large.dat.gz (7 rows instead of 6)
        assert extractor.stats["records_scanned"] == 7


class TestContractExtractorEdgeCasesIntegration:
    """Integration tests for edge cases."""

    def test_empty_dat_gz_file(self, tmp_path, vendor_filter_file):
        """Test handling of empty .dat.gz file."""
        empty_file = tmp_path / "empty.dat.gz"
        with gzip.open(empty_file, "wt", encoding="utf-8"):
            pass  # Write nothing

        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)
        contracts = list(extractor.stream_dat_gz_file(empty_file))

        assert len(contracts) == 0
        assert extractor.stats["records_scanned"] == 0

    def test_malformed_rows_skipped(self, tmp_path, vendor_filter_file):
        """Test that malformed rows are skipped gracefully."""
        malformed_file = tmp_path / "malformed.dat.gz"

        with gzip.open(malformed_file, "wt", encoding="utf-8") as f:
            # Valid row
            row1 = ["\\N"] * 103
            row1[0] = "2001"
            row1[2] = "20230101"
            row1[3] = "A"
            row1[5] = "A"
            row1[9] = "VALID CONTRACTOR"
            row1[10] = "TEST123456789"  # recipient_unique_id
            row1[28] = "VALID001"
            row1[29] = "1000.00"
            row1[96] = "TEST123456789"
            f.write("\t".join(row1) + "\n")

            # Malformed row (missing columns)
            f.write("bad\tdata\n")

            # Another valid row
            row3 = ["\\N"] * 103
            row3[0] = "2003"
            row3[2] = "20230103"
            row3[3] = "A"
            row3[5] = "A"
            row3[9] = "ANOTHER CONTRACTOR"
            row3[10] = "TEST123456789"  # recipient_unique_id
            row3[28] = "VALID002"
            row3[29] = "2000.00"
            row3[96] = "TEST123456789"
            f.write("\t".join(row3) + "\n")

        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)
        contracts = list(extractor.stream_dat_gz_file(malformed_file))

        # Should get 2 valid contracts, skipping malformed row
        assert len(contracts) == 2
        assert extractor.stats["records_scanned"] == 3

    def test_large_batch_accumulation(self, tmp_path, vendor_filter_file):
        """Test that batches accumulate correctly for large datasets."""
        large_file = tmp_path / "large.dat.gz"

        # Create file with 25 valid contracts
        with gzip.open(large_file, "wt", encoding="utf-8") as f:
            for i in range(25):
                row = ["\\N"] * 103
                row[0] = str(3000 + i)
                row[2] = "20230101"
                row[3] = "A"
                row[5] = "A"
                row[9] = f"CONTRACTOR {i}"
                row[10] = "TEST123456789"  # recipient_unique_id
                row[28] = f"BATCH{i:03d}"
                row[29] = f"{1000.00 * (i + 1)}"
                row[96] = "TEST123456789"
                f.write("\t".join(row) + "\n")

        output_file = tmp_path / "large_output.parquet"
        dump_dir = tmp_path / "dump"
        dump_dir.mkdir()

        import shutil

        target_file = dump_dir / "large.dat.gz"
        shutil.copy(large_file, target_file)

        # Use batch_size=10 to test batching
        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file, batch_size=10)
        count = extractor.extract_from_dump(
            dump_dir=dump_dir,
            output_file=output_file,
            table_files=["large.dat.gz"],
        )

        assert count == 25

        # Verify all contracts in output
        df = pd.read_parquet(output_file)
        assert len(df) == 25

        # Verify data integrity
        assert df["obligation_amount"].min() == 1000.00
        assert df["obligation_amount"].max() == 25000.00
