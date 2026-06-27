"""Unit tests for S3-first input sourcing in the raw_contracts asset."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sbir_etl.exceptions import FileSystemError
from tests.mocks import ContextMocks


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
