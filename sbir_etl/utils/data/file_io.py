"""Centralized file I/O utilities for consistent data persistence.

This module provides:
- Unified parquet saving with NDJSON fallback
- Atomic file writes (temp file in the target directory, then os.replace)
- Unified parquet/NDJSON reading
- SHA-256 digests for source-provenance records
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

# Import centralized path utilities
from sbir_etl.utils.path_utils import ensure_parent_dir as _ensure_parent_dir


def _to_jsonable(x: Any) -> Any:
    """Convert a value to JSON-serializable format.

    Handles pandas Timestamps, NumPy scalars, NaN/NaT values, and nested containers.

    Args:
        x: Value to convert

    Returns:
        JSON-serializable value
    """
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass

    if isinstance(x, Decimal):
        # Preserve precision for basic numeric types; convert to float for JSON
        try:
            return float(x)
        except Exception:
            return str(x)

    # pandas Timestamps
    if hasattr(x, "isoformat"):
        try:
            return x.isoformat()
        except Exception:
            pass

    # NumPy scalars
    try:
        import numpy as _np

        if isinstance(x, _np.generic):
            try:
                return x.item()
            except Exception:
                pass
    except Exception:
        pass

    # Containers
    if isinstance(x, dict):
        return {str(k): _to_jsonable(v) for k, v in x.items()}
    if isinstance(x, list | tuple | set):
        return [_to_jsonable(v) for v in list(x)]

    return x


def save_dataframe_parquet(
    df: pd.DataFrame,
    path: Path,
    index: bool = False,
    fallback_to_ndjson: bool = True,
    **kwargs: Any,
) -> Path:
    """Save DataFrame to Parquet format with NDJSON fallback.

    Attempts to save as Parquet first. If that fails and fallback_to_ndjson is True,
    falls back to NDJSON format in the same directory with .ndjson suffix.

    The fallback is handled here rather than raised, so a caller that assumes the
    data landed at ``path`` is wrong whenever it fires — the Parquet file is
    deleted and the rows are at the ``.ndjson`` sibling. Use the returned path
    rather than the one passed in.

    Args:
        df: DataFrame to save
        path: Destination path for Parquet file
        index: Whether to include DataFrame index in output
        fallback_to_ndjson: If True, fall back to NDJSON if Parquet save fails
        **kwargs: Additional arguments passed to pandas.DataFrame.to_parquet()

    Returns:
        The path actually written: ``path`` on success, or the ``.ndjson``
        sibling when the Parquet write failed and the fallback was taken.
    """
    _ensure_parent_dir(path)

    try:
        df.to_parquet(path, index=index, **kwargs)
        logger.debug(f"Saved DataFrame to Parquet: {path}")
        return path
    except Exception as e:
        if not fallback_to_ndjson:
            logger.error(f"Failed to save Parquet and fallback disabled: {e}")
            raise

        # Fallback to NDJSON in the same directory with .ndjson suffix
        ndjson_path = path.with_suffix(".ndjson")
        logger.warning(
            f"Parquet save failed, falling back to NDJSON: {e}",
            path=str(ndjson_path),
        )

        with ndjson_path.open("w", encoding="utf-8") as fh:
            for _, row in df.iterrows():
                record = {k: _to_jsonable(v) for k, v in row.items()}
                fh.write(json.dumps(record) + "\n")

        # Remove stale parquet file so read_parquet_or_ndjson finds the NDJSON
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

        logger.info(f"Saved DataFrame to NDJSON fallback: {ndjson_path}")
        return ndjson_path


@contextmanager
def atomic_write_path(target: Path | str, *, fsync: bool = False) -> Iterator[Path]:
    """Yield a temporary path that replaces ``target`` when the block succeeds.

    The temporary file is created in the target's directory, so ``os.replace``
    is atomic: readers see the old file or the complete new file, never a
    partial one. The new file keeps the target's permission bits, or gets 0644
    when the target does not exist yet. If the block raises, ``target`` is left unchanged and the
    temporary file is removed. Each call gets a unique temporary name, so two
    writers to the same target do not share a temporary file.

    Args:
        target: Final path to write.
        fsync: If True, flush the temporary file to disk before the replace.

    Example:
        >>> with atomic_write_path(Path("out.parquet")) as tmp:  # doctest: +SKIP
        ...     frame.to_parquet(tmp, index=False)
    """
    target = Path(target)
    _ensure_parent_dir(target)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        yield temporary
        if fsync:
            sync_descriptor = os.open(temporary, os.O_RDWR)
            try:
                os.fsync(sync_descriptor)
            finally:
                os.close(sync_descriptor)
        # mkstemp creates the file as 0600. Keep the target's mode, or use 0644
        # for a new file, so that other users and containers can still read it.
        mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644
        temporary.chmod(mode)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def write_text_atomic(
    target: Path | str,
    text: str,
    *,
    encoding: str = "utf-8",
    fsync: bool = False,
) -> None:
    """Write ``text`` to ``target`` atomically. See :func:`atomic_write_path`.

    No newline translation is applied, so the bytes on disk are exactly
    ``text.encode(encoding)``.
    """
    with atomic_write_path(target, fsync=fsync) as temporary:
        temporary.write_bytes(text.encode(encoding))


def write_json_atomic(
    target: Path,
    data: dict[str, Any] | list[Any],
    indent: int = 2,
    sort_keys: bool = False,
    ensure_ascii: bool = False,
    default: Any = str,
) -> None:
    """Write JSON atomically to target path, with fsync before the replace.

    This ensures that the target file is either completely written or not modified,
    preventing partial writes in case of interruption.

    Args:
        target: Target path for JSON file
        data: Data to write (dict or list)
        indent: JSON indentation level
        sort_keys: Whether to sort dictionary keys
        ensure_ascii: Whether to escape non-ASCII characters
        default: Function to handle non-serializable objects
    """
    try:
        with atomic_write_path(target, fsync=True) as temporary:
            with temporary.open("w", encoding="utf-8") as fh:
                json.dump(
                    data,
                    fh,
                    indent=indent,
                    sort_keys=sort_keys,
                    ensure_ascii=ensure_ascii,
                    default=default,
                )
        logger.debug(f"Atomically wrote JSON: {target}")
    except Exception as e:
        logger.error(f"Failed to write JSON atomically: {e}")
        raise


def write_json(
    path: Path,
    payload: dict[str, Any] | list[Any],
    indent: int = 2,
    ensure_ascii: bool = False,
) -> None:
    """Write JSON to file (non-atomic, simple write).

    For atomic writes, use write_json_atomic() instead.

    Args:
        path: Path to write JSON file
        payload: Data to write (dict or list)
        indent: JSON indentation level
        ensure_ascii: Whether to escape non-ASCII characters
    """
    _ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=indent, ensure_ascii=ensure_ascii)


def read_parquet_or_ndjson(parquet_path: Path, json_path: Path | None = None) -> pd.DataFrame:
    """Read data from Parquet file, falling back to NDJSON if Parquet doesn't exist.

    Args:
        parquet_path: Path to Parquet file
        json_path: Optional path to NDJSON fallback file. If None, uses parquet_path with .ndjson suffix.

    Returns:
        DataFrame with loaded data, or empty DataFrame if neither file exists

    Raises:
        FileNotFoundError: If neither Parquet nor NDJSON file exists
    """
    if json_path is None:
        json_path = parquet_path.with_suffix(".ndjson")

    # Try Parquet first
    if parquet_path.exists():
        try:
            df = pd.read_parquet(parquet_path)
            logger.debug(f"Read DataFrame from Parquet: {parquet_path}")
            return df
        except Exception as e:
            logger.warning(f"Failed to read Parquet, trying NDJSON fallback: {e}")

    # Fallback to NDJSON
    if json_path.exists():
        records = []
        with json_path.open("r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping invalid JSON at line {line_num} in {json_path}: {e}")
                    continue

        if records:
            df = pd.DataFrame(records)
            logger.debug(f"Read {len(records)} records from NDJSON: {json_path}")
            return df

    # Neither file exists
    raise FileNotFoundError(
        f"Neither Parquet ({parquet_path}) nor NDJSON ({json_path}) file exists"
    )


# Read size for streamed digests. Fixed at 1 MiB because the value is part of
# no digest: SHA-256 of a file is the same whatever chunk size produced it.
_DIGEST_CHUNK_BYTES = 1024 * 1024


def file_sha256(path: Path | str) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks.

    Use this for the source-provenance digests recorded by extractors,
    releases and study manifests. The file is streamed, so an input larger
    than memory is safe.

    Raises:
        FileNotFoundError: If ``path`` does not exist.

    Example:
        >>> from pathlib import Path
        >>> _ = Path("example.txt").write_text("abc")
        >>> file_sha256("example.txt")[:12]
        'ba7816bf8f01'
        >>> Path("example.txt").unlink()
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_DIGEST_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_sha256_or_none(path: Path | str | None) -> str | None:
    """Return the SHA-256 hex digest of a file, or ``None`` when it is absent.

    Callers that record an optional source use this so a missing input reads
    as "no digest" rather than raising.
    """
    if path is None:
        return None
    resolved = Path(path)
    if not resolved.is_file():
        return None
    return file_sha256(resolved)


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest of an in-memory payload."""
    return hashlib.sha256(data).hexdigest()
