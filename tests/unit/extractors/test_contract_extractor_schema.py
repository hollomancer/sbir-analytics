"""Fail-closed schema and named-row tests for USAspending contract extraction."""

import gzip
from pathlib import Path

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
    "piid",
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


def test_resolver_rejects_missing_provenance_column() -> None:
    columns = tuple(column for column in COLUMNS if column != "research")
    with pytest.raises(ArchiveSchemaError, match="research"):
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

    provenance = ContractExtractor._provenance(source)

    assert provenance["canonical_table"] == "rpt.transaction_search"
    assert provenance["physical_table"] == "rpt.transaction_search_fpds"
    assert provenance["member"] == "9247.dat.gz"
    assert provenance["column_count"] == len(COLUMNS)
    assert len(str(provenance["ordered_columns_sha256"])) == 64


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
