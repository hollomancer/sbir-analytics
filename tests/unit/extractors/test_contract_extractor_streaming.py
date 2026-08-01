"""Offline tests for schema-verified remote contract streaming."""

import gzip
import io
import sys
import types
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import pytest

from sbir_etl.extractors.contract_extractor import (
    ArchiveSchemaError,
    ContractExtractor,
    TransactionSource,
)


pytestmark = pytest.mark.fast


def _row_text(
    rows: Sequence[Mapping[str, str | None]],
    columns: Sequence[str],
) -> str:
    return "\n".join(
        "\t".join(r"\N" if row.get(column) is None else str(row[column]) for column in columns)
        for row in rows
    )


def _fake_remotezip_module(members: Mapping[str, bytes]) -> types.ModuleType:
    """Return a stand-in remotezip module backed by named in-memory members."""
    module = types.ModuleType("remotezip")

    class _Info:
        def __init__(self, filename: str) -> None:
            self.filename = filename
            self.file_size = len(members[filename])

    class _FakeRemoteZip:
        def __init__(self, url: str) -> None:
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> Literal[False]:
            return False

        def infolist(self) -> list[_Info]:
            return [_Info(name) for name in members]

        def open(self, member_name: str) -> io.BytesIO:
            return io.BytesIO(members[member_name])

    module.RemoteZip = _FakeRemoteZip  # type: ignore[attr-defined]
    return module


def _toc() -> str:
    return "9247; 0 999 TABLE DATA rpt transaction_search_fpds usaspending\n"


def _schema(columns: Sequence[str]) -> str:
    definitions = ",\n".join(f"    {column} text" for column in columns)
    return (
        f"CREATE TABLE rpt.transaction_search (\n{definitions}\n) PARTITION BY LIST (is_fpds);\n"
        "CREATE TABLE rpt.transaction_search_fpds PARTITION OF rpt.transaction_search "
        "FOR VALUES IN (true);\n"
    )


def _copy(columns: Sequence[str]) -> str:
    return f"COPY rpt.transaction_search_fpds ({', '.join(columns)}) FROM stdin;\n\\.\n"


def _source(columns: Sequence[str]) -> TransactionSource:
    return TransactionSource(
        member_name="archive/9247.dat.gz",
        columns=tuple(columns),
        relation="rpt.transaction_search_fpds",
        fpds_only=True,
    )


def test_parse_lines_filters_non_fpds_and_unmatched_vendors(
    sample_vendor_filters,
    sample_contract_row_full,
    sample_grant_row,
    contract_copy_columns,
    serialize_contract_row,
) -> None:
    unmatched = dict(sample_contract_row_full)
    unmatched.update(
        {
            "transaction_unique_id": "TX-UNMATCHED",
            "recipient_uei": "NOPE00000001",
            "recipient_unique_id": "000000000",
            "recipient_name": "UNMATCHED COMPANY",
        }
    )
    lines = [
        serialize_contract_row(sample_contract_row_full, contract_copy_columns),
        serialize_contract_row(unmatched, contract_copy_columns),
        serialize_contract_row(sample_grant_row, contract_copy_columns),
    ]
    extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)

    contracts = list(
        extractor._parse_lines(
            lines,
            "parent.dat.gz",
            contract_copy_columns,
            fpds_only=False,
        )
    )

    assert [contract.contract_id for contract in contracts] == ["SPE4A924D0001"]
    assert extractor.stats == {
        "records_scanned": 3,
        "contracts_found": 2,
        "vendor_matches": 1,
        "records_extracted": 1,
        "parent_relationships": 0,
        "child_relationships": 0,
        "idv_parents": 0,
        "unique_parent_ids": 0,
        "unique_idv_parents": 0,
    }


def test_stream_remote_zip_member_streams_verified_named_rows(
    sample_vendor_filters,
    sample_contract_row_full,
    contract_copy_columns,
) -> None:
    member_name = "archive/9247.dat.gz"
    payload = _row_text([sample_contract_row_full], contract_copy_columns).encode()
    extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)

    with patch.dict(
        sys.modules,
        {"remotezip": _fake_remotezip_module({member_name: gzip.compress(payload)})},
    ):
        contracts = list(
            extractor.stream_remote_zip_member(
                "https://files.usaspending.gov/database_download/archive.zip",
                member_name,
                contract_copy_columns,
                fpds_only=True,
            )
        )

    assert [contract.contract_id for contract in contracts] == ["SPE4A924D0001"]
    assert contracts[0].vendor_uei == "ABC123456789"  # pragma: allowlist secret


