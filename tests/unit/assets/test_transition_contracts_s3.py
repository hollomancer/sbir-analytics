"""Unit tests for S3-first vendor-filter sourcing in the raw_contracts asset."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sbir_etl.exceptions import FileSystemError
from tests.mocks import ContextMocks


def _config_with_paths(tmp_path: Path, s3_url: str) -> MagicMock:
    """Build a mock config whose paths resolve to tmp_path and carry an S3 url."""
    out = tmp_path / "contracts.parquet"
    dump = tmp_path / "dump"  # intentionally absent → asset bails after S3 resolution
    vendor = tmp_path / "sbir_vendor_filters.json"

    resolved = {
        "transition_contracts_output": out,
        "transition_dump_dir": dump,
        "transition_vendor_filters": vendor,
    }

    config = MagicMock()
    config.paths.resolve_path.side_effect = lambda key: resolved[key]
    config.paths.transition_vendor_filters_s3_path = s3_url
    return config, vendor


@patch("sbir_analytics.assets.transition.contracts.resolve_data_path")
@patch("sbir_analytics.assets.transition.contracts.get_config")
def test_vendor_filters_resolved_s3_first(mock_get_config, mock_resolve, tmp_path):
    """When the S3 url is set, the asset resolves it S3-first with a local fallback."""
    from sbir_analytics.assets.transition.contracts import raw_contracts

    s3_url = "s3://test-bucket/raw/transition/sbir_vendor_filters.json"
    config, vendor_local = _config_with_paths(tmp_path, s3_url)
    mock_get_config.return_value = config
    mock_resolve.return_value = tmp_path / "downloaded_filters.json"

    # The dump dir is absent, so the asset raises after the S3 resolution step —
    # enough to assert the S3-first call happened with the local fallback.
    with pytest.raises(FileSystemError):
        raw_contracts(ContextMocks.context_with_logging())

    mock_resolve.assert_called_once_with(s3_url, local_fallback=vendor_local)


@patch("sbir_analytics.assets.transition.contracts.resolve_data_path")
@patch("sbir_analytics.assets.transition.contracts.get_config")
def test_vendor_filters_local_only_when_s3_unset(mock_get_config, mock_resolve, tmp_path):
    """Empty S3 url leaves behavior unchanged — resolve_data_path is never called."""
    from sbir_analytics.assets.transition.contracts import raw_contracts

    config, _ = _config_with_paths(tmp_path, "")
    mock_get_config.return_value = config

    with pytest.raises(FileSystemError):
        raw_contracts(ContextMocks.context_with_logging())

    mock_resolve.assert_not_called()
