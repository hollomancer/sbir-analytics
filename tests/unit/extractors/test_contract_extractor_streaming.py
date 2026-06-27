"""Tests for the streaming (remote-zip) contract extraction path.

Validates the transport-agnostic parser and the remote-zip member streaming
offline — a fake ``remotezip`` module is injected so no network or real
USAspending endpoint is touched.
"""

import gzip
import io
import sys
import types
from unittest.mock import patch

import pytest

from sbir_etl.extractors.contract_extractor import ContractExtractor


def _row_text(*rows: list[str]) -> str:
    """Join 103-column rows into tab-delimited, newline-separated text."""
    return "\n".join("\t".join(r) for r in rows)


def _fake_remotezip_module(member_gzip: bytes) -> types.ModuleType:
    """A stand-in ``remotezip`` whose RemoteZip.open() yields gzip member bytes."""
    mod = types.ModuleType("remotezip")

    class _FakeRemoteZip:
        def __init__(self, url):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def open(self, member_name):  # used as a context manager
            return io.BytesIO(member_gzip)

    mod.RemoteZip = _FakeRemoteZip  # type: ignore[attr-defined]
    return mod


def test_parse_lines_filters_and_parses(
    sample_vendor_filters, sample_contract_row_full, sample_grant_row
):
    """The shared parser keeps vendor-matching contracts and drops grants."""
    extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)
    lines = [
        "\t".join(sample_contract_row_full),  # matches (UEI ABC123456789, contract)
        "\t".join(sample_grant_row),  # grant → filtered out
    ]

    contracts = list(extractor._parse_lines(lines, "test"))

    assert len(contracts) == 1
    assert contracts[0].contract_id == "SPE4A924D0001"
    assert contracts[0].vendor_uei == "ABC123456789"  # pragma: allowlist secret


def test_stream_remote_zip_member_streams_and_parses(
    sample_vendor_filters, sample_contract_row_full, sample_grant_row
):
    """stream_remote_zip_member: RemoteZip → open member → gunzip → parse."""
    extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)
    member_gzip = gzip.compress(
        _row_text(sample_contract_row_full, sample_grant_row).encode("utf-8")
    )
    fake_mod = _fake_remotezip_module(member_gzip)

    with patch.dict(sys.modules, {"remotezip": fake_mod}):
        contracts = list(
            extractor.stream_remote_zip_member(
                "https://files.usaspending.gov/database_download/usaspending-db-subset_20240101.zip",
                "5530.dat.gz",
            )
        )

    assert len(contracts) == 1
    assert contracts[0].contract_id == "SPE4A924D0001"


def test_extract_from_remote_zip_writes_parquet(
    tmp_path, sample_vendor_filters, sample_contract_row_full, sample_grant_row
):
    """extract_from_remote_zip streams, filters, and writes the Parquet output."""
    extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)
    member_gzip = gzip.compress(
        _row_text(sample_contract_row_full, sample_grant_row).encode("utf-8")
    )
    out = tmp_path / "contracts.parquet"

    with patch.dict(sys.modules, {"remotezip": _fake_remotezip_module(member_gzip)}):
        count = extractor.extract_from_remote_zip(
            "https://files.usaspending.gov/x.zip", "5530.dat.gz", out
        )

    assert count == 1
    assert out.exists()
    assert out.stat().st_size > 0


def test_stream_remote_zip_member_missing_dependency_raises(sample_vendor_filters):
    """A clear ImportError is raised when remotezip is not installed."""
    extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)
    # Force the lazy `from remotezip import RemoteZip` to fail.
    with patch.dict(sys.modules, {"remotezip": None}):
        with pytest.raises(ImportError, match="remotezip"):
            list(extractor.stream_remote_zip_member("https://x/y.zip", "m.dat.gz"))
