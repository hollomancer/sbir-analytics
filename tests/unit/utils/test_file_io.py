"""Unit tests for file I/O utilities."""

import hashlib
import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest


pytestmark = pytest.mark.fast

from sbir_etl.utils.data.file_io import (
    file_sha256,
    file_sha256_or_none,
    read_parquet_or_ndjson,
    save_dataframe_parquet,
    sha256_bytes,
    write_json,
    write_json_atomic,
    write_ndjson,
)


@pytest.fixture
def sample_dataframe():
    return pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_save_dataframe_parquet_success(temp_dir, sample_dataframe):
    """Test successful Parquet save."""
    path = temp_dir / "test.parquet"
    assert save_dataframe_parquet(sample_dataframe, path) == path
    assert path.exists()

    # Verify can read back
    df = pd.read_parquet(path)
    assert len(df) == 3
    assert list(df.columns) == ["a", "b"]


def test_save_dataframe_parquet_fallback_to_ndjson(temp_dir, sample_dataframe, monkeypatch):
    """The NDJSON fallback must report where it actually wrote.

    The fallback is handled inside the helper rather than raised, so a caller
    that keeps using the Parquet path it passed in ends up pointing at a file
    this function deleted.
    """

    path = temp_dir / "test.parquet"

    def _explode(*args, **kwargs):
        raise OSError("simulated parquet engine failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", _explode)

    written = save_dataframe_parquet(sample_dataframe, path)

    assert written == temp_dir / "test.ndjson"
    assert written.exists()
    assert not path.exists(), "stale Parquet must be removed so readers find the NDJSON"

    records = [json.loads(line) for line in written.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 3
    assert set(records[0]) == {"a", "b"}


def test_save_dataframe_parquet_reraises_when_fallback_disabled(
    temp_dir, sample_dataframe, monkeypatch
):
    """With the fallback disabled the caller owns the failure."""

    def _explode(*args, **kwargs):
        raise OSError("simulated parquet engine failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", _explode)

    with pytest.raises(OSError, match="simulated parquet engine failure"):
        save_dataframe_parquet(
            sample_dataframe, temp_dir / "test.parquet", fallback_to_ndjson=False
        )


def test_write_json_atomic(temp_dir):
    """Test atomic JSON write."""
    path = temp_dir / "test.json"
    data = {"key": "value", "number": 42}

    write_json_atomic(path, data)
    assert path.exists()

    with path.open() as f:
        loaded = json.load(f)
    assert loaded == data


def test_write_json_atomic_with_sort_keys(temp_dir):
    """Test atomic JSON write with sorted keys."""
    path = temp_dir / "test.json"
    data = {"z": 1, "a": 2, "m": 3}

    write_json_atomic(path, data, sort_keys=True)

    with path.open() as f:
        content = f.read()
        # Check keys are sorted
        assert content.index('"a"') < content.index('"m"') < content.index('"z"')


def test_write_json(temp_dir):
    """Test simple JSON write."""
    path = temp_dir / "test.json"
    data = {"key": "value"}

    write_json(path, data)
    assert path.exists()

    with path.open() as f:
        loaded = json.load(f)
    assert loaded == data


def test_write_ndjson(temp_dir):
    """Test NDJSON write."""
    path = temp_dir / "test.ndjson"
    records = [{"a": 1}, {"b": 2}, {"c": 3}]

    write_ndjson(path, records)
    assert path.exists()

    with path.open() as f:
        lines = f.readlines()
    assert len(lines) == 3
    assert json.loads(lines[0]) == {"a": 1}


def test_read_parquet_or_ndjson_parquet(temp_dir, sample_dataframe):
    """Test reading from Parquet file."""
    parquet_path = temp_dir / "test.parquet"
    sample_dataframe.to_parquet(parquet_path, index=False)

    df = read_parquet_or_ndjson(parquet_path)
    assert len(df) == 3
    assert list(df.columns) == ["a", "b"]


def test_read_parquet_or_ndjson_ndjson_fallback(temp_dir):
    """Test reading from NDJSON fallback."""
    parquet_path = temp_dir / "test.parquet"
    ndjson_path = temp_dir / "test.ndjson"

    # Create NDJSON file
    records = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    write_ndjson(ndjson_path, records)

    # Should read from NDJSON since Parquet doesn't exist
    df = read_parquet_or_ndjson(parquet_path, ndjson_path)
    assert len(df) == 2
    assert list(df.columns) == ["a", "b"]


def test_read_parquet_or_ndjson_not_found(temp_dir):
    """Test error when neither file exists."""
    parquet_path = temp_dir / "nonexistent.parquet"

    with pytest.raises(FileNotFoundError):
        read_parquet_or_ndjson(parquet_path)


class TestSha256Digests:
    """SHA-256 helpers shared by extractors, releases and study manifests."""

    def test_file_digest_matches_hashlib(self, tmp_path: Path) -> None:
        payload = b"provenance"
        target = tmp_path / "source.csv"
        target.write_bytes(payload)

        assert file_sha256(target) == hashlib.sha256(payload).hexdigest()

    def test_file_digest_is_chunk_size_independent(self, tmp_path: Path) -> None:
        # The digest of a file larger than one read chunk must equal the digest
        # of the whole payload, otherwise recorded provenance would change.
        payload = bytes(range(256)) * 12_000  # ~3 MB, several 1 MiB chunks
        target = tmp_path / "large.bin"
        target.write_bytes(payload)

        assert file_sha256(target) == hashlib.sha256(payload).hexdigest()

    def test_file_digest_accepts_a_string_path(self, tmp_path: Path) -> None:
        target = tmp_path / "source.csv"
        target.write_bytes(b"abc")

        assert file_sha256(str(target)) == file_sha256(target)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            file_sha256(tmp_path / "absent.csv")

    def test_optional_digest_returns_none_for_absent_source(self, tmp_path: Path) -> None:
        assert file_sha256_or_none(None) is None
        assert file_sha256_or_none(tmp_path / "absent.csv") is None
        assert file_sha256_or_none(tmp_path) is None  # a directory is not a source file

    def test_optional_digest_matches_file_digest_when_present(self, tmp_path: Path) -> None:
        target = tmp_path / "source.csv"
        target.write_bytes(b"abc")

        assert file_sha256_or_none(target) == file_sha256(target)

    def test_bytes_digest_matches_hashlib(self) -> None:
        assert sha256_bytes(b"abc") == hashlib.sha256(b"abc").hexdigest()

    def test_bytes_and_file_digests_agree_on_the_same_payload(self, tmp_path: Path) -> None:
        payload = b"the same bytes"
        target = tmp_path / "source.bin"
        target.write_bytes(payload)

        assert sha256_bytes(payload) == file_sha256(target)
