"""Fail-closed schema and named-row tests for USAspending contract extraction."""

import gzip
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from sbir_etl.extractors.contract_extractor import (
    ArchiveSchemaError,
    ContractExtractor,
    SourceDataError,
    _TableEntry,
    _resolve_source,
)
from sbir_etl.models.transition_models import CompetitionType, FederalContract


pytestmark = pytest.mark.fast

REQUIRED_COLUMNS = (
    "transaction_unique_id",
    "is_fpds",
    "piid",
    "research",
    "generated_unique_award_id",
    "product_or_service_code",
    "naics_code",
    "recipient_uei",
    "recipient_name",
    "awarding_toptier_agency_name",
    "awarding_subtier_agency_name",
    "action_date",
    "extent_competed",
    "federal_action_obligation",
)
OPTIONAL_COLUMNS = (
    "period_of_performance_start_date",
    "period_of_performance_current_end_date",
    "transaction_description",
)
COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS


def _schema_sql(*, partition: bool = True) -> str:
    definitions = ",\n".join(f"    {column} text" for column in reversed(COLUMNS))
    partition_sql = (
        "\nCREATE TABLE rpt.transaction_search_fpds ();\n"
        "ALTER TABLE ONLY rpt.transaction_search ATTACH PARTITION "
        "rpt.transaction_search_fpds FOR VALUES IN (true);\n"
        if partition
        else ""
    )
    return f"CREATE TABLE rpt.transaction_search (\n{definitions}\n);{partition_sql}"


def _copy_sql(table: str = "transaction_search_fpds", columns: tuple[str, ...] = COLUMNS) -> str:
    return f"COPY rpt.{table} ({', '.join(columns)}) FROM stdin;\n\\.\n"


def _toc(*tables: tuple[str, str]) -> str:
    return "\n".join(
        f"{dump_id}; 0 999 TABLE DATA rpt {table} usaspending" for dump_id, table in tables
    )


def _row(**overrides: str) -> dict[str, str]:
    values = {
        "transaction_unique_id": "TX-1",
        "is_fpds": "t",
        "research": "SR3",
        "generated_unique_award_id": "CONT_AWD_1",
        "product_or_service_code": "AC12",
        "naics_code": "541715",
        "recipient_uei": "ABC123456789",  # pragma: allowlist secret
        "recipient_name": "Example Corp",
        "awarding_toptier_agency_name": "Department of Defense",
        "awarding_subtier_agency_name": "Department of the Air Force",
        "action_date": "2024-03-15",
        "extent_competed": "NONE",
        "federal_action_obligation": "-1250.50",
        "piid": "PIID-1",
        "period_of_performance_start_date": "2024-03-20",
        "period_of_performance_current_end_date": "2025-03-20",
        "transaction_description": "Prototype",
    }
    values.update(overrides)
    return values


def _line(row: dict[str, str], columns: tuple[str, ...] = COLUMNS) -> str:
    return "\t".join(row.get(column, r"\N") for column in columns)


def test_resolver_uses_leaf_dump_id_and_copy_order() -> None:
    source = _resolve_source(
        _toc(("8123", "transaction_search"), ("9247", "transaction_search_fpds")),
        _schema_sql(),
        _copy_sql(),
    )

    assert source.member_name == "9247.dat.gz"
    assert source.relation == "rpt.transaction_search_fpds"
    assert source.fpds_only is True
    # CREATE TABLE is deliberately reversed; COPY is the serialized row order.
    assert source.columns == COLUMNS


def test_resolver_accepts_partition_root_copy_target() -> None:
    source = _resolve_source(
        _toc(("9247", "transaction_search_fpds")),
        _schema_sql(),
        _copy_sql("transaction_search"),
    )

    assert source.columns == COLUMNS


@pytest.mark.parametrize("missing_column", ["piid", "research"])
def test_resolver_rejects_missing_provenance_column(missing_column: str) -> None:
    columns = tuple(column for column in COLUMNS if column != missing_column)
    with pytest.raises(ArchiveSchemaError, match=missing_column):
        _resolve_source(
            _toc(("9247", "transaction_search_fpds")),
            _schema_sql(),
            _copy_sql(columns=columns),
        )


def test_resolver_never_selects_fabs_or_unrelated_shape() -> None:
    with pytest.raises(ArchiveSchemaError, match="Expected one"):
        _resolve_source(
            _toc(("9246", "transaction_search_fabs"), ("9999", "transaction_normalized")),
            _schema_sql(),
            _copy_sql("transaction_search_fabs"),
        )


