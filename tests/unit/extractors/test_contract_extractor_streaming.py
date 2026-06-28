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


def _fake_remotezip_module_multi(
    members: dict[str, bytes],
    sizes: dict[str, int] | None = None,
) -> types.ModuleType:
    """Multi-member fake ``remotezip`` for auto-detection tests.

    ``members`` maps ``filename → gzip-compressed bytes`` used by ``open()``.
    ``sizes`` optionally overrides each entry's reported ``file_size`` — useful
    for exercising ``find_transaction_member``'s largest-first probe ordering
    without bloating the actual gzip payloads. Defaults to the blob length.
    """
    mod = types.ModuleType("remotezip")

    class _Info:
        def __init__(self, filename, file_size):
            self.filename = filename
            self.file_size = file_size

    class _FakeRemoteZip:
        def __init__(self, url):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def infolist(self):
            return [
                _Info(name, (sizes or {}).get(name, len(blob)))
                for name, blob in members.items()
            ]

        def open(self, member_name):
            return io.BytesIO(members[member_name])

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
        # The message points users at the optional 'streaming' extra.
        with pytest.raises(ImportError, match="streaming"):
            list(extractor.stream_remote_zip_member("https://x/y.zip", "m.dat.gz"))


def test_find_transaction_member_skips_wrong_layout(
    sample_vendor_filters, sample_contract_row_full
):
    """find_transaction_member skips short/wrong-shape members and picks the match.

    The decoys are declared *larger* than the real match via the ``sizes`` override
    so the largest-first probe ordering inside ``find_transaction_member`` is
    actually exercised: decoys get probed first and skipped, then the match wins.
    """
    decoy_short = gzip.compress(b"\t".join([b"x"] * 20) + b"\n")
    decoy_no_date = gzip.compress(
        ("\t".join(["123", "id1", "NOT_A_DATE", "A"] + ["x"] * 99)).encode("utf-8") + b"\n"
    )
    txn_blob = gzip.compress(("\t".join(sample_contract_row_full) + "\n").encode("utf-8"))
    members = {
        "pruned_data_store_api_dump/9999.dat.gz": decoy_short,
        "pruned_data_store_api_dump/9998.dat.gz": decoy_no_date,
        "pruned_data_store_api_dump/5183.dat.gz": txn_blob,
    }
    # Force decoys to appear larger so largest-first ordering probes them first.
    sizes = {
        "pruned_data_store_api_dump/9999.dat.gz": len(txn_blob) + 200,
        "pruned_data_store_api_dump/9998.dat.gz": len(txn_blob) + 100,
        "pruned_data_store_api_dump/5183.dat.gz": len(txn_blob),
    }

    fake = _fake_remotezip_module_multi(members, sizes=sizes)
    with patch.dict(sys.modules, {"remotezip": fake}):
        picked = ContractExtractor.find_transaction_member("https://x/y.zip")

    assert picked == "pruned_data_store_api_dump/5183.dat.gz"


def test_find_transaction_member_raises_when_none_match(sample_vendor_filters):
    """find_transaction_member raises RuntimeError when no member has the signature."""
    members = {
        "a.dat.gz": gzip.compress(b"\t".join([b"x"] * 5) + b"\n"),
        "b.dat.gz": gzip.compress(b"\t".join([b"y"] * 10) + b"\n"),
    }
    fake = _fake_remotezip_module_multi(members)
    with patch.dict(sys.modules, {"remotezip": fake}):
        with pytest.raises(RuntimeError, match="transaction_normalized signature"):
            ContractExtractor.find_transaction_member("https://x/y.zip")


def test_extract_from_remote_zip_auto_detects_member(
    tmp_path, sample_vendor_filters, sample_contract_row_full
):
    """extract_from_remote_zip(member_name=None) sniffs the zip and streams the match."""
    extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)
    decoy = gzip.compress(b"\t".join([b"x"] * 8) + b"\n")
    txn_blob = gzip.compress(("\t".join(sample_contract_row_full) + "\n").encode("utf-8"))
    members = {
        "pruned_data_store_api_dump/9999.dat.gz": decoy,
        "pruned_data_store_api_dump/5183.dat.gz": txn_blob,
    }
    out = tmp_path / "contracts.parquet"
    fake = _fake_remotezip_module_multi(members)

    with patch.dict(sys.modules, {"remotezip": fake}):
        count = extractor.extract_from_remote_zip(
            "https://x/y.zip", member_name=None, output_file=out
        )

    assert count == 1
    assert out.exists()
