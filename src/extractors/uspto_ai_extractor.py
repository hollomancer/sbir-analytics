# sbir-etl/src/extractors/uspto_ai_extractor.py
"""
USPTOAIExtractor - streaming, chunked extractor for the USPTO AI predictions dataset.

Goals:
- Stream and normalize USPTO AI records from NDJSON / CSV / Stata (.dta) / Parquet.
- Provide chunked iteration for large files with resume/checkpoint support.
- Offer optional in-memory deduplication by `grant_doc_num`.
- Normalize common identifier fields to a canonical `grant_doc_num`.

Notes:
- This module prefers stdlib paths for NDJSON/CSV. DTA/Parquet use optional deps:
    * pandas, pyreadstat, pyarrow
- Checkpointing stores lightweight progress files in a checkpoint directory
  keyed by absolute source file path.

Typical usage:
    ex = USPTOAIExtractor("data/raw/USPTO")
    files = ex.discover_files()  # list of .ndjson/.csv/.dta/.parquet
    for rec in ex.stream_normalized(files[0], chunk_size=10000, resume=True, dedupe=True):
        handle(rec)

The normalized record schema is intentionally minimal:
    {
        "grant_doc_num": "US1234567B2",
        "prediction": { ...original fields... },
        "_meta": {
            "source_file": "/abs/path/to/file",
            "row_index": 12345,              # best-effort position within file
            "extracted_at": "2025-10-27T12:34:56Z"
        }
    }

Where possible, the extractor will also coerce common score fields to float.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from collections.abc import Generator, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


LOG = logging.getLogger(__name__)

# Optional imports - gracefully degrade when not available
try:  # pragma: no cover - optional
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore

try:  # pragma: no cover - optional
    import pyreadstat  # type: ignore
except Exception:  # pragma: no cover
    pyreadstat = None  # type: ignore

try:  # pragma: no cover - optional
    import pyarrow as pa  # type: ignore
    import pyarrow.parquet as pq  # type: ignore
except Exception:  # pragma: no cover
    pa = None  # type: ignore
    pq = None  # type: ignore


SUPPORTED_EXTENSIONS = (".ndjson", ".jsonl", ".csv", ".dta", ".parquet")


@dataclass(frozen=True)
class _Checkpoint:
    path: Path
    last_offset: int = 0  # meaning depends on file type (line index or row offset)


class USPTOAIExtractor:
    """
    Extractor for USPTO AI prediction datasets with chunked iteration, resume, and normalization.
    """

    def __init__(
        self,
        input_dir: str | Path,
        *,
        checkpoint_dir: str | Path = "data/cache/uspto_ai_checkpoints",
        continue_on_error: bool = True,
        log_every: int = 100_000,
    ) -> None:
        self.input_dir = Path(input_dir)
        if not self.input_dir.exists():
            raise FileNotFoundError(f"Input directory does not exist: {self.input_dir}")
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.continue_on_error = continue_on_error
        self.log_every = max(0, int(log_every))
        self._seen_ids_mem: set[str] = set()

    # ----------------------------
    # Discovery
    # ----------------------------
    def discover_files(self, file_globs: Iterable[str] | None = None) -> list[Path]:
        """
        Discover files under `input_dir` matching supported extensions or provided globs.
        """
        files: list[Path] = []
        if file_globs:
            for pattern in file_globs:
                files.extend(sorted(self.input_dir.glob(pattern)))
        else:
            for ext in SUPPORTED_EXTENSIONS:
                files.extend(sorted(self.input_dir.rglob(f"*{ext}")))
        LOG.info("Discovered %d USPTO AI files under %s", len(files), self.input_dir)
        return files

    # ----------------------------
    # Public streaming APIs
    # ----------------------------
    def stream_raw(
        self,
        file_path: str | Path,
        *,
        chunk_size: int = 10000,
        resume: bool = False,
    ) -> Generator[dict, None, None]:
        """
        Stream raw records from a single file as dictionaries.

        - NDJSON: yields parsed JSON objects per line
        - CSV: yields dict rows using csv.DictReader
        - DTA: chunked reads via pandas.iter or pyreadstat with row_limit/offset
        - Parquet: chunked via pyarrow row groups; fallback to pandas

        Checkpoint/resume:
          - When resume=True, starts at a saved offset (line/row) if available.
          - Saves checkpoint progress periodically and on completion.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        ext = path.suffix.lower()

        if ext in (".ndjson", ".jsonl"):
            yield from self._stream_ndjson(path, chunk_size=chunk_size, resume=resume)
            return
        if ext == ".csv":
            yield from self._stream_csv(path, chunk_size=chunk_size, resume=resume)
            return
        if ext == ".dta":
            yield from self._stream_dta(path, chunk_size=chunk_size, resume=resume)
            return
        if ext == ".parquet":
            yield from self._stream_parquet(path, chunk_size=chunk_size, resume=resume)
            return

        raise ValueError(f"Unsupported file extension for USPTO AI extractor: {ext}")

    def stream_normalized(
        self,
        file_path: str | Path,
        *,
        chunk_size: int = 10000,
        resume: bool = False,
        dedupe: bool = False,
        skip_missing_id: bool = True,
        id_candidates: list[str] | None = None,
    ) -> Generator[dict, None, None]:
        """
        Stream records normalized into the canonical schema:
            {
                "grant_doc_num": str,
                "prediction": dict,
                "_meta": { "source_file": str, "row_index": int, "extracted_at": iso }
            }

        - dedupe=True will drop repeated grant_doc_num values within this process.
        - skip_missing_id=True will skip rows where no grant id can be inferred.
        """
        src = Path(file_path)
        idx = 0
        for rec in self.stream_raw(src, chunk_size=chunk_size, resume=resume):
            idx += 1
            g = self._extract_grant_id(rec, id_candidates=id_candidates)
            if not g:
                if skip_missing_id:
                    continue
            else:
                if dedupe and g in self._seen_ids_mem:
                    continue
                if dedupe:
                    self._seen_ids_mem.add(g)

            out = {
                "grant_doc_num": g,
                "prediction": self._coerce_score_fields(rec),
                "_meta": {
                    "source_file": str(src.resolve()),
                    "row_index": idx,
                    "extracted_at": datetime.now(UTC).isoformat(),
                },
            }
            yield out

    def stream_batches(
        self,
        file_path: str | Path,
        *,
        batch_size: int = 1000,
        resume: bool = False,
        normalized: bool = True,
        dedupe: bool = False,
        skip_missing_id: bool = True,
        id_candidates: list[str] | None = None,
    ) -> Generator[list[dict], None, None]:
        """
        Stream the file but yield lists of dicts (batches) for efficiency.
        """
        batch: list[dict] = []
        it = (
            self.stream_normalized(
                file_path,
                chunk_size=batch_size,
                resume=resume,
                dedupe=dedupe,
                skip_missing_id=skip_missing_id,
                id_candidates=id_candidates,
            )
            if normalized
            else self.stream_raw(file_path, chunk_size=batch_size, resume=resume)
        )
        for rec in it:
            batch.append(rec)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    # ----------------------------
    # File format implementations
    # ----------------------------
    def _stream_ndjson(
        self, path: Path, *, chunk_size: int, resume: bool
    ) -> Generator[dict, None, None]:
        cp = self._load_checkpoint(path) if resume else _Checkpoint(path, 0)
        last_line = cp.last_offset
        emitted = 0
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line_no, raw in enumerate(fh, start=1):
                    if line_no <= last_line:
                        continue
                    s = raw.strip()
                    if not s:
                        continue
                    try:
                        obj = json.loads(s)
                    except Exception as e:
                        self._handle_error(path, f"Invalid JSON at line {line_no}: {e}")
                        continue
                    emitted += 1
                    if self._need_progress_log(emitted):
                        LOG.info(
                            "Streaming %s (ndjson): %s rows processed",
                            path.name,
                            emitted,
                        )
                    # Save checkpoint periodically
                    if emitted % max(1, chunk_size) == 0:
                        self._save_checkpoint(path, line_no)
                    yield obj
                    last_line = line_no
        finally:
            # Save last line index
            self._save_checkpoint(path, last_line)

    def _stream_csv(
        self, path: Path, *, chunk_size: int, resume: bool
    ) -> Generator[dict, None, None]:
        # CSV via stdlib reader for memory-safety
        cp = self._load_checkpoint(path) if resume else _Checkpoint(path, 0)
        last_rows = cp.last_offset
        emitted = 0
        try:
            with path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                # Skip header doesn't count toward offset; offset tracks data rows
                skipped = 0
                for row in reader:
                    skipped += 1
                    if skipped <= last_rows:
                        continue
                    emitted += 1
                    if self._need_progress_log(emitted):
                        LOG.info(
                            "Streaming %s (csv): %s rows processed",
                            path.name,
                            emitted,
                        )
                    if emitted % max(1, chunk_size) == 0:
                        self._save_checkpoint(path, skipped)
                    yield row
                    last_rows = skipped
        finally:
            self._save_checkpoint(path, last_rows)

    def _stream_dta(
        self, path: Path, *, chunk_size: int, resume: bool
    ) -> Generator[dict, None, None]:
        """
        Stream rows from a .dta (Stata) file. Attempts:
            1) pandas iterator get_chunk
            2) pyreadstat with row_limit/row_offset
            3) full pandas read (last resort)
        """
        if pd is None:
            raise RuntimeError("pandas is required to read .dta files for USPTO AI extraction")

        cp = self._load_checkpoint(path) if resume else _Checkpoint(path, 0)
        offset = cp.last_offset
        emitted = 0

        # 1) pandas iterator with resume (approximate by skipping initial chunks)
        try:
            reader = pd.read_stata(path, iterator=True, convert_categoricals=False)  # type: ignore
            # fast-forward to offset
            to_skip = offset
            while to_skip > 0:
                take = min(chunk_size, to_skip)
                try:
                    _ = reader.get_chunk(take)  # type: ignore
                except StopIteration:
                    break
                to_skip -= take

            while True:
                try:
                    chunk = reader.get_chunk(chunk_size)  # type: ignore
                except StopIteration:
                    break
                except Exception as e:
                    LOG.debug("pandas get_chunk failed for %s: %s", path, e)
                    raise
                for rec in chunk.to_dict(orient="records"):
                    emitted += 1
                    if self._need_progress_log(emitted):
                        LOG.info("Streaming %s (dta:pandas): %s rows", path.name, emitted)
                    if emitted % max(1, chunk_size) == 0:
                        offset += chunk_size
                        self._save_checkpoint(path, offset)
                    yield rec
                offset += len(chunk)
            self._save_checkpoint(path, offset)
            return
        except Exception:
            LOG.debug("pandas iterator failed for %s; trying pyreadstat or fallback", path)

        # 2) pyreadstat stride if available
        if pyreadstat is not None:
            try:
                rows_yielded = 0
                total_rows = None
                try:
                    meta = pyreadstat.read_dta_metadata(str(path))
                    total_rows = getattr(meta, "number_of_rows", None)
                except Exception:
                    total_rows = None
                row_off = offset
                while True:
                    df, _ = pyreadstat.read_dta(str(path), row_limit=chunk_size, row_offset=row_off)
                    if df is None or df.shape[0] == 0:
                        break
                    recs = df.to_dict(orient="records")
                    for rec in recs:
                        emitted += 1
                        if self._need_progress_log(emitted):
                            LOG.info(
                                "Streaming %s (dta:pyreadstat): %s rows (total hint=%s)",
                                path.name,
                                emitted,
                                total_rows,
                            )
                        if emitted % max(1, chunk_size) == 0:
                            self._save_checkpoint(path, row_off + emitted)
                        yield rec
                    rows_yielded += len(recs)
                    row_off += len(recs)
                self._save_checkpoint(path, row_off)
                return
            except Exception:
                LOG.debug("pyreadstat streaming failed for %s; trying full pandas read", path)

        # 3) Last resort: full pandas read
        LOG.warning("Falling back to reading entire .dta into memory for %s", path)
        df_full = pd.read_stata(path, convert_categoricals=False)  # type: ignore
        n = len(df_full)
        i = offset
        emitted = 0
        while i < n:
            j = min(n, i + chunk_size)
            chunk = df_full.iloc[i:j]
            for rec in chunk.to_dict(orient="records"):
                emitted += 1
                yield rec
            i = j
            self._save_checkpoint(path, i)

    def _stream_parquet(
        self, path: Path, *, chunk_size: int, resume: bool
    ) -> Generator[dict, None, None]:
        cp = self._load_checkpoint(path) if resume else _Checkpoint(path, 0)
        offset = cp.last_offset
        emitted = 0

        if pq is not None and pa is not None:
            try:
                pf = pq.ParquetFile(path)
                cur = 0
                for rg_idx in range(pf.num_row_groups):
                    tbl = pf.read_row_group(rg_idx)
                    df = tbl.to_pandas()
                    n = len(df)
                    start = 0
                    # Skip within this row group if resuming
                    if offset > 0 and cur + n <= offset:
                        cur += n
                        continue
                    if offset > cur:
                        start = max(0, offset - cur)
                    for i in range(start, n, chunk_size):
                        chunk = df.iloc[i : i + chunk_size]
                        for rec in chunk.to_dict(orient="records"):
                            emitted += 1
                            if self._need_progress_log(emitted):
                                LOG.info(
                                    "Streaming %s (parquet:pyarrow): %s rows",
                                    path.name,
                                    emitted,
                                )
                            if emitted % max(1, chunk_size) == 0:
                                self._save_checkpoint(path, cur + i + len(chunk))
                            yield rec
                    cur += n
                self._save_checkpoint(path, cur)
                return
            except Exception:
                LOG.debug("pyarrow parquet streaming failed for %s; falling back to pandas", path)

        if pd is None:
            raise RuntimeError("pandas is required to read parquet files (fallback)")

        df = pd.read_parquet(path)  # type: ignore
        n = len(df)
        i = offset
        while i < n:
            j = min(n, i + chunk_size)
            chunk = df.iloc[i:j]
            for rec in chunk.to_dict(orient="records"):
                emitted += 1
                yield rec
            i = j
            self._save_checkpoint(path, i)

    # ----------------------------
    # Utilities
    # ----------------------------
    @staticmethod
    def _need_progress_log(count: int) -> bool:
        return count > 0 and (count % 100_000 == 0)

    def _checkpoint_key(self, path: Path) -> Path:
        # Hash-less but deterministic mapping to filesystem-friendly name
        safe = str(path.resolve()).replace(os.sep, "_").replace(":", "_")
        return self.checkpoint_dir / f"{safe}.checkpoint"

    def _load_checkpoint(self, path: Path) -> _Checkpoint:
        ck = self._checkpoint_key(path)
        try:
            if not ck.exists():
                return _Checkpoint(path, 0)
            raw = ck.read_text(encoding="utf-8").strip()
            last = int(raw) if raw else 0
            return _Checkpoint(path, last)
        except Exception:
            return _Checkpoint(path, 0)

    def _save_checkpoint(self, path: Path, last_offset: int) -> None:
        ck = self._checkpoint_key(path)
        try:
            ck.parent.mkdir(parents=True, exist_ok=True)
            ck.write_text(str(int(last_offset)), encoding="utf-8")
        except Exception:
            LOG.debug("Failed to write checkpoint for %s (offset=%s)", path, last_offset)

    def _handle_error(self, path: Path, msg: str) -> None:
        if self.continue_on_error:
            LOG.warning("Continuing after error in %s: %s", path, msg)
        else:
            raise RuntimeError(f"{path}: {msg}")

    @staticmethod
    def _extract_grant_id(rec: dict, id_candidates: list[str] | None = None) -> str | None:
        """
        Attempt to extract a canonical grant_doc_num from common fields.
        """
        candidates = (
            id_candidates
            if id_candidates
            else [
                "grant_doc_num",
                "grant_number",
                "grant_docnum",
                "doc_num",
                "patent_id",
                "publication_number",
                "grant",
                "grant_no",
                "doc_id",
            ]
        )
        for k in candidates:
            v = rec.get(k)
            if v is None:
                # try case-insensitive match
                for kk, vv in rec.items():
                    if isinstance(kk, str) and kk.lower() == k.lower() and vv:
                        v = vv
                        break
            if v:
                s = str(v).strip()
                if s:
                    return s
        return None

    @staticmethod
    def _coerce_score_fields(rec: dict) -> dict:
        """
        Best-effort coercion for common score/predict fields to numeric/boolean types
        while preserving the original keys and payload.
        """
        out = dict(rec)
        float_fields = [
            "ai_score_any_ai",
            "ai_score_ml",
            "ai_score_vision",
            "ai_score_nlp",
            "ai_score_robotics",
            "ai_score_cv",
            "ai_score_nlp_sub",
        ]
        int_bool_fields = [
            "predict93_any_ai",
            "predict_any_ai",
            "is_ai",
        ]
        for f in float_fields:
            if f in out and out[f] is not None and out[f] != "":
                try:
                    out[f] = float(out[f])
                except Exception:
                    pass
        for f in int_bool_fields:
            if f in out and out[f] is not None and out[f] != "":
                try:
                    # preserve 0/1 as int
                    out[f] = int(out[f])
                except Exception:
                    # fallback: bool coercion
                    try:
                        out[f] = (
                            1 if str(out[f]).strip().lower() in ("true", "t", "yes", "1") else 0
                        )
                    except Exception:
                        pass
        return out

    # Convenience helpers
    def read_first_n(self, file_path: str | Path, n: int = 10) -> list[dict]:
        """Return a small preview of the first n raw rows."""
        out: list[dict] = []
        it = self.stream_raw(file_path, chunk_size=n, resume=False)
        for _ in range(n):
            try:
                out.append(next(it))
            except StopIteration:
                break
        return out

    def count_rows_estimate(self, file_path: str | Path) -> int | None:
        """
        Best-effort estimate of row count:
          - NDJSON/CSV: None (requires full scan)
          - DTA: pyreadstat metadata if available
          - Parquet: pyarrow metadata if available
        """
        p = Path(file_path)
        ext = p.suffix.lower()
        try:
            if ext == ".parquet" and pq is not None:
                pf = pq.ParquetFile(p)
                return sum(pf.metadata.row_group(i).num_rows for i in range(pf.num_row_groups))
            if ext == ".dta" and pyreadstat is not None:
                meta = pyreadstat.read_dta_metadata(str(p))
                val = getattr(meta, "number_of_rows", None) or getattr(meta, "rows", None)
                return int(val) if val is not None else None
        except Exception:
            return None
        return None


__all__ = ["USPTOAIExtractor"]