def test_resolver_rejects_unproved_fpds_partition() -> None:
    with pytest.raises(ArchiveSchemaError, match="does not prove"):
        _resolve_source(
            _toc(("9247", "transaction_search_fpds")),
            _schema_sql(partition=False),
            _copy_sql(),
        )


def test_named_parser_preserves_signed_obligation_and_raw_codes() -> None:
    extractor = ContractExtractor()
    source_row = _row(research=" sR3 ", naics_code="541715 ", product_or_service_code=" AC12")

    contracts = list(
        extractor._parse_lines([_line(source_row)], "fixture.dat.gz", COLUMNS, fpds_only=True)
    )

    assert len(contracts) == 1
    contract = contracts[0]
    assert contract.piid == "PIID-1"
    assert contract.transaction_unique_id == "TX-1"
    assert contract.generated_unique_award_id == "CONT_AWD_1"
    assert contract.obligation_amount == -1250.50
    assert contract.is_deobligation is True
    assert contract.competition_type == CompetitionType.SOLE_SOURCE
    assert contract.research == " sR3 "
    assert contract.naics_code == "541715 "
    assert contract.product_or_service_code == " AC12"
    assert contract.metadata["research"] == " sR3 "


@pytest.mark.parametrize("source_value", [r"\N", "not-a-number"])
def test_missing_or_malformed_obligation_stays_none(source_value: str) -> None:
    extractor = ContractExtractor()

    contract = list(
        extractor._parse_lines(
            [_line(_row(federal_action_obligation=source_value))],
            "fixture.dat.gz",
            COLUMNS,
            fpds_only=True,
        )
    )[0]

    assert contract.obligation_amount is None
    assert contract.is_deobligation is False


def test_parent_table_filters_fabs_through_identical_code_path() -> None:
    extractor = ContractExtractor()
    contracts = list(
        extractor._parse_lines(
            [_line(_row(is_fpds="f"))], "parent.dat.gz", COLUMNS, fpds_only=False
        )
    )

    assert contracts == []
    assert extractor.stats["records_scanned"] == 1
    assert extractor.stats["contracts_found"] == 0


def test_fpds_partition_rejects_false_row() -> None:
    extractor = ContractExtractor()
    with pytest.raises(SourceDataError, match="Non-FPDS row"):
        list(
            extractor._parse_lines(
                [_line(_row(is_fpds="f"))], "leaf.dat.gz", COLUMNS, fpds_only=True
            )
        )


def test_row_width_must_match_copy_list() -> None:
    extractor = ContractExtractor()
    with pytest.raises(SourceDataError, match="COPY declares"):
        list(extractor._parse_lines(["too\tshort"], "bad.dat.gz", COLUMNS, fpds_only=True))


def test_matched_row_requires_both_stable_keys() -> None:
    extractor = ContractExtractor()
    with pytest.raises(SourceDataError, match="transaction_unique_id"):
        list(
            extractor._parse_lines(
                [_line(_row(transaction_unique_id=r"\N"))],
                "bad.dat.gz",
                COLUMNS,
                fpds_only=True,
            )
        )


def test_copy_metadata_probe_uses_empty_selected_member(tmp_path, monkeypatch) -> None:
    toc_file = tmp_path / "toc.dat"
    toc_file.write_bytes(b"toc-owned-metadata")
    observed: dict[str, object] = {}

    def fake_pg_restore(dump_dir: Path, *arguments: str) -> str:
        observed["arguments"] = arguments
        assert (dump_dir / "toc.dat").read_bytes() == b"toc-owned-metadata"
        selected = dump_dir / "9247.dat.gz"
        assert selected.is_file()
        with gzip.open(selected, "rb") as file:
            assert file.read() == b""
        return _copy_sql()

    monkeypatch.setattr(ContractExtractor, "_run_pg_restore", staticmethod(fake_pg_restore))
    result = ContractExtractor._restore_copy_statement(
        toc_file, _TableEntry("9247", "rpt", "transaction_search_fpds")
    )

    assert result == _copy_sql()
    assert observed["arguments"] == (
        "--data-only",
        "--schema=rpt",
        "--table=transaction_search_fpds",
        "--strict-names",
        "--file=-",
    )


def test_pg_restore_absence_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("sbir_etl.extractors.contract_extractor.shutil.which", lambda _: None)

    with pytest.raises(ArchiveSchemaError, match="refusing positional extraction"):
        ContractExtractor._run_pg_restore(tmp_path, "--list")


