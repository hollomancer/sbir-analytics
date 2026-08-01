"""Integration tests for schema-verified USAspending contract extraction.

The fixtures model the COPY order declared by a PostgreSQL directory archive.
They intentionally avoid positional assumptions from historical dump snapshots.
"""

import datetime
import gzip
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.transition.contracts import normalize_contract_columns
from sbir_etl.extractors.contract_extractor import (
    ArchiveSchemaError,
    ContractExtractor,
    SourceDataError,
)


pytestmark = pytest.mark.integration

SOURCE_MEMBER = "8123.dat.gz"
COPY_COLUMNS = (
    # Deliberately unlike any historic physical order: parsing must be by name.
    "recipient_name",
    "research",
    "transaction_unique_id",
    "federal_action_obligation",
    "generated_unique_award_id",
    "is_fpds",
    "product_or_service_code",
    "recipient_unique_id",
    "action_date",
    "naics_code",
    "awarding_subtier_agency_name",
    "recipient_uei",
    "awarding_toptier_agency_name",
    "extent_competed",
    "piid",
    "period_of_performance_start_date",
    "period_of_performance_current_end_date",
    "contract_award_type",
    "referenced_idv_agency_iden",
    "referenced_idv_piid",
)
TOC_TEXT = "8123; 0 999 TABLE DATA rpt transaction_search usaspending\n"
SCHEMA_SQL = "CREATE TABLE rpt.transaction_search (is_fpds boolean);\n"
COPY_SQL = f"COPY rpt.transaction_search ({', '.join(COPY_COLUMNS)}) FROM stdin;\n\\.\n"


def _transaction_row(**overrides: str) -> dict[str, str]:
    row = {
        "recipient_name": "TEST CONTRACTOR ONE",
        "research": "SR3",
        "transaction_unique_id": "TX-DEFAULT",
        "federal_action_obligation": "100000.00",
        "generated_unique_award_id": "CONT_AWD_DEFAULT",
        "is_fpds": "t",
        "product_or_service_code": "AC12",
        "recipient_unique_id": "TEST12345678",
        "action_date": "20230115",
        "naics_code": "541715",
        "awarding_subtier_agency_name": "Department of the Air Force",
        "recipient_uei": "TEST12345678",
        "awarding_toptier_agency_name": "Department of Defense",
        "extent_competed": "FULL",
        "piid": "CONT001",
        "period_of_performance_start_date": "20230115",
        "period_of_performance_current_end_date": "20240115",
        "contract_award_type": "A",
        "referenced_idv_agency_iden": r"\N",
        "referenced_idv_piid": r"\N",
    }
    row.update(overrides)
    return row


def _copy_line(row: dict[str, str]) -> str:
    return "\t".join(row.get(column, r"\N") for column in COPY_COLUMNS)


@pytest.fixture
def sample_dat_gz_file(tmp_path: Path) -> Path:
    """Create named transaction-search rows in the declared COPY order."""
    data_file = tmp_path / "test_contracts.dat.gz"
    rows = [
        _transaction_row(
            transaction_unique_id="TX-1001",
            generated_unique_award_id="CONT_AWD_TEST_001",
            piid="CONT001",
        ),
        # Assistance row in the parent table: row-gated by is_fpds.
        _transaction_row(
            transaction_unique_id="TX-1002",
            generated_unique_award_id="ASST_AWD_TEST_001",
            is_fpds="f",
            recipient_name="GRANT RECIPIENT",
            recipient_uei="GRANT1234567",
            recipient_unique_id="GRANT1234567",
            federal_action_obligation="50000.00",
            piid="GRANT001",
        ),
        _transaction_row(
            transaction_unique_id="TX-1003",
            generated_unique_award_id="IDV_PARENT_TEST_001",
            action_date="20230125",
            recipient_name="TEST CONTRACTOR TWO",
            recipient_uei="TEST98765432",
            recipient_unique_id="TEST98765432",
            federal_action_obligation="5000000.00",
            piid="IDV001",
            contract_award_type="IDV-A",
        ),
        _transaction_row(
            transaction_unique_id="TX-1004",
            generated_unique_award_id="TASK_ORDER_TEST_001",
            action_date="20230201",
            recipient_name="TEST CONTRACTOR TWO",
            recipient_uei="TEST98765432",
            recipient_unique_id="TEST98765432",
            federal_action_obligation="250000.00",
            piid="TASK001",
            extent_competed="CDO",
            referenced_idv_agency_iden="9700",
            referenced_idv_piid="IDV001",
        ),
        _transaction_row(
            transaction_unique_id="TX-1005",
            generated_unique_award_id="DEOBLIG_TEST_001",
            action_date="20230210",
            recipient_name="TEST CONTRACTOR THREE",
            recipient_uei="TEST11122233",
            recipient_unique_id="TEST11122233",
            federal_action_obligation="-25000.00",
            piid="DEOB001",
        ),
        _transaction_row(
            transaction_unique_id="TX-1006",
            generated_unique_award_id="NOMATCH_TEST_001",
            action_date="20230215",
            recipient_name="DIFFERENT CONTRACTOR",
            recipient_uei="NOMATCH00000",
            recipient_unique_id="NOMATCH00000",
            federal_action_obligation="10000.00",
            piid="NOMAT001",
        ),
    ]
    with gzip.open(data_file, "wt", encoding="utf-8") as file:
        for row in rows:
            file.write(_copy_line(row) + "\n")
    return data_file


