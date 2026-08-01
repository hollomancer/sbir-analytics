"""Tests for the contract extraction script's provenance sidecar."""

import importlib.util
import json
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
