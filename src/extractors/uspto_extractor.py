# sbir-etl/src/extractors/uspto_extractor.py
"""
USPTOExtractor - chunked and streaming extractor for USPTO datasets.

Goals implemented:
- Task 3.1: Create USPTOExtractor class in `src/extractors/uspto_extractor.py`.
- Task 3.2: Implement Stata (.dta) file reading with chunked iteration.
- Task 3.3: Add memory-efficient streaming for large files with fallbacks.

Behavior summary:
- The extractor locates supported files under a given path (by extension).
- For each supported file it provides:
    * `stream_rows(file_path, chunk_size)` generator yielding dictionaries (row-wise),
      reading in chunks appropriate for file type.
    * `stream_assignments(file_path, chunk_size)` generator yielding
      `PatentAssignment` instances (when model available), or raw dicts on error.
- Robust against Stata format variations by attempting a sequence:
    1) pandas iterator (`read_stata(..., iterator=True)` and `.get_chunk()`),
    2) pyreadstat row_limit (if available),
    3) full pandas read with a warning (last resort).
- CSVs are read via pandas `read_csv` with `chunksize`.
- Parquet is handled using pyarrow if available (stream by row-groups) otherwise pandas read with chunking fallback.
- Includes graceful error handling: logs errors, yields error records as metadata, and continues where possible.

Notes:
- This file assumes the project has `pandas` installed. If pyreadstat or pyarrow
  are available those are preferred for certain formats.
- The mapping from raw row -> PatentAssignment is heuristic: it looks for
  common field names and attempts to populate the Pydantic model. Missing fields
  are left None; converters are applied via the model validators.

Example:
    ex = USPTOExtractor(Path("data/raw/uspto"))
    for row in ex.stream_rows(ex.input_dir / "assignment.dta", chunk_size=10000):
        process(row)
    # Or get model instances:
    for assignment in ex.stream_assignments(ex.input_dir/"assignment.dta", chunk_size=10000):
        # assignment is PatentAssignment or dict on error
        handle(assignment)
"""

from __future__ import annotations

import time
from collections.abc import Generator, Iterable
from pathlib import Path

from loguru import logger

# Optional imports - fallbacks are handled at runtime
try:
    import pandas as pd
except Exception:  # pragma: no cover - environment may not have pandas
    pd = None  # type: ignore

try:
    import pyreadstat
except Exception:
    pyreadstat = None

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except Exception:
    pa = None
    pq = None

# Import the PatentAssignment model if available; otherwise use a type alias to dict
try:
    from src.models.uspto_models import PatentAssignment
except Exception:  # pragma: no cover - allow this module to exist even if models missing
    PatentAssignment = None  # type: ignore


SUPPORTED_EXTENSIONS = [".dta", ".csv", ".parquet"]


