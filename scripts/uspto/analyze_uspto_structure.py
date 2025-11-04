#!/usr/bin/env python3
"""
sbir-etl/scripts/uspto/analyze_uspto_structure.py

Initial USPTO data structure analysis script.

Purpose
-------
- Scan a directory containing USPTO data files (commonly Stata .dta files or CSV exports).
- For each file found, read a small sample (configurable) and produce:
    - Column-level summary: dtype, sample non-null fraction, unique counts, example values
    - Suggested primary/key columns (heuristic)
    - Basic statistics for numeric/date fields
    - A human-readable Markdown summary and a JSON report written to reports/uspto_structure_<file>.json

Notes / Requirements
--------------------
- Tries to use pandas first. If reading .dta fails (for very large files or unsupported versions),
  the script will attempt to use pyreadstat if available. If neither works, it will surface a clear error.
- This script is conservative: it inspects a sample (default 5000 rows) so the results are preliminary.
  For definitive counts and referential integrity checks, run the full extractor pipeline (task: USPTOExtractor).
- This is intended as an initial engineering aid for task 1.1 in the USPTO ETL change.

Usage
-----
$ python sbir-etl/scripts/uspto/analyze_uspto_structure.py \
    --input-dir data/raw/uspto \
    --sample-size 5000 \
    --out-dir reports/uspto-structure

Outputs
-------
- JSON files per input file with collected metadata and suggestions.
- A single Markdown summary per run (reports/uspto-structure/summary.md).
"""

from __future__ import annotations

from loguru import logger

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


try:
    import pandas as pd
except Exception:
    pd = None  # type: ignore

# pyreadstat can be used as an alternative/back-up for reading .dta reliably
try:
    import pyreadstat  # type: ignore
except Exception:
    pyreadstat = None  # type: ignore
DEFAULT_SAMPLE = 5000
SUPPORTED_EXT = [".dta", ".csv", ".parquet"]


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def find_uspto_files(input_dir: Path) -> list[Path]:
    files: list[Path] = []
    for ext in SUPPORTED_EXT:
        files.extend(sorted(input_dir.rglob(f"*{ext}")))
    return files


def read_sample_with_pandas(path: Path, nrows: int) -> tuple[Any, int | None]:
    """
    Attempt to read a sample using pandas. Returns (DataFrame, approx_total_rows_or_None).
    For Stata files, pandas supports reading fully but may struggle with huge files; we try to read a small sample
    by using the iterator interface if available; otherwise we read with pyreadstat fallback (else read full and warn).
    """
    if pd is None:
        raise RuntimeError("pandas is required for this script. Install with: pip install pandas")

    suffix = path.suffix.lower()
    logger.debug("Reading sample for %s with pandas (nrows=%s)", path, nrows)
    if suffix == ".csv":
        df = pd.read_csv(path, nrows=nrows)
        # for CSV we can't know total rows cheaply except by scanning; leave as None
        return df, None

    if suffix == ".parquet":
        # Parquet supports row-group-based reading but pandas doesn't expose chunked read easily; read full if small file else error
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb < 200:  # arbitrary safety threshold
            df = pd.read_parquet(path)
            return df.head(nrows), len(df)
        else:
            logger.warning(
                "Large parquet file (~%.1f MB). Attempting to read only first %d rows via pyarrow if available.",
                size_mb,
                nrows,
            )
            try:
                import pyarrow.parquet as pq  # type: ignore

                table = pq.read_table(path, columns=None, use_pandas_metadata=True)
                df = table.to_pandas()
                return df.head(nrows), len(df)
            except Exception:
                raise

    if suffix == ".dta":
        # Try the pandas iterator interface if available
        try:
            # pandas.read_stata(..., iterator=True) returns a StataReader in older versions; attempt it and get_chunk
            reader = pd.read_stata(path, iterator=True, convert_categoricals=False)
            try:
                df = reader.get_chunk(nrows)
            except Exception:
                # fallback to reading normally but only a sample subset (pandas doesn't support skiprows for stata)
                logger.debug("Iterator get_chunk failed; trying pyreadstat fallback if available")
                raise
            # No easy way to get total rows for stata via pandas
            return df, None
        except Exception:
            logger.debug("pandas.read_stata iterator approach failed; trying pyreadstat if available")
            if pyreadstat is not None:
                try:
                    # pyreadstat provides a row_limit kwarg for reading in a subset (best-effort)
                    df, meta = pyreadstat.read_dta(path, row_limit=nrows)
                    total_rows = None
                    # pyreadstat meta may contain row_count in some versions; attempt discovery
                    try:
                        total_rows = getattr(meta, "number_of_rows", None) or getattr(
                            meta, "rows", None
                        )
                    except Exception:
                        total_rows = None
                    return df, total_rows
                except Exception as e:
                    logger.debug("pyreadstat read failed: %s", e)
                    # fallback to attempt full pandas read (dangerous for huge files)
            # Final fallback - attempt full read with pandas (may OOM on very large files)
            logger.warning(
                "Falling back to reading entire .dta file into memory with pandas - may fail for large files."
            )
            df = pd.read_stata(path)
            return df.head(nrows), len(df)
    # Unknown extension
    raise ValueError(f"Unsupported file type for sampling: {path}")