@pytest.fixture
def vendor_filter_file(tmp_path: Path) -> Path:
    filter_file = tmp_path / "integration_filters.json"
    filter_file.write_text(
        json.dumps(
            {
                "uei": ["TEST12345678", "TEST98765432", "TEST11122233"],
                "duns": [],
                "company_names": ["TEST CONTRACTOR ONE", "TEST CONTRACTOR TWO"],
            }
        )
    )
    return filter_file


@pytest.fixture
def verified_pg_restore(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make archive inspection return an explicit parent-table COPY contract."""

    def fake_pg_restore(dump_dir: Path, *arguments: str) -> str:
        if "--list" in arguments:
            return TOC_TEXT
        if "--schema-only" in arguments:
            return SCHEMA_SQL
        if "--data-only" in arguments:
            # _restore_copy_statement must construct an empty selected member.
            assert (dump_dir / SOURCE_MEMBER).is_file()
            return COPY_SQL
        raise AssertionError(f"Unexpected pg_restore arguments: {arguments!r}")

    monkeypatch.setattr(ContractExtractor, "_run_pg_restore", staticmethod(fake_pg_restore))


def _install_verified_archive(dump_dir: Path, source_file: Path) -> None:
    dump_dir.mkdir()
    (dump_dir / "toc.dat").write_bytes(b"fixture archive metadata")
    shutil.copy(source_file, dump_dir / SOURCE_MEMBER)


class TestContractExtractorStreaming:
    def test_stream_dat_gz_file(self, sample_dat_gz_file, vendor_filter_file) -> None:
        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)

        contracts = list(
            extractor.stream_dat_gz_file(
                sample_dat_gz_file,
                COPY_COLUMNS,
                fpds_only=False,
            )
        )

        assert len(contracts) == 4
        assert contracts[0].contract_id == "CONT001"
        assert contracts[0].vendor_name == "TEST CONTRACTOR ONE"
        assert contracts[0].vendor_uei == "TEST12345678"
        assert contracts[0].obligation_amount == 100000.00
        assert contracts[0].is_deobligation is False

        idv_contract = next(contract for contract in contracts if contract.contract_id == "IDV001")
        assert idv_contract.metadata["parent_relationship_type"] == "idv_parent"

        task_contract = next(
            contract for contract in contracts if contract.contract_id == "TASK001"
        )
        assert task_contract.parent_contract_id == "IDV001"
        assert task_contract.metadata["parent_relationship_type"] == "child_of_idv"

        deobligation = next(contract for contract in contracts if contract.contract_id == "DEOB001")
        assert deobligation.obligation_amount == -25000.00
        assert deobligation.is_deobligation is True

    def test_stream_without_vendor_filter(self, sample_dat_gz_file) -> None:
        contracts = list(
            ContractExtractor().stream_dat_gz_file(
                sample_dat_gz_file,
                COPY_COLUMNS,
                fpds_only=False,
            )
        )

        assert len(contracts) == 5

    def test_stream_statistics_tracking(self, sample_dat_gz_file, vendor_filter_file) -> None:
        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)

        list(extractor.stream_dat_gz_file(sample_dat_gz_file, COPY_COLUMNS, fpds_only=False))

        assert extractor.stats["records_scanned"] == 6
        assert extractor.stats["contracts_found"] == 5
        assert extractor.stats["vendor_matches"] == 4
        assert extractor.stats["records_extracted"] == 4

    def test_stream_parent_child_tracking(self, sample_dat_gz_file, vendor_filter_file) -> None:
        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)

        list(extractor.stream_dat_gz_file(sample_dat_gz_file, COPY_COLUMNS, fpds_only=False))

        assert extractor.stats["parent_relationships"] == 1
        assert extractor.stats["child_relationships"] == 1
        assert extractor.stats["idv_parents"] == 1
        assert "IDV001" in extractor._parent_ids_seen
        assert "IDV001" in extractor._idv_parent_ids_seen


class TestExtractFromDump:
    def test_extract_from_dump_end_to_end(
        self,
        tmp_path,
        sample_dat_gz_file,
        vendor_filter_file,
        verified_pg_restore,
    ) -> None:
        output_file = tmp_path / "output" / "contracts.parquet"
        dump_dir = tmp_path / "dump"
        _install_verified_archive(dump_dir, sample_dat_gz_file)
        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file, batch_size=2)

        count = extractor.extract_from_dump(
            dump_dir=dump_dir,
            output_file=output_file,
            table_files=[SOURCE_MEMBER],
        )

        assert count == 4
        assert extractor.source_provenance["canonical_table"] == "rpt.transaction_search"
        assert extractor.source_provenance["physical_table"] == "rpt.transaction_search"
        assert extractor.source_provenance["member"] == SOURCE_MEMBER
        assert extractor.source_provenance["column_count"] == len(COPY_COLUMNS)
        assert len(str(extractor.source_provenance["ordered_columns_sha256"])) == 64

        frame = pd.read_parquet(output_file)
        assert len(frame) == 4
        assert {"contract_id", "vendor_name", "obligation_amount"}.issubset(frame.columns)
        assert set(frame["contract_id"]) == {"CONT001", "IDV001", "TASK001", "DEOB001"}

    def test_extract_from_dump_statistics(
        self,
        tmp_path,
        sample_dat_gz_file,
        vendor_filter_file,
        verified_pg_restore,
    ) -> None:
        dump_dir = tmp_path / "dump"
        _install_verified_archive(dump_dir, sample_dat_gz_file)
        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)

        extractor.extract_from_dump(dump_dir, tmp_path / "stats.parquet")

        assert extractor.stats["records_scanned"] == 6
        assert extractor.stats["records_extracted"] == 4
        assert extractor.stats["unique_parent_ids"] == 1
        assert extractor.stats["unique_idv_parents"] == 1

    def test_extract_from_dump_batch_processing(
        self,
        tmp_path,
        sample_dat_gz_file,
        vendor_filter_file,
        verified_pg_restore,
    ) -> None:
        dump_dir = tmp_path / "dump"
        output_file = tmp_path / "batch.parquet"
        _install_verified_archive(dump_dir, sample_dat_gz_file)
        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file, batch_size=1)

        count = extractor.extract_from_dump(dump_dir, output_file)

        assert count == 4
        assert len(pd.read_parquet(output_file)) == 4

    def test_extract_from_dump_no_toc(self, tmp_path, vendor_filter_file) -> None:
        dump_dir = tmp_path / "empty_dump"
        dump_dir.mkdir()

        with pytest.raises(ArchiveSchemaError, match="no toc.dat"):
            ContractExtractor(vendor_filter_file=vendor_filter_file).extract_from_dump(
                dump_dir,
                tmp_path / "empty.parquet",
            )

    def test_extract_from_dump_selects_toc_member_not_largest(
        self,
        tmp_path,
        sample_dat_gz_file,
        vendor_filter_file,
        verified_pg_restore,
    ) -> None:
        dump_dir = tmp_path / "dump"
        _install_verified_archive(dump_dir, sample_dat_gz_file)
        unrelated = dump_dir / "9999.dat.gz"
        shutil.copy(sample_dat_gz_file, unrelated)
        with gzip.open(unrelated, "at", encoding="utf-8") as file:
            file.write(_copy_line(_transaction_row(transaction_unique_id="TX-EXTRA")) + "\n")
        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)

        extractor.extract_from_dump(dump_dir, tmp_path / "toc-selected.parquet")

        assert extractor.source_provenance["member"] == SOURCE_MEMBER
        assert extractor.stats["records_scanned"] == 6


class TestActionDateEndToEnd:
    def test_true_action_date_survives_extract_and_bridge(
        self,
        tmp_path,
        vendor_filter_file,
        verified_pg_restore,
    ) -> None:
        data_file = tmp_path / "action_date.dat.gz"
        row = _transaction_row(
            transaction_unique_id="TX-5001",
            generated_unique_award_id="CONT_AWD_ACTION_DATE_001",
            piid="ACT001",
            action_date="20221101",
            period_of_performance_start_date="20230801",
        )
        with gzip.open(data_file, "wt", encoding="utf-8") as file:
            file.write(_copy_line(row) + "\n")
        dump_dir = tmp_path / "dump"
        _install_verified_archive(dump_dir, data_file)

        output_file = tmp_path / "action-date.parquet"
        count = ContractExtractor(vendor_filter_file=vendor_filter_file).extract_from_dump(
            dump_dir,
            output_file,
        )

        assert count == 1
        normalized = normalize_contract_columns(pd.read_parquet(output_file)).iloc[0]
        assert normalized["contract_id"] == "ACT001"
        assert pd.Timestamp(normalized["action_date"]).date() == datetime.date(2022, 11, 1)
        assert pd.Timestamp(normalized["start_date"]).date() == datetime.date(2023, 8, 1)
        assert normalized["action_date"] != normalized["start_date"]


class TestContractExtractorEdgeCasesIntegration:
    def test_empty_dat_gz_file(self, tmp_path, vendor_filter_file) -> None:
        empty_file = tmp_path / "empty.dat.gz"
        with gzip.open(empty_file, "wt", encoding="utf-8"):
            pass
        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)

        contracts = list(extractor.stream_dat_gz_file(empty_file, COPY_COLUMNS, fpds_only=False))

        assert contracts == []
        assert extractor.stats["records_scanned"] == 0

    def test_malformed_row_fails_closed(self, tmp_path, vendor_filter_file) -> None:
        malformed_file = tmp_path / "malformed.dat.gz"
        with gzip.open(malformed_file, "wt", encoding="utf-8") as file:
            file.write(
                _copy_line(
                    _transaction_row(
                        transaction_unique_id="TX-2001",
                        generated_unique_award_id="CONT_AWD_2001",
                        piid="VALID001",
                    )
                )
                + "\n"
            )
            file.write("bad\tdata\n")

        extractor = ContractExtractor(vendor_filter_file=vendor_filter_file)

        with pytest.raises(SourceDataError, match="COPY declares"):
            list(
                extractor.stream_dat_gz_file(
                    malformed_file,
                    COPY_COLUMNS,
                    fpds_only=False,
                )
            )

        assert extractor.stats["records_scanned"] == 2
        assert extractor.stats["records_extracted"] == 1

    def test_matched_row_without_stable_transaction_key_fails_closed(
        self,
        tmp_path,
        vendor_filter_file,
    ) -> None:
        data_file = tmp_path / "missing-key.dat.gz"
        with gzip.open(data_file, "wt", encoding="utf-8") as file:
            file.write(_copy_line(_transaction_row(transaction_unique_id=r"\N")) + "\n")

        with pytest.raises(SourceDataError, match="transaction_unique_id"):
            list(
                ContractExtractor(vendor_filter_file=vendor_filter_file).stream_dat_gz_file(
                    data_file,
                    COPY_COLUMNS,
                    fpds_only=False,
                )
            )

    def test_malformed_obligation_remains_null(self, tmp_path, vendor_filter_file) -> None:
        data_file = tmp_path / "malformed-obligation.dat.gz"
        with gzip.open(data_file, "wt", encoding="utf-8") as file:
            file.write(
                _copy_line(_transaction_row(federal_action_obligation="not-a-number")) + "\n"
            )

        contracts = list(
            ContractExtractor(vendor_filter_file=vendor_filter_file).stream_dat_gz_file(
                data_file,
                COPY_COLUMNS,
                fpds_only=False,
            )
        )

        assert contracts[0].obligation_amount is None
        assert contracts[0].is_deobligation is False

    def test_large_batch_accumulation(
        self,
        tmp_path,
        vendor_filter_file,
        verified_pg_restore,
    ) -> None:
        data_file = tmp_path / "large.dat.gz"
        with gzip.open(data_file, "wt", encoding="utf-8") as file:
            for index in range(25):
                file.write(
                    _copy_line(
                        _transaction_row(
                            transaction_unique_id=f"TX-{3000 + index}",
                            generated_unique_award_id=f"CONT_AWD_{3000 + index}",
                            recipient_name=f"CONTRACTOR {index}",
                            piid=f"BATCH{index:03d}",
                            federal_action_obligation=str(1000.00 * (index + 1)),
                        )
                    )
                    + "\n"
                )
        dump_dir = tmp_path / "dump"
        _install_verified_archive(dump_dir, data_file)
        output_file = tmp_path / "large.parquet"

        count = ContractExtractor(
            vendor_filter_file=vendor_filter_file,
            batch_size=10,
        ).extract_from_dump(dump_dir, output_file)

        assert count == 25
        frame = pd.read_parquet(output_file)
        assert len(frame) == 25
        assert frame["obligation_amount"].min() == 1000.00
        assert frame["obligation_amount"].max() == 25000.00
