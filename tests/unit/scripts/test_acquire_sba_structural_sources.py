"""Tests for the SBA structural-comparison source acquisition command."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from scripts.data.acquire_sba_structural_sources import (
    SourceAcquisitionError,
    acquire_sources,
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_manifest(
    path: Path,
    *,
    source_bytes: bytes,
    table_bytes: bytes,
    allowed: bool = True,
) -> None:
    manifest = {
        "schema_version": 1,
        "capture_gate": {
            "allowed": allowed,
            "blockers": [] if allowed else ["Source review is incomplete."],
        },
        "sources": [
            {
                "source_id": "source-one",
                "durable_uri": "https://example.test/source.csv",
                "local_path": "data/source.csv",
                "sha256": _sha256(source_bytes),
                "size_bytes": len(source_bytes),
            }
        ],
        "captured_tables": [
            {
                "source_id": "table-one",
                "path": "studies/table.csv",
                "sha256": _sha256(table_bytes),
                "size_bytes": len(table_bytes),
            }
        ],
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_acquire_sources_downloads_then_verifies_complete_bundle(tmp_path: Path) -> None:
    source_bytes = b"a,b\n1,2\n"
    table_bytes = b"state,count\nAK,1\n"
    manifest_path = tmp_path / "source-manifest.json"
    _write_manifest(
        manifest_path,
        source_bytes=source_bytes,
        table_bytes=table_bytes,
    )
    table_path = tmp_path / "studies/table.csv"
    table_path.parent.mkdir(parents=True)
    table_path.write_bytes(table_bytes)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=source_bytes))

    report = acquire_sources(manifest_path, tmp_path, transport=transport)

    assert (tmp_path / "data/source.csv").read_bytes() == source_bytes
    assert report["sources"][0]["verified"] is True
    assert report["captured_tables"][0]["sha256"] == _sha256(table_bytes)


def test_acquire_sources_refuses_closed_capture_gate(tmp_path: Path) -> None:
    manifest_path = tmp_path / "source-manifest.json"
    _write_manifest(
        manifest_path,
        source_bytes=b"source",
        table_bytes=b"table",
        allowed=False,
    )

    with pytest.raises(SourceAcquisitionError, match="acquisition gate is closed"):
        acquire_sources(manifest_path, tmp_path)


def test_acquire_sources_refuses_tampered_existing_file(tmp_path: Path) -> None:
    source_bytes = b"expected"
    table_bytes = b"table"
    manifest_path = tmp_path / "source-manifest.json"
    _write_manifest(
        manifest_path,
        source_bytes=source_bytes,
        table_bytes=table_bytes,
    )
    source_path = tmp_path / "data/source.csv"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"tampered")
    table_path = tmp_path / "studies/table.csv"
    table_path.parent.mkdir(parents=True)
    table_path.write_bytes(table_bytes)

    with pytest.raises(SourceAcquisitionError, match="SHA-256 mismatch"):
        acquire_sources(manifest_path, tmp_path)


def test_acquire_sources_does_not_publish_bad_download(tmp_path: Path) -> None:
    source_bytes = b"expected"
    table_bytes = b"table"
    manifest_path = tmp_path / "source-manifest.json"
    _write_manifest(
        manifest_path,
        source_bytes=source_bytes,
        table_bytes=table_bytes,
    )
    table_path = tmp_path / "studies/table.csv"
    table_path.parent.mkdir(parents=True)
    table_path.write_bytes(table_bytes)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"wrong"))

    with pytest.raises(SourceAcquisitionError, match="downloaded byte count mismatch"):
        acquire_sources(manifest_path, tmp_path, transport=transport)

    assert not (tmp_path / "data/source.csv").exists()
    assert list((tmp_path / "data").glob("*.part")) == []
