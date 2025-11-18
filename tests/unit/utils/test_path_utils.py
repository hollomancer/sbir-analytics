"""Unit tests for path utilities."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

# Import directly using importlib to avoid pulling in duckdb dependency via __init__.py
_spec = importlib.util.spec_from_file_location(
    "path_utils", Path(__file__).parent.parent.parent / "src" / "utils" / "path_utils.py"
)
_path_utils = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_path_utils)  # type: ignore[union-attr]

ensure_dir = _path_utils.ensure_dir
ensure_parent_dir = _path_utils.ensure_parent_dir
ensure_path_exists = _path_utils.ensure_path_exists
normalize_path_list = _path_utils.normalize_path_list
resolve_path = _path_utils.resolve_path
safe_path_join = _path_utils.safe_path_join


class TestEnsureParentDir:
    """Tests for ensure_parent_dir function."""

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        """Test that parent directory is created."""
        file_path = tmp_path / "subdir" / "file.txt"
        ensure_parent_dir(file_path)
        assert file_path.parent.exists()
        assert file_path.parent.is_dir()

    def test_handles_nested_directories(self, tmp_path: Path) -> None:
        """Test that nested parent directories are created."""
        file_path = tmp_path / "level1" / "level2" / "level3" / "file.txt"
        ensure_parent_dir(file_path)
        assert file_path.parent.exists()
        assert (tmp_path / "level1" / "level2" / "level3").exists()

    def test_idempotent(self, tmp_path: Path) -> None:
        """Test that calling multiple times doesn't error."""
        file_path = tmp_path / "subdir" / "file.txt"
        ensure_parent_dir(file_path)
        ensure_parent_dir(file_path)  # Should not raise
        assert file_path.parent.exists()

    def test_handles_string_path(self, tmp_path: Path) -> None:
        """Test that string paths are accepted."""
        file_path = tmp_path / "subdir" / "file.txt"
        ensure_parent_dir(str(file_path))
        assert file_path.parent.exists()


class TestEnsureDir:
    """Tests for ensure_dir function."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        """Test that directory is created."""
        dir_path = tmp_path / "newdir"
        ensure_dir(dir_path)
        assert dir_path.exists()
        assert dir_path.is_dir()

    def test_creates_nested_directories(self, tmp_path: Path) -> None:
        """Test that nested directories are created."""
        dir_path = tmp_path / "level1" / "level2" / "level3"
        ensure_dir(dir_path)
        assert dir_path.exists()
        assert (tmp_path / "level1" / "level2").exists()

    def test_idempotent(self, tmp_path: Path) -> None:
        """Test that calling multiple times doesn't error."""
        dir_path = tmp_path / "newdir"
        ensure_dir(dir_path)
        ensure_dir(dir_path)  # Should not raise
        assert dir_path.exists()

    def test_handles_string_path(self, tmp_path: Path) -> None:
        """Test that string paths are accepted."""
        dir_path = tmp_path / "newdir"
        ensure_dir(str(dir_path))
        assert dir_path.exists()


class TestResolvePath:
    """Tests for resolve_path function."""

    def test_resolves_absolute_path(self, tmp_path: Path) -> None:
        """Test that absolute paths are resolved."""
        abs_path = tmp_path / "file.txt"
        resolved = resolve_path(abs_path)
        assert resolved.is_absolute()
        assert resolved == abs_path.resolve()

    def test_resolves_relative_path(self) -> None:
        """Test that relative paths are resolved."""
        rel_path = Path("some_file.txt")
        resolved = resolve_path(rel_path)
        assert resolved.is_absolute()

    def test_resolves_relative_path_with_base(self, tmp_path: Path) -> None:
        """Test that relative paths are resolved with base."""
        rel_path = Path("subdir") / "file.txt"
        resolved = resolve_path(rel_path, base=tmp_path)
        assert resolved.is_absolute()
        assert resolved == (tmp_path / "subdir" / "file.txt").resolve()

    def test_handles_string_path(self, tmp_path: Path) -> None:
        """Test that string paths are accepted."""
        resolved = resolve_path("file.txt", base=str(tmp_path))
        assert resolved.is_absolute()
        assert tmp_path in resolved.parents