def column_summary(df, sample_size: int = DEFAULT_SAMPLE) -> dict[str, Any]:
    """
    Produce a per-column summary from a dataframe sample.
    """
    summary: dict[str, Any] = {}
    total_rows = len(df)
    for col in df.columns:
        ser = df[col]
        nonnull = ser.dropna()
        nonnull_count = int(nonnull.shape[0])
        null_count = int(total_rows - nonnull_count)
        unique_vals = None
        try:
            unique_vals = int(ser.nunique(dropna=True))
        except Exception:
            unique_vals = None
        dtype = str(ser.dtype)
        # top values
        try:
            # Use value_counts but ensure keys/values are JSON-serializable.
            raw_top = ser.dropna().value_counts(dropna=True).head(5).to_dict()
            # Convert potentially non-string keys (e.g., Timestamp) to strings and counts to ints.
            top = {str(k): int(v) for k, v in raw_top.items()}
        except Exception:
            top = {}
        dtype = str(ser.dtype)
        col_info: dict[str, Any] = {
            "dtype": dtype,
            "nonnull_count": nonnull_count,
            "null_count": null_count,
            "nonnull_fraction": None if total_rows == 0 else round(nonnull_count / total_rows, 4),
            "unique_values": unique_vals,
            "top_values": top,
        }
        # numeric stats
        if pd is not None:
            if pd.api.types.is_numeric_dtype(ser):
                try:
                    col_info["min"] = float(ser.min(skipna=True))
                    col_info["max"] = float(ser.max(skipna=True))
                    col_info["mean"] = float(ser.mean(skipna=True))
                except Exception:
                    pass
            # length stats for object/text
            if pd.api.types.is_object_dtype(ser) or pd.api.types.is_string_dtype(ser):
                try:
                    lens = nonnull.astype(str).map(len)
                    col_info["min_len"] = int(lens.min()) if not lens.empty else None
                    col_info["max_len"] = int(lens.max()) if not lens.empty else None
                    col_info["sample_values"] = list(nonnull.head(10).astype(str).values[:10])
                except Exception:
                    pass
        summary[str(col)] = col_info
    return summary


def detect_key_candidates(df, approx_total_rows: int | None = None) -> list[str]:
    """
    Heuristic: columns which are unique or nearly unique in the sample may be primary keys.
    """
    candidates: list[tuple[str, float]] = []
    total = len(df)
    for col in df.columns:
        try:
            nunique = df[col].nunique(dropna=True)
            # if we know approximate total rows larger than sample, we adjust conservatively
            uniqueness_ratio = nunique / max(total, 1)
            # prefer exact uniqueness (ratio == 1.0) or very high uniqueness
            candidates.append((col, uniqueness_ratio))
        except Exception:
            continue
    # sort by ratio desc
    candidates.sort(key=lambda x: x[1], reverse=True)
    # return those with ratio >= 0.98 or top 3 if none reach threshold
    result = [c for c, r in candidates if r >= 0.98]
    if not result:
        result = [c for c, _ in candidates[:3]]
    return result