def test_extract_from_remote_zip_resolves_then_writes(
    tmp_path,
    monkeypatch,
    sample_vendor_filters,
    sample_contract_row_full,
    contract_copy_columns,
) -> None:
    source = _source(contract_copy_columns)
    payload = _row_text([sample_contract_row_full], contract_copy_columns).encode()
    output = tmp_path / "contracts.parquet"

    monkeypatch.setattr(
        ContractExtractor,
        "_resolve_remote_source",
        classmethod(lambda cls, url: source),
    )
    monkeypatch.setattr(
        "sbir_etl.utils.data.file_io.save_dataframe_parquet",
        lambda frame, path, **kwargs: path.write_bytes(b"verified-parquet"),
    )
    extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)

    with patch.dict(
        sys.modules,
        {"remotezip": _fake_remotezip_module({source.member_name: gzip.compress(payload)})},
    ):
        count = extractor.extract_from_remote_zip(
            "https://files.usaspending.gov/archive.zip",
            member_name=None,
            output_file=output,
        )

    assert count == 1
    assert output.read_bytes() == b"verified-parquet"
    assert extractor.source_provenance["physical_table"] == source.relation
    assert extractor.source_provenance["member"] == source.member_name


def test_remote_resolution_uses_toc_selected_member_not_file_size(
    monkeypatch,
    contract_copy_columns,
) -> None:
    members = {
        "archive/toc.dat": b"archive-owned-toc",
        "archive/9247.dat.gz": gzip.compress(b""),
        # Deliberately larger: selection must come from metadata, never size/sniffing.
        "archive/9999.dat.gz": b"x" * 10000,
    }
    observed_calls: list[tuple[str, ...]] = []

    def fake_pg_restore(dump_dir: Path, *arguments: str) -> str:
        observed_calls.append(arguments)
        assert (dump_dir / "toc.dat").is_file()
        if "--list" in arguments:
            return _toc()
        if "--schema-only" in arguments:
            return _schema(contract_copy_columns)
        if "--data-only" in arguments:
            return _copy(contract_copy_columns)
        raise AssertionError(f"Unexpected pg_restore arguments: {arguments!r}")

    monkeypatch.setattr(
        ContractExtractor,
        "_run_pg_restore",
        staticmethod(fake_pg_restore),
    )

    with patch.dict(sys.modules, {"remotezip": _fake_remotezip_module(members)}):
        source = ContractExtractor._resolve_remote_source("https://example.test/archive.zip")

    assert source == _source(contract_copy_columns)
    assert any("--list" in arguments for arguments in observed_calls)
    assert any("--schema-only" in arguments for arguments in observed_calls)
    assert any("--data-only" in arguments for arguments in observed_calls)


def test_remote_resolution_requires_exactly_one_toc() -> None:
    members = {
        "first/toc.dat": b"one",
        "second/toc.dat": b"two",
        "first/9247.dat.gz": gzip.compress(b""),
    }

    with patch.dict(sys.modules, {"remotezip": _fake_remotezip_module(members)}):
        with pytest.raises(ArchiveSchemaError, match="exactly one toc.dat"):
            ContractExtractor._resolve_remote_source("https://example.test/archive.zip")


def test_configured_remote_member_must_match_verified_metadata(
    tmp_path,
    monkeypatch,
    contract_copy_columns,
) -> None:
    source = _source(contract_copy_columns)
    monkeypatch.setattr(
        ContractExtractor,
        "_resolve_remote_source",
        classmethod(lambda cls, url: source),
    )

    with pytest.raises(ArchiveSchemaError, match="does not match TOC-selected"):
        ContractExtractor().extract_from_remote_zip(
            "https://example.test/archive.zip",
            member_name="archive/largest-file.dat.gz",
            output_file=tmp_path / "contracts.parquet",
        )


def test_find_transaction_member_returns_metadata_selection(
    monkeypatch,
    contract_copy_columns,
) -> None:
    source = _source(contract_copy_columns)
    monkeypatch.setattr(
        ContractExtractor,
        "_resolve_remote_source",
        classmethod(lambda cls, url: source),
    )

    assert ContractExtractor.find_transaction_member("https://example.test/archive.zip") == (
        "archive/9247.dat.gz"
    )


def test_stream_remote_zip_member_missing_dependency_raises(
    sample_vendor_filters,
    contract_copy_columns,
) -> None:
    extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)

    with patch.dict(sys.modules, {"remotezip": None}):
        with pytest.raises(ImportError, match="streaming"):
            list(
                extractor.stream_remote_zip_member(
                    "https://example.test/archive.zip",
                    "archive/9247.dat.gz",
                    contract_copy_columns,
                    fpds_only=True,
                )
            )
