"""Path manipulation utilities for consistent file system operations.

This module provides centralized utilities for common path operations,
reducing duplication and standardizing path handling across the codebase.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def ensure_parent_dir(path: Path | str) -> None:
    """Ensure parent directory exists for a given path.

    Creates parent directories if they don't exist. Safe to call multiple times.

    Args:
        path: Path to file or directory (parent will be created)

    Examples:
        >>> ensure_parent_dir(Path("data/processed/output.csv"))
        # Creates data/processed/ if it doesn't exist
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)


def ensure_dir(path: Path | str) -> None:
    """Ensure directory exists, creating it if necessary.

    Args:
        path: Path to directory

    Examples:
        >>> ensure_dir(Path("data/cache"))
        # Creates data/cache/ if it doesn't exist
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)


def resolve_path(path: Path | str, base: Path | str | None = None) -> Path:
    """Resolve and normalize a path to an absolute Path object.

    Args:
        path: Path to resolve (can be relative or absolute)
        base: Base path for resolving relative paths (defaults to current working directory)

    Returns:
        Resolved absolute Path object

    Examples:
        >>> resolve_path("data/raw/file.csv")
        Path('/absolute/path/to/data/raw/file.csv')
        >>> resolve_path("../file.csv", base=Path("/base/path"))
        Path('/base/file.csv')
    """
    path = Path(path)

    if path.is_absolute():
        return path.resolve()

    if base is not None:
        base = Path(base)
        return (base / path).resolve()

    return path.resolve()


def normalize_path_list(
    path_or_paths: str | Path | Iterable[str | Path],
    require_at_least_one: bool = False,
) -> list[Path]:
    """Normalize a single path or iterable of paths into a list of Path objects.

    Args:
        path_or_paths: Single path (str or Path) or iterable of paths
        require_at_least_one: If True, raise ValueError if result is empty

    Returns:
        List of Path objects

    Raises:
        TypeError: If input type is not supported
        ValueError: If require_at_least_one=True and result is empty

    Examples:
        >>> normalize_path_list("data/file.csv")
        [Path('data/file.csv')]
        >>> normalize_path_list(["file1.csv", "file2.csv"])
        [Path('file1.csv'), Path('file2.csv')]
    """
    if isinstance(path_or_paths, str | Path):
        return [Path(path_or_paths)]

    if isinstance(path_or_paths, Iterable):
        paths: list[Path] = []
        for item in path_or_paths:
            if isinstance(item, str | Path):
                paths.append(Path(item))
            else:
                raise TypeError(f"Unsupported path entry type: {type(item)!r}")

        if require_at_least_one and not paths:
            raise ValueError("At least one path must be provided")

        return paths

    raise TypeError(f"Unsupported path type: {type(path_or_paths)!r}")
