"""Unit tests for S3-first input sourcing in the raw_contracts asset."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from sbir_etl.exceptions import FileSystemError
from tests.mocks import ContextMocks


def _provenance_complete_contracts() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "contract_id": ["c1"],
            "action_date": ["2023-01-01"],
            "transaction_unique_id": ["tx-1"],
            "generated_unique_award_id": ["award-1"],
            "research": [None],
            "naics_code": ["541715"],
            "product_or_service_code": ["AC13"],
        }
    )


def _base_source_provenance() -> dict[str, object]:
    return {
        "canonical_table": "rpt.transaction_search",
        "physical_table": "rpt.transaction_search_fpds",
        "member": "9247.dat.gz",
        "ordered_columns_sha256": "a" * 64,
        "column_count": 300,
    }


def _write_reusable_checks(out: Path, dump: Path, vendor: Path) -> None:
    from sbir_analytics.assets.transition.contracts import (
        SOURCE_PROVENANCE_VERSION,
        _file_sha256,
    )

    provenance = {
        **_base_source_provenance(),
        "toc_sha256": _file_sha256(dump / "toc.dat"),
        "vendor_filter_sha256": _file_sha256(vendor),
        "output_sha256": _file_sha256(out),
        "provenance_version": SOURCE_PROVENANCE_VERSION,
    }
    out.with_suffix(".checks.json").write_text(
        json.dumps({"source_provenance": provenance}), encoding="utf-8"
    )


def test_source_provenance_status_detects_input_drift() -> None:
    from sbir_analytics.assets.transition.contracts import source_provenance_status

    provenance = {
        **_base_source_provenance(),
        "toc_sha256": "b" * 64,
        "vendor_filter_sha256": "c" * 64,
        "output_sha256": "d" * 64,
        "provenance_version": 1,
    }
    status = source_provenance_status(
        provenance,
        toc_sha256="b" * 64,
        vendor_filter_sha256="changed",
        output_sha256="d" * 64,
        table_files=None,
    )

    assert status["complete"] is False
    assert "vendor_filter_sha256" in status["mismatches"]


def _config_with_paths(tmp_path: Path, *, vendor_s3: str = "", dump_s3: str = ""):
    """Build a mock config whose paths resolve to tmp_path and carry S3 settings.

    The dump dir is intentionally absent so the asset bails (FileSystemError) right
    after the S3-sourcing steps — enough to assert what those steps did.
    """
    out = tmp_path / "contracts.parquet"
    dump = tmp_path / "dump"  # absent
    vendor = tmp_path / "sbir_vendor_filters.json"

    resolved = {
        "transition_contracts_output": out,
        "transition_dump_dir": dump,
        "transition_vendor_filters": vendor,
    }

    config = MagicMock()
    config.paths.resolve_path.side_effect = lambda key: resolved[key]
    config.paths.transition_vendor_filters_s3_path = vendor_s3
    config.paths.transition_dump_s3_prefix = dump_s3
    return config, vendor, dump


@patch("sbir_analytics.assets.transition.contracts.resolve_data_path")
@patch("sbir_analytics.assets.transition.contracts.get_config")
def test_vendor_filters_resolved_s3_first(mock_get_config, mock_resolve, tmp_path):
    """When the S3 url is set, the asset resolves it S3-first with a local fallback."""
    from sbir_analytics.assets.transition.contracts import raw_contracts

    s3_url = "s3://test-bucket/raw/transition/sbir_vendor_filters.json"
    config, vendor_local, _ = _config_with_paths(tmp_path, vendor_s3=s3_url)
    mock_get_config.return_value = config
    mock_resolve.return_value = tmp_path / "downloaded_filters.json"

    with pytest.raises(FileSystemError):
        raw_contracts(ContextMocks.context_with_logging())

    mock_resolve.assert_called_once_with(s3_url, local_fallback=vendor_local)


@patch("sbir_analytics.assets.transition.contracts.sync_s3_prefix_to_dir")
@patch("sbir_analytics.assets.transition.contracts.resolve_data_path")
@patch("sbir_analytics.assets.transition.contracts.get_config")
def test_local_only_when_s3_unset(mock_get_config, mock_resolve, mock_sync, tmp_path):
    """Empty S3 settings leave behavior unchanged — no S3 calls are made."""
    from sbir_analytics.assets.transition.contracts import raw_contracts

    config, _, _ = _config_with_paths(tmp_path)
    mock_get_config.return_value = config

    with pytest.raises(FileSystemError):
        raw_contracts(ContextMocks.context_with_logging())

    mock_resolve.assert_not_called()
    mock_sync.assert_not_called()


@patch("sbir_analytics.assets.transition.contracts.sync_s3_prefix_to_dir")
@patch("sbir_analytics.assets.transition.contracts.get_config")
def test_dump_synced_selectively_with_table_files(
    mock_get_config, mock_sync, tmp_path, monkeypatch
):
    """With a dump prefix + TABLE_FILES, the asset syncs only toc.dat + those files."""
    from sbir_analytics.assets.transition.contracts import raw_contracts

    prefix = "s3://test-bucket/raw/transition/pruned_data_store_api_dump/"
    config, _, dump_local = _config_with_paths(tmp_path, dump_s3=prefix)
    mock_get_config.return_value = config
    monkeypatch.setenv("SBIR_ETL__TRANSITION__CONTRACTS__TABLE_FILES", "best.dat.gz")

    with pytest.raises(FileSystemError):
        raw_contracts(ContextMocks.context_with_logging())

    mock_sync.assert_called_once()
    args, kwargs = mock_sync.call_args
    assert args[0] == prefix
    assert args[1] == dump_local
    # Selective: only the named table file plus the table-of-contents.
    assert kwargs["include"] == ["toc.dat", "best.dat.gz"]


@patch("sbir_analytics.assets.transition.contracts.upload_file_to_s3")
@patch("sbir_analytics.assets.transition.contracts.get_config")
def test_output_uploaded_to_s3_when_configured(mock_get_config, mock_upload, tmp_path):
    """When the output S3 url is set, the written parquet is uploaded after extraction."""
    from sbir_analytics.assets.transition.contracts import raw_contracts

    # Happy path: dump dir + vendor file exist, output parquet already present
    # (so extraction is skipped), and an output S3 url is configured.
    out = tmp_path / "contracts.parquet"
    dump = tmp_path / "dump"
    dump.mkdir()
    (dump / "toc.dat").write_bytes(b"fixture toc")
    vendor = tmp_path / "sbir_vendor_filters.json"
    vendor.write_text('{"uei": [], "duns": [], "company_names": []}')
    _provenance_complete_contracts().to_parquet(out)
    _write_reusable_checks(out, dump, vendor)

    resolved = {
        "transition_contracts_output": out,
        "transition_dump_dir": dump,
        "transition_vendor_filters": vendor,
    }
    s3_out = "s3://bucket/raw/transition/contracts_ingestion.parquet"
    config = MagicMock()
    config.paths.resolve_path.side_effect = lambda key: resolved[key]
    config.paths.transition_vendor_filters_s3_path = ""
    config.paths.transition_dump_s3_prefix = ""
    config.paths.transition_contracts_output_s3_path = s3_out
    mock_get_config.return_value = config

    raw_contracts(ContextMocks.context_with_logging())

    mock_upload.assert_called_once_with(out, s3_out)


@patch("sbir_analytics.assets.transition.contracts.ContractExtractor")
@patch("sbir_analytics.assets.transition.contracts.get_config")
def test_stale_cached_parquet_forces_reextraction_and_surfaces_provenance(
    mock_get_config, mock_extractor_cls, tmp_path
):
    """An old parquet without raw source columns is never silently reused."""
    from sbir_analytics.assets.transition.contracts import raw_contracts

    out = tmp_path / "contracts.parquet"
    pd.DataFrame({"contract_id": ["stale"]}).to_parquet(out)
    dump = tmp_path / "dump"
    dump.mkdir()
    (dump / "toc.dat").write_bytes(b"fixture toc")
    vendor = tmp_path / "sbir_vendor_filters.json"
    vendor.write_text('{"uei": [], "duns": [], "company_names": []}')

    resolved = {
        "transition_contracts_output": out,
        "transition_dump_dir": dump,
        "transition_vendor_filters": vendor,
    }
    config = MagicMock()
    config.paths.resolve_path.side_effect = lambda key: resolved[key]
    config.paths.transition_vendor_filters_s3_path = ""
    config.paths.transition_dump_s3_prefix = ""
    config.paths.transition_contracts_output_s3_path = ""
    mock_get_config.return_value = config

    extractor = mock_extractor_cls.return_value
    extractor.stats = {"source_table": "rpt.transaction_search"}
    extractor.source_provenance = _base_source_provenance()

    def _replace_stale(*, dump_dir, output_file, table_files):
        assert dump_dir == dump
        assert table_files is None
        _provenance_complete_contracts().to_parquet(output_file)
        return 1

    extractor.extract_from_dump.side_effect = _replace_stale

    raw_contracts(ContextMocks.context_with_logging())

    extractor.extract_from_dump.assert_called_once()
    checks = json.loads(out.with_suffix(".checks.json").read_text())
    assert checks["provenance"]["complete"] is True
    assert checks["provenance"]["missing_columns"] == []
    assert checks["source_provenance"]["canonical_table"] == "rpt.transaction_search"


@patch("sbir_analytics.assets.transition.contracts.ContractExtractor")
@patch("sbir_analytics.assets.transition.contracts.get_config")
def test_reextracted_output_without_provenance_fails_explicitly(
    mock_get_config, mock_extractor_cls, tmp_path
):
    """A failed refresh cannot leave an old-format file looking usable."""
    from sbir_analytics.assets.transition.contracts import raw_contracts

    out = tmp_path / "contracts.parquet"
    pd.DataFrame({"contract_id": ["stale"]}).to_parquet(out)
    dump = tmp_path / "dump"
    dump.mkdir()
    (dump / "toc.dat").write_bytes(b"fixture toc")
    vendor = tmp_path / "sbir_vendor_filters.json"
    vendor.write_text('{"uei": [], "duns": [], "company_names": []}')

    resolved = {
        "transition_contracts_output": out,
        "transition_dump_dir": dump,
        "transition_vendor_filters": vendor,
    }
    config = MagicMock()
    config.paths.resolve_path.side_effect = lambda key: resolved[key]
    config.paths.transition_vendor_filters_s3_path = ""
    config.paths.transition_dump_s3_prefix = ""
    config.paths.transition_contracts_output_s3_path = ""
    mock_get_config.return_value = config
    extractor = mock_extractor_cls.return_value
    extractor.stats = {}
    extractor.source_provenance = {}
    extractor.extract_from_dump.return_value = 0

    with pytest.raises(FileSystemError, match="missing required raw USAspending provenance"):
        raw_contracts(ContextMocks.context_with_logging())

    extractor.extract_from_dump.assert_called_once()
