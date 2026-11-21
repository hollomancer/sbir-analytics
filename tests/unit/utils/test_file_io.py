"""Unit tests for file I/O utilities."""

import hashlib
import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest


pytestmark = pytest.mark.fast

from sbir_etl.utils.data.file_io import (
    atomic_write_path,
    file_sha256,
    file_sha256_or_none,
    read_parquet_or_ndjson,
    save_dataframe_parquet,
    sha256_bytes,
    write_json,
    write_json_atomic,
    write_text_atomic,
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


class TestAtomicWrites:
    """A failed write must leave the old file intact and no temp file behind."""

    @staticmethod
    def _seed(tmp_path: Path) -> Path:
        target = tmp_path / "out.dat"
        target.write_bytes(b"previous-complete-artifact")
        return target

    @staticmethod
    def _assert_untouched(target: Path) -> None:
        assert target.read_bytes() == b"previous-complete-artifact"
        assert sorted(p.name for p in target.parent.iterdir()) == [target.name]

    def test_path_replaces_target_on_success(self, tmp_path: Path) -> None:
        target = self._seed(tmp_path)
        with atomic_write_path(target) as temporary:
            assert temporary.parent == target.parent
            assert temporary != target
            temporary.write_bytes(b"new")
        assert target.read_bytes() == b"new"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["out.dat"]

    def test_path_failure_keeps_old_file_and_removes_temp(self, tmp_path: Path) -> None:
        target = self._seed(tmp_path)
        with pytest.raises(RuntimeError, match="simulated"):
            with atomic_write_path(target) as temporary:
                temporary.write_bytes(b"partial")
                raise RuntimeError("simulated")
        self._assert_untouched(target)

    def test_path_failure_after_fsync_keeps_old_file(self, tmp_path: Path, monkeypatch) -> None:
        target = self._seed(tmp_path)

        def fail_fsync(_fd: int) -> None:
            raise OSError("simulated fsync failure")

        monkeypatch.setattr("sbir_etl.utils.data.file_io.os.fsync", fail_fsync)
        with pytest.raises(OSError, match="simulated fsync"):
            with atomic_write_path(target, fsync=True) as temporary:
                temporary.write_bytes(b"new")
        self._assert_untouched(target)

    def test_path_fsync_runs_only_when_requested(self, tmp_path: Path, monkeypatch) -> None:
        calls: list[int] = []
        monkeypatch.setattr("sbir_etl.utils.data.file_io.os.fsync", calls.append)
        with atomic_write_path(tmp_path / "a.dat") as temporary:
            temporary.write_bytes(b"a")
        assert calls == []
        with atomic_write_path(tmp_path / "b.dat", fsync=True) as temporary:
            temporary.write_bytes(b"b")
        assert len(calls) == 1

    def test_path_creates_parent_and_gives_each_writer_its_own_temp(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "out.dat"
        with atomic_write_path(target) as first, atomic_write_path(target) as second:
            assert first != second
            first.write_bytes(b"first")
            second.write_bytes(b"second")
        assert target.read_bytes() == b"first"
        assert sorted(p.name for p in target.parent.iterdir()) == ["out.dat"]

    def test_path_supports_parquet_writers(self, tmp_path: Path, sample_dataframe) -> None:
        target = tmp_path / "out.parquet"
        with atomic_write_path(target) as temporary:
            sample_dataframe.to_parquet(temporary, index=False)
        pd.testing.assert_frame_equal(pd.read_parquet(target), sample_dataframe)

    def test_text_writes_exact_bytes(self, tmp_path: Path) -> None:
        target = tmp_path / "out.txt"
        write_text_atomic(target, "caf\u00e9\r\nline\n")
        assert target.read_bytes() == "caf\u00e9\r\nline\n".encode()

    def test_text_failure_keeps_old_file_and_removes_temp(self, tmp_path: Path) -> None:
        target = self._seed(tmp_path)
        with pytest.raises(UnicodeEncodeError):
            write_text_atomic(target, "caf\u00e9", encoding="ascii")
        self._assert_untouched(target)

    def test_json_failure_keeps_old_file_and_removes_temp(self, tmp_path: Path) -> None:
        target = self._seed(tmp_path)
        circular: dict[str, object] = {}
        circular["self"] = circular
        with pytest.raises(ValueError, match="Circular reference"):
            write_json_atomic(target, circular)
        self._assert_untouched(target)

    def test_json_still_fsyncs(self, tmp_path: Path, monkeypatch) -> None:
        calls: list[int] = []
        monkeypatch.setattr("sbir_etl.utils.data.file_io.os.fsync", calls.append)
        write_json_atomic(tmp_path / "out.json", {"a": 1})
        assert len(calls) == 1


def test_write_json(temp_dir):
    """Test simple JSON write."""
    path = temp_dir / "test.json"
    data = {"key": "value"}

    write_json(path, data)
    assert path.exists()

    with path.open() as f:
        loaded = json.load(f)
    assert loaded == data


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
    ndjson_path.write_text("".join(json.dumps(r) + "\n" for r in records))

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


def test_atomic_write_new_file_is_world_readable(tmp_path):
    # mkstemp makes 0600 files; outputs on shared mounts must stay readable.
    target = tmp_path / "new.json"
    write_text_atomic(target, "{}\n")
    assert target.stat().st_mode & 0o777 == 0o644


def test_atomic_write_keeps_existing_mode(tmp_path):
    target = tmp_path / "existing.json"
    target.write_text("old")
    target.chmod(0o640)
    write_text_atomic(target, "new")
    assert target.read_text() == "new"
    assert target.stat().st_mode & 0o777 == 0o640