class USPTOExtractor:
    """
    Extractor for USPTO dataset files with chunked iteration and streaming.

    Parameters
    ----------
    input_dir:
        Directory where USPTO files are stored. Can contain multiple .dta/.csv/.parquet.
    file_globs:
        Optional list of filename patterns to include (defaults to all supported extensions).
    """

    def __init__(
        self,
        input_dir: str | Path,
        file_globs: Iterable[str] | None = None,
        *,
        continue_on_error: bool = True,
        log_every: int = 50000,
    ):
        self.input_dir = Path(input_dir)
        if not self.input_dir.exists():
            raise FileNotFoundError(f"Input directory does not exist: {self.input_dir}")
        self.file_globs = list(file_globs) if file_globs else []
        self.continue_on_error = continue_on_error
        self.log_every = max(0, int(log_every))
        logger.debug("Initialized USPTOExtractor on {}", self.input_dir)

    def discover_files(self) -> list[Path]:
        """
        Discover files under the input directory matching supported extensions
        and optional globs.
        """
        files: list[Path] = []
        if self.file_globs:
            for pattern in self.file_globs:
                files.extend(sorted(self.input_dir.glob(pattern)))
        else:
            for ext in SUPPORTED_EXTENSIONS:
                files.extend(sorted(self.input_dir.rglob(f"*{ext}")))
        logger.info("Discovered %d USPTO files under %s", len(files), self.input_dir)
        return files

    # ----------------------------
    # High-level streaming methods
    # ----------------------------
    def stream_rows(
        self, file_path: str | Path, chunk_size: int = 10000
    ) -> Generator[dict, None, None]:
        """
        Stream raw rows from the file as dictionaries in chunks.

        Yields
        ------
        dict
            A mapping of column -> value for each row in the dataset.
        """
        path = Path(file_path)
        start = time.perf_counter()
        yielded = 0
        try:
            for rec in self._stream_rows_for_extension(path, chunk_size):
                yielded += 1
                if self.log_every and yielded % self.log_every == 0:
                    elapsed = max(time.perf_counter() - start, 1e-6)
                    logger.info(
                        "Streaming %s (%s rows processed, %.1f rows/sec)",
                        path.name,
                        yielded,
                        yielded / elapsed,
                    )
                yield rec
        except Exception as exc:
            logger.exception("Failed streaming %s: %s", path, exc)
            if self.continue_on_error:
                yield {"_error": str(exc), "_file": str(path)}
            else:
                raise
        finally:
            elapsed = max(time.perf_counter() - start, 1e-6)
            logger.info(
                "Completed streaming %s: %s rows in %.2fs (%.1f rows/sec)",
                path.name,
                yielded,
                elapsed,
                yielded / elapsed,
            )

    def _stream_rows_for_extension(
        self, path: Path, chunk_size: int
    ) -> Generator[dict, None, None]:
        ext = path.suffix.lower()
        if ext == ".csv":
            yield from self._stream_csv(path, chunk_size)
        elif ext == ".dta":
            yield from self._stream_dta(path, chunk_size)
        elif ext == ".parquet":
            yield from self._stream_parquet(path, chunk_size)
        else:
            raise ValueError(f"Unsupported file extension for USPTO extractor: {ext}")

    def stream_assignments(
        self, file_path: str | Path, chunk_size: int = 10000
    ) -> Generator[PatentAssignment | dict, None, None]:
        """
        Stream assignments as PatentAssignment model instances when possible.
        If the model import is unavailable or construction fails for a row,
        yields the raw dict (with an '_error' key describing the issue).
        """

        def _filter_none(d: dict) -> dict:
            """Remove keys with None values to allow Pydantic defaults to be used."""
            return {k: v for k, v in d.items() if v is not None}

        for row in self.stream_rows(file_path, chunk_size=chunk_size):
            if PatentAssignment is not None:
                try:
                    # Map relevant fields heuristically: allow model to validate/coerce
                    # Attempt to construct PatentAssignment from the raw row dict
                    # Filter None values so Pydantic defaults are applied
                    pa = PatentAssignment(
                        rf_id=row.get("rf_id") or row.get("record_id") or row.get("id"),
                        file_id=row.get("file_id"),
                        document=_filter_none(
                            {
                                "grant_number": row.get("grant_doc_num") or row.get("grant_number"),
                                "application_number": row.get("application_number"),
                                "publication_number": row.get("publication_number"),
                                "filing_date": row.get("filing_date"),
                                "publication_date": row.get("publication_date"),
                                "grant_date": row.get("grant_date"),
                                "title": row.get("title"),
                                "abstract": row.get("abstract"),
                            }
                        ),
                        conveyance=_filter_none(
                            {
                                "rf_id": row.get("conveyance_rf_id"),
                                "conveyance_type": row.get("conveyance_type"),
                                "description": row.get("conveyance_text"),
                                "recorded_date": row.get("recorded_date"),
                            }
                        ),
                        assignee=_filter_none(
                            {
                                "rf_id": row.get("assignee_rf_id"),
                                "name": row.get("assignee_name"),
                                "street": row.get("assignee_street"),
                                "city": row.get("assignee_city"),
                                "state": row.get("assignee_state"),
                                "postal_code": row.get("assignee_postal"),
                                "country": row.get("assignee_country"),
                                "uei": row.get("assignee_uei"),
                                "cage": row.get("assignee_cage"),
                                "duns": row.get("assignee_duns"),
                            }
                        ),
                        assignor=_filter_none(
                            {
                                "rf_id": row.get("assignor_rf_id"),
                                "name": row.get("assignor_name"),
                                "execution_date": row.get("execution_date"),
                                "acknowledgment_date": row.get("acknowledgment_date"),
                            }
                        ),
                        execution_date=row.get("execution_date"),
                        recorded_date=row.get("recorded_date"),
                        normalized_assignee_name=row.get("assignee_name"),
                        normalized_assignor_name=row.get("assignor_name"),
                        metadata={"_source_row": row},
                    )
                    yield pa
                except Exception as e:
                    logger.debug("Failed to construct PatentAssignment for row: %s", e)
                    # attach error info and yield raw row for later inspection
                    row_with_err = dict(row)
                    row_with_err["_error"] = str(e)
                    yield row_with_err
            else:
                yield row

    # ----------------------------
    # File format-specific readers
    # ----------------------------
    def _stream_csv(self, path: Path, chunk_size: int) -> Generator[dict, None, None]:
        if pd is None:
            raise RuntimeError("pandas is required to read CSV files for USPTO extraction")
        logger.debug("Streaming CSV %s with chunk_size=%d", path, chunk_size)
        try:
            for chunk in pd.read_csv(path, chunksize=chunk_size, low_memory=True):
                yield from chunk.to_dict(orient="records")
        except Exception:
            logger.exception("CSV streaming failed for %s", path)
            raise

    def _stream_dta(self, path: Path, chunk_size: int) -> Generator[dict, None, None]:
        """
        Stream rows from a .dta (Stata) file in chunks.

        Strategy (enhanced):
        - Probe file metadata (when available) to detect Stata release/version differences.
        - Try pandas iterator (read_stata iterator + get_chunk).
        - If iterator fails, try pyreadstat with row_limit, and inspect metadata for format/version.
        - Normalize column names (common variant mapping) to canonical keys to make downstream mapping stable.
        - As a last resort, read full file with pandas (only for smaller files).
        """
        if pd is None:
            raise RuntimeError("pandas is required to read .dta files for USPTO extraction")

        def _normalize_row_keys(row: dict) -> dict:
            """
            Normalize keys from various release variations to canonical keys used by the pipeline.
            This mapping is intentionally conservative and can be extended as we see real variants.
            """
            key_map = {
                # common variations => canonical
                "grant_doc_num": ["grant_doc_num", "grant_docnum", "grant_number", "patent_number"],
                "application_number": ["application_number", "app_num", "applicationno"],
                "publication_number": ["publication_number", "pub_num", "pub_no"],
                "filing_date": ["filing_date", "file_dt", "application_date"],
                "publication_date": ["publication_date", "pub_date"],
                "grant_date": ["grant_date", "issue_date", "grant_dt"],
                "assignee_name": ["assignee_name", "assignee", "assignee_org", "assignee_org_name"],
                "assignor_name": ["assignor_name", "assignor", "grantor_name"],
                "conveyance_text": ["conveyance_text", "conveyance", "text"],
                "recorded_date": ["recorded_date", "record_date", "recorded_dt"],
                "rf_id": ["rf_id", "record_id", "id"],
                "file_id": ["file_id", "fileid"],
            }
            normalized = {}
            # lower-case map of incoming keys for quick lookup
            incoming_map = {k.lower(): k for k in row.keys()}
            # For each canonical key, find the first incoming variant present
            for canon, variants in key_map.items():
                found = None
                for v in variants:
                    k = v.lower()
                    if k in incoming_map:
                        found = incoming_map[k]
                        break
                if found:
                    normalized[canon] = row.get(found)
            # copy over any keys that are already canonical or not remapped, preserving case
            for k, v in row.items():
                if k not in normalized:
                    normalized[k] = v
            return normalized

        def _detect_stata_release_with_pyreadstat(p) -> str | None:
            """Attempt to discover Stata file format/version via pyreadstat metadata, if available."""
            if pyreadstat is None:
                return None
            try:
                meta = pyreadstat.read_dta_metadata(str(p))
                # pyreadstat meta may expose file_format_version or other attributes
                version = getattr(meta, "file_format_version", None) or getattr(
                    meta, "format_version", None
                )
                if version is not None:
                    return str(version)
            except Exception:
                # not critical - just return None
                return None
            return None

        try:
            # Attempt to detect file variant first (best-effort)
            release_hint = None
            try:
                release_hint = _detect_stata_release_with_pyreadstat(path)
                if release_hint:
                    logger.debug("Detected Stata format/version for %s: %s", path, release_hint)
            except Exception:
                release_hint = None

            release_numeric: int | None = None
            if release_hint:
                try:
                    release_numeric = int(release_hint)
                except ValueError:
                    release_numeric = None
            if release_numeric is None:
                release_numeric = self._detect_stata_release(path)
                if release_numeric:
                    logger.debug("Header-based Stata release for %s: %s", path, release_numeric)

            skip_pandas = release_numeric is not None and release_numeric >= 118

            # Try pandas iterator approach first (fast for many .dta files)
            if not skip_pandas:
                logger.debug("Attempting pandas read_stata iterator for %s", path)
                try:
                    reader = pd.read_stata(path, iterator=True, convert_categoricals=False)
                    while True:
                        try:
                            chunk = reader.get_chunk(chunk_size)  # type: ignore
                        except StopIteration:
                            break
                        except Exception as e:
                            # pandas iterator may raise for some .dta versions; fallback to pyreadstat
                            logger.debug("pandas iterator get_chunk error: %s", e)
                            raise
                        for rec in chunk.to_dict(orient="records"):
                            yield _normalize_row_keys(rec)
                    return
                except Exception:
                    logger.debug(
                        "pandas iterator approach failed for %s; trying pyreadstat fallback", path
                    )
            else:
                logger.debug(
                    "Skipping pandas iterator for %s (Stata release=%s not fully supported)",
                    path,
                    release_numeric,
                )

            # Fallback: pyreadstat if available - use row_limit and row_offset for chunked reads
            if pyreadstat is not None:
                logger.debug("Using pyreadstat.read_dta row_limit for %s", path)
                offset = 0
                rows_yielded = 0
                total_rows = None
                # Try to get a row count hint from metadata (best-effort)
                try:
                    meta_hint = pyreadstat.read_dta_metadata(str(path))
                    total_rows = getattr(meta_hint, "number_of_rows", None) or getattr(
                        meta_hint, "rows", None
                    )
                except Exception:
                    total_rows = None
                while True:
                    try:
                        # pyreadstat returns (df, meta)
                        df, meta = pyreadstat.read_dta(
                            str(path), row_limit=chunk_size, row_offset=offset
                        )
                    except Exception as e:
                        logger.debug("pyreadstat read failed at offset %s: %s", offset, e)
                        raise
                    if df is None or df.shape[0] == 0:
                        break
                    for rec in df.to_dict(orient="records"):
                        yield _normalize_row_keys(rec)
                    rows_yielded += df.shape[0]
                    offset += df.shape[0]
                    # Periodic progress logging to help monitor long reads
                    if self.log_every and rows_yielded % self.log_every == 0:
                        if total_rows:
                            try:
                                pct = rows_yielded / int(total_rows) * 100.0
                                logger.info(
                                    "Streaming %s via pyreadstat: %d/%s rows (%.1f%%)",
                                    path.name,
                                    rows_yielded,
                                    total_rows,
                                    pct,
                                )
                            except Exception:
                                logger.info(
                                    "Streaming %s via pyreadstat: %d rows processed (total unknown)",
                                    path.name,
                                    rows_yielded,
                                )
                        else:
                            logger.info(
                                "Streaming %s via pyreadstat: %d rows processed",
                                path.name,
                                rows_yielded,
                            )
                return

            # Last resort: read entire file (may be large) - but attempt to rename columns using heuristics
            logger.warning(
                "Falling back to reading entire .dta file into memory for %s (last resort)", path
            )
            df_full = pd.read_stata(path, convert_categoricals=False)
            # Normalize column names (lowercase, trim) to help mapping downstream
            df_full.columns = [str(c).strip() for c in df_full.columns]
            for i in range(0, len(df_full), chunk_size):
                chunk = df_full.iloc[i : i + chunk_size]
                for rec in chunk.to_dict(orient="records"):
                    yield _normalize_row_keys(rec)
            return

        except Exception as e:
            logger.exception("Failed streaming .dta file %s: %s", path, e)
            raise

    def _stream_parquet(self, path: Path, chunk_size: int) -> Generator[dict, None, None]:
        """
        Stream parquet files preferentially with pyarrow row groups; fallback to pandas.
        """
        if pq is not None and pa is not None:
            try:
                logger.debug("Streaming parquet via pyarrow for %s", path)
                pf = pq.ParquetFile(path)
                # iterate row groups and then batch within row group to chunk_size
                for rg_index in range(pf.num_row_groups):
                    table = pf.read_row_group(rg_index)
                    df = table.to_pandas()
                    for i in range(0, len(df), chunk_size):
                        chunk = df.iloc[i : i + chunk_size]
                        for rec in chunk.to_dict(orient="records"):
                            yield rec
                return
            except Exception:
                logger.debug("pyarrow parquet streaming failed for %s; falling back to pandas", path)
        # pandas fallback
        if pd is None:
            raise RuntimeError("pandas is required to read parquet files (fallback)")
        try:
            df = pd.read_parquet(path)
            for i in range(0, len(df), chunk_size):
                chunk = df.iloc[i : i + chunk_size]
                for rec in chunk.to_dict(orient="records"):
                    yield rec
        except Exception:
            logger.exception("Failed streaming parquet %s", path)
            raise

    # ----------------------------
    # Helper / utility methods
    # ----------------------------
    def read_first_n(self, file_path: str | Path, n: int = 10) -> list[dict]:
        """Read and return the first n rows (useful for quick inspection)."""
        it = self.stream_rows(file_path, chunk_size=n)
        out = []
        for _ in range(n):
            try:
                out.append(next(it))
            except StopIteration:
                break
        return out

    def count_rows_estimate(self, file_path: str | Path) -> int | None:
        """
        Return an approximate total row count for a file, if available cheaply.
        - CSV: None (would require scanning file)
        - parquet: use pyarrow metadata if available
        - dta: pyreadstat meta may provide row count; otherwise None
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        try:
            if ext == ".parquet" and pq is not None:
                pf = pq.ParquetFile(path)
                return sum(pf.metadata.row_group(i).num_rows for i in range(pf.num_row_groups))
            if ext == ".dta" and pyreadstat is not None:
                try:
                    meta = pyreadstat.read_dta_metadata(str(path))
                    # attempt to extract row count from meta if available
                    row_count = getattr(meta, "number_of_rows", None) or getattr(meta, "rows", None)
                    return int(row_count) if row_count is not None else None
                except Exception:
                    return None
        except Exception:
            return None
        return None

    def _detect_stata_release(self, file_path: str | Path) -> int | None:
        """
        Best-effort detection of Stata release version for .dta files.

        Strategy:
         - Prefer pyreadstat metadata when available (reads file metadata).
         - Fall back to a lightweight header sniff (non-exhaustive) if pyreadstat unavailable.
        Returns:
         - Integer Stata release (e.g., 117, 118) when detectable, otherwise None.
        """
        p = Path(file_path)
        if pyreadstat is not None:
            try:
                meta = pyreadstat.read_dta_metadata(str(p))
                version = getattr(meta, "file_format_version", None) or getattr(
                    meta, "format_version", None
                )
                if version is not None:
                    try:
                        return int(version)
                    except Exception:
                        # Coerce "118.0" -> 118, or take integer prefix where possible
                        try:
                            return int(str(version).split(".")[0])
                        except Exception:
                            return None
            except Exception:
                # non-fatal; return None to indicate unknown
                return None
        # Lightweight header inspection fallback (may not be reliable for all files)
        try:
            with open(p, "rb") as fh:
                header = fh.read(256)
                import re

                m = re.search(rb"release[\s=]*([0-9]{3})", header, re.IGNORECASE)
                if m:
                    try:
                        return int(m.group(1))
                    except Exception:
                        return None
        except Exception:
            return None
        return None

    def supported_files_summary(self) -> dict[str, int]:
        """Return a summary count of supported files found in the input directory (with logging)."""
        files = self.discover_files()
        by_ext: dict[str, int] = {}
        for f in files:
            by_ext.setdefault(f.suffix.lower(), 0)
            by_ext[f.suffix.lower()] += 1
        logger.info("USPTO files discovered: %s", by_ext)
        return by_ext