def test_provenance_is_machine_readable_and_stable() -> None:
    source = _resolve_source(
        _toc(("9247", "transaction_search_fpds")),
        _schema_sql(),
        _copy_sql(),
    )

    source = replace(source, toc_sha256="b" * 64)
    provenance = ContractExtractor._provenance(source)

    assert provenance["canonical_table"] == "rpt.transaction_search"
    assert provenance["physical_table"] == "rpt.transaction_search_fpds"
    assert provenance["member"] == "9247.dat.gz"
    assert provenance["column_count"] == len(COLUMNS)
    assert len(str(provenance["ordered_columns_sha256"])) == 64
    assert provenance["toc_sha256"] == "b" * 64


def test_zero_matches_atomically_replace_stale_output(tmp_path, monkeypatch) -> None:
    output = tmp_path / "contracts.parquet"
    output.write_bytes(b"stale")
    observed: dict[str, object] = {}

    def fake_save(frame, path, **kwargs) -> None:
        observed["columns"] = tuple(frame.columns)
        observed["path"] = path
        path.write_bytes(b"fresh-empty-parquet")

    monkeypatch.setattr("sbir_etl.utils.data.file_io.save_dataframe_parquet", fake_save)

    count = ContractExtractor()._collect_and_write([], output)

    assert count == 0
    assert output.read_bytes() == b"fresh-empty-parquet"
    assert observed["columns"] == tuple(FederalContract.model_fields)
    assert observed["path"] != output


def test_multiple_batches_preserve_one_shot_schema_and_row_order(
    tmp_path, sample_child_contract_row
) -> None:
    first = FederalContract(
        contract_id="NULL-FIRST",
        transaction_unique_id="TX-NULL-FIRST",
        generated_unique_award_id="CONT_AWD_NULL_FIRST",
    )
    extractor = ContractExtractor(batch_size=1)
    second = extractor._parse_contract_row(sample_child_contract_row)
    contracts = [first, second]
    output = tmp_path / "contracts.parquet"
    legacy_output = tmp_path / "legacy-one-shot.parquet"
    pd.DataFrame([contract.model_dump() for contract in contracts]).to_parquet(
        legacy_output,
        index=False,
        compression="snappy",
    )

    count = extractor._collect_and_write(iter(contracts), output)

    assert count == 2
    assert pq.read_schema(output).equals(pq.read_schema(legacy_output))
    schema = pq.read_schema(output)
    assert (
        schema.field("matched_vendor").type
        == pq.read_schema(legacy_output).field("matched_vendor").type
    )
    assert schema.field("metadata").type == pq.read_schema(legacy_output).field("metadata").type
    assert pq.ParquetFile(output).metadata.num_row_groups == 2
    assert pd.read_parquet(output)["contract_id"].tolist() == [
        "NULL-FIRST",
        second.contract_id,
    ]


def test_multiple_batch_failure_keeps_stale_output_and_removes_temp(tmp_path) -> None:
    output = tmp_path / "contracts.parquet"
    output.write_bytes(b"stale")
    contract = FederalContract(
        contract_id="C1",
        transaction_unique_id="TX-1",
        generated_unique_award_id="CONT_AWD_1",
    )

    def contracts():
        yield contract
        yield contract.model_copy(update={"contract_id": "C2"})
        raise RuntimeError("source stream failed")

    with pytest.raises(RuntimeError, match="source stream failed"):
        ContractExtractor(batch_size=1)._collect_and_write(contracts(), output)

    assert output.read_bytes() == b"stale"
    assert not (tmp_path / ".contracts.tmp.parquet").exists()


def test_multiple_batches_fail_instead_of_dropping_unknown_metadata(tmp_path) -> None:
    output = tmp_path / "contracts.parquet"
    output.write_bytes(b"stale")
    contract = FederalContract(
        contract_id="C1",
        transaction_unique_id="TX-1",
        generated_unique_award_id="CONT_AWD_1",
        metadata={"future_audit_field": "must not disappear"},
    )

    with pytest.raises(SourceDataError, match="outside the verified Parquet schema"):
        ContractExtractor(batch_size=1)._collect_and_write(
            [contract, contract.model_copy(update={"contract_id": "C2"})],
            output,
        )

    assert output.read_bytes() == b"stale"
    assert not (tmp_path / ".contracts.tmp.parquet").exists()