def analyze_file(path: Path, sample_size: int, out_dir: Path) -> dict[str, Any]:
    logger.info("Analyzing file: %s", path)
    start = time.time()
    try:
        df_sample, approx_total = read_sample_with_pandas(path, sample_size)
    except Exception as e:
        logger.exception("Failed to read sample for %s: %s", path, e)
        return {"file": str(path), "error": str(e)}

    meta: dict[str, Any] = {
        "file": str(path),
        "sample_rows": len(df_sample),
        "approx_total_rows": approx_total,
        "analyzed_at": now_iso(),
    }

    # Column summaries
    meta["columns"] = column_summary(df_sample, sample_size=sample_size)

    # Candidate keys
    meta["key_candidates"] = detect_key_candidates(df_sample, approx_total_rows=approx_total)

    # Suggest join keys commonly used in USPTO data
    common_names = [
        "rf_id",
        "file_id",
        "documentid",
        "document_id",
        "grant_doc_num",
        "patent_number",
        "doc_num",
    ]
    present_common = [n for n in common_names if n in df_sample.columns]
    meta["present_common_field_names"] = present_common

    # Quick duplicates heuristics on sample for likely keys
    dup_suggest = []
    for col in meta["key_candidates"]:
        try:
            dup_ratio = 1.0 - (df_sample[col].nunique(dropna=True) / max(1, len(df_sample)))
            dup_suggest.append({"column": col, "duplicate_fraction": round(dup_ratio, 4)})
        except Exception:
            pass
    meta["duplicate_estimates"] = dup_suggest

    # Basic coverage metrics
    coverage = {}
    for col, info in meta["columns"].items():
        coverage[col] = {
            "nonnull_fraction": info.get("nonnull_fraction"),
            "unique_count": info.get("unique_values"),
        }
    meta["coverage_summary"] = coverage

    # Save JSON & markdown summary
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{path.stem}.uspto_structure.json"
    md_path = out_dir / "summary.md"

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)

    # Append a short markdown summary for the run
    with open(md_path, "a", encoding="utf-8") as mf:
        mf.write(f"## File: {path.name}\n\n")
        mf.write(f"- Sample rows analyzed: {len(df_sample)}\n")
        if approx_total is not None:
            mf.write(f"- Approx total rows: {approx_total}\n")
        mf.write(f"- Candidate key columns: {meta['key_candidates']}\n")
        if present_common:
            mf.write(f"- Common USPTO-like fields present: {present_common}\n")
        mf.write("- Top columns (summary):\n\n")
        for col, info in list(meta["columns"].items())[:10]:
            mf.write(
                f"  - **{col}** ({info.get('dtype')}): nonnull_fraction={info.get('nonnull_fraction')} unique={info.get('unique_values')}\n"
            )
        mf.write("\n\n")

    took = time.time() - start
    logger.info("Analyzed %s in %.2fs; report: %s", path.name, took, json_path)
    meta["elapsed_seconds"] = took
    return meta


def main():
    parser = argparse.ArgumentParser(
        description="Analyze USPTO data file structure (initial analysis)."
    )
    parser.add_argument(
        "--input-dir",
        "-i",
        type=str,
        default="data/raw/uspto",
        help="Directory containing USPTO files (.dta, .csv, .parquet).",
    )
    parser.add_argument(
        "--sample-size",
        "-n",
        type=int,
        default=DEFAULT_SAMPLE,
        help=f"Number of rows to sample per file (default {DEFAULT_SAMPLE}).",
    )
    parser.add_argument(
        "--out-dir",
        "-o",
        type=str,
        default="reports/uspto-structure",
        help="Output directory for JSON/markdown reports.",
    )
    parser.add_argument(
        "--skip-extensions",
        "-s",
        nargs="*",
        default=[],
        help="File extensions to skip (e.g., .parquet).",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging.")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s - %(message)s",
    )

    input_dir = Path(args.input_dir)
    out_dir = Path(args.out_dir)

    if not input_dir.exists():
        logger.error("Input directory does not exist: %s", input_dir)
        sys.exit(2)

    files = find_uspto_files(input_dir)
    if not files:
        logger.warning("No supported files found under %s (extensions: %s)", input_dir, SUPPORTED_EXT)
        sys.exit(0)

    # Filter skip extensions
    if args.skip_extensions:
        skip_set = {
            x.lower() if x.startswith(".") else f".{x.lower()}" for x in args.skip_extensions
        }
        files = [f for f in files if f.suffix.lower() not in skip_set]

    logger.info("Found %d files to analyze", len(files))
    summary: list[dict[str, Any]] = []
    for fp in files:
        try:
            meta = analyze_file(fp, args.sample_size, out_dir=out_dir)
            summary.append(meta)
        except Exception as e:
            logger.exception("Error analyzing file %s: %s", fp, e)
            summary.append({"file": str(fp), "error": str(e)})

    # Write run-level summary
    run_summary = {
        "run_at": now_iso(),
        "input_dir": str(input_dir),
        "files_analyzed": [os.path.basename(s.get("file", "")) for s in summary],
        "file_count": len(summary),
        "reports_dir": str(out_dir),
    }
    with open(out_dir / "run_summary.json", "w", encoding="utf-8") as fh:
        json.dump({"run": run_summary, "details": summary}, fh, indent=2, ensure_ascii=False)

    logger.info("Completed analysis. Reports written under %s", out_dir)
    print("Completed analysis. Reports written under", out_dir)


if __name__ == "__main__":
    main()