class TestNormalizePathList:
    """Tests for normalize_path_list function."""

    def test_single_string_path(self) -> None:
        """Test normalizing a single string path."""
        result = normalize_path_list("data/file.csv")
        assert len(result) == 1
        assert result[0] == Path("data/file.csv")

    def test_single_path_object(self) -> None:
        """Test normalizing a single Path object."""
        path = Path("data/file.csv")
        result = normalize_path_list(path)
        assert len(result) == 1
        assert result[0] == path

    def test_list_of_strings(self) -> None:
        """Test normalizing a list of string paths."""
        result = normalize_path_list(["file1.csv", "file2.csv"])
        assert len(result) == 2
        assert result[0] == Path("file1.csv")
        assert result[1] == Path("file2.csv")

    def test_list_of_paths(self) -> None:
        """Test normalizing a list of Path objects."""
        paths = [Path("file1.csv"), Path("file2.csv")]
        result = normalize_path_list(paths)
        assert len(result) == 2
        assert result == paths

    def test_mixed_list(self) -> None:
        """Test normalizing a mixed list of strings and Paths."""
        result = normalize_path_list(["file1.csv", Path("file2.csv")])
        assert len(result) == 2
        assert result[0] == Path("file1.csv")
        assert result[1] == Path("file2.csv")

    def test_empty_list_without_requirement(self) -> None:
        """Test that empty list is allowed when require_at_least_one=False."""
        result = normalize_path_list([])
        assert result == []

    def test_empty_list_with_requirement(self) -> None:
        """Test that empty list raises ValueError when require_at_least_one=True."""
        with pytest.raises(ValueError, match="At least one path"):
            normalize_path_list([], require_at_least_one=True)

    def test_invalid_type_raises(self) -> None:
        """Test that invalid types raise TypeError."""
        with pytest.raises(TypeError, match="Unsupported path type"):
            normalize_path_list(123)  # type: ignore[arg-type]

    def test_invalid_list_item_raises(self) -> None:
        """Test that invalid list items raise TypeError."""
        with pytest.raises(TypeError, match="Unsupported path entry type"):
            normalize_path_list(["valid.csv", 123])  # type: ignore[list-item]


class TestEnsurePathExists:
    """Tests for ensure_path_exists function."""

    def test_creates_parent_only(self, tmp_path: Path) -> None:
        """Test that parent is created but file is not."""
        file_path = tmp_path / "subdir" / "file.txt"
        result = ensure_path_exists(file_path, create_parent=True, create_file=False)
        assert file_path.parent.exists()
        assert not file_path.exists()
        assert result == file_path

    def test_creates_parent_and_file(self, tmp_path: Path) -> None:
        """Test that both parent and file are created."""
        file_path = tmp_path / "subdir" / "file.txt"
        result = ensure_path_exists(file_path, create_parent=True, create_file=True)
        assert file_path.parent.exists()
        assert file_path.exists()
        assert result == file_path

    def test_does_not_create_without_flags(self, tmp_path: Path) -> None:
        """Test that nothing is created without flags."""
        file_path = tmp_path / "subdir" / "file.txt"
        result = ensure_path_exists(file_path, create_parent=False, create_file=False)
        assert not file_path.parent.exists()
        assert not file_path.exists()
        assert result == file_path

    def test_handles_string_path(self, tmp_path: Path) -> None:
        """Test that string paths are accepted."""
        file_path = tmp_path / "subdir" / "file.txt"
        result = ensure_path_exists(str(file_path), create_parent=True, create_file=True)
        assert file_path.exists()


class TestSafePathJoin:
    """Tests for safe_path_join function."""

    def test_joins_strings(self) -> None:
        """Test joining string path components."""
        result = safe_path_join("data", "raw", "file.csv")
        assert result == Path("data/raw/file.csv")

    def test_joins_path_objects(self) -> None:
        """Test joining Path object components."""
        result = safe_path_join(Path("data"), Path("raw"), Path("file.csv"))
        assert result == Path("data/raw/file.csv")

    def test_joins_mixed_types(self) -> None:
        """Test joining mixed string and Path components."""
        result = safe_path_join("data", Path("raw"), "file.csv")
        assert result == Path("data/raw/file.csv")

    def test_single_component(self) -> None:
        """Test joining a single component."""
        result = safe_path_join("file.csv")
        assert result == Path("file.csv")

    def test_empty_components(self) -> None:
        """Test joining with empty components."""
        result = safe_path_join("data", "", "file.csv")
        assert result == Path("data") / "" / "file.csv"

