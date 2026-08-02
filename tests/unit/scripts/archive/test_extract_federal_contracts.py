"""Tests for the contract extraction script's provenance sidecar."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


SCRIPT_PATH = Path(__file__).parents[4] / "scripts" / "archive" / "extract_federal_contracts.py"
_SPEC = importlib.util.spec_from_file_location("extract_federal_contracts", SCRIPT_PATH)
assert _SPEC and _SPEC.loader
extract_federal_contracts = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(extract_federal_contracts)


pytestmark = pytest.mark.fast


def _source_provenance() -> dict[str, object]:
    return {
        "canonical_table": "rpt.transaction_search",
        "physical_table": "rpt.transaction_search_fpds",
        "member": "archive/9247.dat.gz",
        "ordered_columns_sha256": "a" * 64,
        "column_count": 300,
        "toc_sha256": "b" * 64,
    }


def test_remote_checks_bind_verified_parquet(tmp_path) -> None:
    output = tmp_path / "contracts_ingestion.parquet"
    expected_frame = pd.DataFrame({"contract_id": ["contract-1"]})
    expected_frame.to_parquet(output)
    vendor_filter = tmp_path / "sbir_vendor_filters.json"
    vendor_filter.write_text('{"uei": ["ABC123456789"]}', encoding="utf-8")
    vendor_sha256 = extract_federal_contracts._file_sha256(vendor_filter)
    extractor = SimpleNamespace(
        source_provenance=_source_provenance(),
        stats={"invalid_performance_periods": 2},
    )

    checks_path = extract_federal_contracts.write_contract_provenance_checks(
        extractor=extractor,
        output_file=output,
        vendor_filter_file=vendor_filter,
        expected_vendor_filter_sha256=vendor_sha256,
        total_rows=1,
        source={"remote_zip": "https://files.usaspending.gov/database_download/archive.zip"},
    )

    checks = json.loads(checks_path.read_text(encoding="utf-8"))
    assert set(checks["source_provenance"]) == extract_federal_contracts.SOURCE_PROVENANCE_KEYS
    assert checks["source_provenance"]["vendor_filter_sha256"] == vendor_sha256
    assert checks["source_provenance"]["output_sha256"] == (
        extract_federal_contracts._file_sha256(output)
    )
    assert checks["source"]["remote_zip"].startswith("https://files.usaspending.gov/")
    assert checks["extraction_stats"]["invalid_performance_periods"] == 2


def test_checks_refuse_vendor_filter_changed_during_extraction(tmp_path) -> None:
    output = tmp_path / "contracts_ingestion.parquet"
    pd.DataFrame({"contract_id": ["contract-1"]}).to_parquet(output)
    vendor_filter = tmp_path / "sbir_vendor_filters.json"
    vendor_filter.write_text('{"uei": ["ABC123456789"]}', encoding="utf-8")
    original_sha256 = extract_federal_contracts._file_sha256(vendor_filter)
    vendor_filter.write_text('{"uei": ["CHANGED000001"]}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="changed during contract extraction"):
        extract_federal_contracts.write_contract_provenance_checks(
            extractor=SimpleNamespace(source_provenance=_source_provenance(), stats={}),
            output_file=output,
            vendor_filter_file=vendor_filter,
            expected_vendor_filter_sha256=original_sha256,
            total_rows=1,
            source={"remote_zip": "https://files.usaspending.gov/database_download/archive.zip"},
        )

    assert not output.with_suffix(".checks.json").exists()


def test_checks_require_archive_toc_fingerprint(tmp_path) -> None:
    output = tmp_path / "contracts_ingestion.parquet"
    pd.DataFrame({"contract_id": ["contract-1"]}).to_parquet(output)
    vendor_filter = tmp_path / "sbir_vendor_filters.json"
    vendor_filter.write_text('{"uei": ["ABC123456789"]}', encoding="utf-8")
    source_provenance = _source_provenance()
    source_provenance.pop("toc_sha256")

    with pytest.raises(RuntimeError, match=r"missing fields: \['toc_sha256'\]"):
        extract_federal_contracts.write_contract_provenance_checks(
            extractor=SimpleNamespace(source_provenance=source_provenance, stats={}),
            output_file=output,
            vendor_filter_file=vendor_filter,
            expected_vendor_filter_sha256=extract_federal_contracts._file_sha256(vendor_filter),
            total_rows=1,
            source={"remote_zip": "https://files.usaspending.gov/database_download/archive.zip"},
        )

    assert not output.with_suffix(".checks.json").exists()


def test_award_archive_checks_preserve_archive_provenance(tmp_path) -> None:
    output = tmp_path / "contracts_ingestion.parquet"
    pd.DataFrame({"contract_id": ["contract-1"]}).to_parquet(output)
    vendor_filter = tmp_path / "sbir_vendor_filters.json"
    vendor_filter.write_text('{"uei": ["ABC123456789"]}', encoding="utf-8")
    archive_provenance = {
        "source_kind": extract_federal_contracts.AWARD_ARCHIVE_SOURCE_KIND,
        "canonical_table": "award_data_archive.contracts_full",
        "physical_table": "award_data_archive.contracts_full",
        "archive_file": "FY2026_All_Contracts_Full_20260706.zip",
        "archive_sha256": "a" * 64,
        "archive_size_bytes": 100,
        "member_count": 4,
        "member_manifest_sha256": "b" * 64,
        "ordered_columns_sha256": "c" * 64,
        "column_count": 297,
        "provenance_version": extract_federal_contracts.AWARD_ARCHIVE_PROVENANCE_VERSION,
    }

    checks_path = extract_federal_contracts.write_contract_provenance_checks(
        extractor=SimpleNamespace(source_provenance=archive_provenance, stats={}),
        output_file=output,
        vendor_filter_file=vendor_filter,
        expected_vendor_filter_sha256=extract_federal_contracts._file_sha256(vendor_filter),
        total_rows=1,
        source={"award_archive": archive_provenance["archive_file"]},
    )

    checks = json.loads(checks_path.read_text(encoding="utf-8"))
    provenance = checks["source_provenance"]
    assert set(provenance) == extract_federal_contracts.AWARD_ARCHIVE_PROVENANCE_KEYS
    assert provenance["provenance_version"] == 2
    assert provenance["archive_sha256"] == "a" * 64


def test_sequential_remote_member_sha_does_not_require_parallel_fields(tmp_path) -> None:
    output = tmp_path / "contracts_ingestion.parquet"
    pd.DataFrame({"contract_id": ["contract-1"]}).to_parquet(output)
    vendor_filter = tmp_path / "sbir_vendor_filters.json"
    vendor_filter.write_text('{"uei": ["ABC123456789"]}', encoding="utf-8")
    source_provenance = {**_source_provenance(), "member_sha256": "c" * 64}

    checks_path = extract_federal_contracts.write_contract_provenance_checks(
        extractor=SimpleNamespace(source_provenance=source_provenance, stats={}),
        output_file=output,
        vendor_filter_file=vendor_filter,
        expected_vendor_filter_sha256=extract_federal_contracts._file_sha256(vendor_filter),
        total_rows=1,
        source={"remote_zip": "https://files.usaspending.gov/archive.zip"},
    )

    checks = json.loads(checks_path.read_text(encoding="utf-8"))
    assert checks["source_provenance"]["member_sha256"] == "c" * 64


def test_parallel_range_cli_forwards_only_explicit_replica_urls(
    tmp_path,
    monkeypatch,
) -> None:
    vendor_filter = tmp_path / "sbir_vendor_filters.json"
    vendor_filter.write_text('{"uei": ["ABC123456789"]}', encoding="utf-8")
    output = tmp_path / "contracts.parquet"
    observed: dict[str, object] = {}

    class _Paths:
        @staticmethod
        def resolve_path(name: str) -> Path:
            assert name == "transition_vendor_filters"
            return vendor_filter

    class _Extractor:
        source_provenance = _source_provenance()
        stats: dict[str, int] = {}

        def extract_from_remote_zip(self, **kwargs) -> int:
            observed.update(kwargs)
            output.write_bytes(b"parquet")
            return 1

    monkeypatch.setattr(
        extract_federal_contracts, "get_config", lambda: SimpleNamespace(paths=_Paths())
    )
    monkeypatch.setattr(
        extract_federal_contracts, "ContractExtractor", lambda **kwargs: _Extractor()
    )
    monkeypatch.setattr(
        extract_federal_contracts,
        "write_contract_provenance_checks",
        lambda **kwargs: output.with_suffix(".checks.json"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "extract_federal_contracts.py",
            "--remote-zip",
            "https://canonical.example.test/archive.zip",
            "--parallel-range",
            "--parallel-range-replica",
            "https://replica-one.example.test/archive.zip",
            "--parallel-range-replica",
            "https://replica-two.example.test/archive.zip",
            "--output",
            str(output),
        ],
    )

    extract_federal_contracts.main()

    assert observed == {
        "zip_url": "https://canonical.example.test/archive.zip",
        "member_name": None,
        "output_file": output,
        "parallel_range": True,
        "replica_urls": [
            "https://replica-one.example.test/archive.zip",
            "https://replica-two.example.test/archive.zip",
        ],
    }


def test_parallel_range_replica_cli_requires_explicit_parallel_mode(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "extract_federal_contracts.py",
            "--remote-zip",
            "https://canonical.example.test/archive.zip",
            "--parallel-range-replica",
            "https://replica.example.test/archive.zip",
        ],
    )

    with pytest.raises(SystemExit, match="2"):
        extract_federal_contracts.main()
