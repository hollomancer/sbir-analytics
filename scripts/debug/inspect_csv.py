#!/usr/bin/env python3
"""
sbir-etl/scripts/debug/inspect_csv.py

Small CLI helper to inspect CSV rows safely using Python's csv.reader.

Purpose:
- Quickly find rows with inconsistent field counts (common cause of downstream
  tokenization errors).
- Preview parsed rows and optionally the raw file lines for debugging quoting
  and delimiter issues.
- Try multiple quotechar values to see which one yields consistent parsing.

Usage:
    python sbir-etl/scripts/debug/inspect_csv.py --path tests/fixtures/sbir_sample.csv

Key options:
    --delimiter          CSV delimiter (default: ,)
    --quotechars         One or more quote characters to try (default: '"')
    --expected-columns   If known, assert row lengths == expected columns
    --max-rows           How many rows to scan (default: all)
    --preview            How many first rows to display for a quick look (default: 3)
    --show-raw           Show raw text lines for problematic rows
    --limit-problems     Show up to N problematic rows in detail (default: 10)

Example:
    python sbir-etl/scripts/debug/inspect_csv.py --path tests/fixtures/sbir_sample.csv \
      --delimiter ',' --quotechars '"' "'" --expected-columns 42 --show-raw

This script is intentionally lightweight and does not depend on third-party packages.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


def inspect_csv_once(
    path: Path,
    delimiter: str = ",",
    quotechar: str = '"',
    escapechar: Optional[str] = None,
    expected_columns: Optional[int] = None,
    max_rows: Optional[int] = None,
    preview: int = 3,
    show_raw: bool = False,
    limit_problems: int = 10,
) -> dict:
    """
    Inspect a CSV file using the provided csv.reader parameters.

    Returns a dictionary with summary info and lists of problematic rows.
    """
    summary = {
        "path": str(path),
        "delimiter": delimiter,
        "quotechar": quotechar,
        "escapechar": escapechar,
        "expected_columns": expected_columns,
        "total_rows": 0,
        "length_counts": Counter(),
        "problem_rows": [],  # list of tuples: (row_no, parsed_len, parsed_row)
        "preview_rows": [],
    }

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    # For showing raw lines if requested, load them into a list once for indexing
    raw_lines: List[str] = []
    if show_raw:
        with path.open("r", encoding="utf-8", newline="") as rf:
            raw_lines = rf.readlines()

    # Configure csv.reader; be defensive about quoting settings
    reader_kwargs = {"delimiter": delimiter, "quotechar": quotechar}
    if escapechar is not None:
        reader_kwargs["escapechar"] = escapechar

    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f, **reader_kwargs)
            for i, row in enumerate(reader, start=1):
                summary["total_rows"] += 1
                row_len = len(row)
                summary["length_counts"][row_len] += 1

                # Collect first few parsed rows for preview
                if len(summary["preview_rows"]) < preview:
                    summary["preview_rows"].append((i, row))

                # If expected_columns is provided, treat mismatch as a problem
                is_problem = False
                if expected_columns is not None:
                    if row_len != expected_columns:
                        is_problem = True
                else:
                    # If we don't know expected_columns, flag rows that don't match the
                    # most common length observed so far (heuristic)
                    if i == 1:
                        # cannot decide yet
                        is_problem = False
                    else:
                        # decide based on current dominant length
                        most_common_len, _ = summary["length_counts"].most_common(1)[0]
                        if (
                            row_len != most_common_len
                            and summary["length_counts"][most_common_len] >= 2
                        ):
                            # only declare a problem if the dominant length is stable
                            is_problem = True

                if is_problem and len(summary["problem_rows"]) < limit_problems:
                    summary["problem_rows"].append((i, row_len, row))

                if max_rows is not None and summary["total_rows"] >= max_rows:
                    break

    except csv.Error as e:
        # csv.Error often includes helpful info about the line that failed
        summary["csv_error"] = str(e)
        return summary
    except Exception as e:
        raise

    return summary


def print_summary(
    result: dict, show_raw: bool = False, raw_lines: Optional[List[str]] = None
) -> None:
    """
    Nicely print the summary returned by inspect_csv_once.
    """
    print("\nCSV inspection summary")
    print("----------------------")
    print("path:", result.get("path"))
    print("delimiter:", repr(result.get("delimiter")))
    print("quotechar:", repr(result.get("quotechar")))
    print("escapechar:", repr(result.get("escapechar")))
    print("expected_columns:", result.get("expected_columns"))
    print("total_rows_scanned:", result.get("total_rows"))
    print("unique_parsed_lengths:", sorted(result.get("length_counts").items()))
    if "csv_error" in result:
        print("csv.Error encountered:", result["csv_error"])

    # Show preview rows
    if result.get("preview_rows"):
        print("\nParsed preview (first rows):")
        for i, row in result["preview_rows"]:
            print(f"  {i:>4}: ({len(row):>2} fields) -> {row}")

    # Show problematic rows
    problems = result.get("problem_rows", [])
    if problems:
        print(f"\nFound {len(problems)} problematic rows (showing up to limit):")
        for row_no, parsed_len, parsed_row in problems:
            print(f"  Row {row_no}: parsed_len={parsed_len}")
            print(f"    parsed: {parsed_row}")
            if show_raw and raw_lines is not None:
                # raw_lines uses 0-based indexing
                if 1 <= row_no <= len(raw_lines):
                    raw = raw_lines[row_no - 1].rstrip("\n")
                    print(f"    raw  : {raw!r}")
                else:
                    print("    raw  : <raw line not available>")
    else:
        print("\nNo problematic rows detected under these parsing rules.")

    # Give guidance
    print("\nTips:")
    print(" - If many rows have an unexpected length, inspect the file for mismatched quotes,")
    print("   stray commas inside unquoted fields, or inconsistent use of delimiters/quotes.")
    print(
        " - Try different --quotechars (e.g. '\"' and \"'\") or remove commas from numeric fields"
    )
    print('   (e.g., 1,000 -> 1000) or wrap them in quotes ("1,000").')
    print(
        " - If the file still fails to parse, run this script with --show-raw to inspect the raw text."
    )


def try_multiple_quotechars(
    path: Path,
    delimiter: str,
    quotechars: Iterable[str],
    expected_columns: Optional[int],
    max_rows: Optional[int],
    preview: int,
    show_raw: bool,
    limit_problems: int,
) -> None:
    """Run inspect_csv_once for each quotechar and print compact summaries."""
    # If show_raw we will load the raw lines once
    raw_lines: Optional[List[str]] = None
    if show_raw:
        raw_lines = path.read_text(encoding="utf-8").splitlines()

    for qc in quotechars:
        print("\n" + "=" * 72)
        print(f"Trying quotechar={repr(qc)} (delimiter={repr(delimiter)})")
        print("=" * 72)
        res = inspect_csv_once(
            path=path,
            delimiter=delimiter,
            quotechar=qc,
            escapechar=None,
            expected_columns=expected_columns,
            max_rows=max_rows,
            preview=preview,
            show_raw=show_raw,
            limit_problems=limit_problems,
        )
        print_summary(res, show_raw=show_raw, raw_lines=raw_lines)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Inspect a CSV file for inconsistent row lengths and quoting issues."
    )
    p.add_argument("--path", "-p", required=True, help="Path to CSV file")
    p.add_argument("--delimiter", "-d", default=",", help="Field delimiter (default: ,)")
    p.add_argument(
        "--quotechars",
        "-q",
        nargs="+",
        default=['"'],
        help="Quote characters to try (space-separated). Example: -q '\"' \"'\"",
    )
    p.add_argument(
        "--expected-columns",
        "-e",
        type=int,
        default=None,
        help="If known, assert rows == this number of columns",
    )
    p.add_argument(
        "--max-rows", type=int, default=None, help="Maximum number of rows to scan (default: all)"
    )
    p.add_argument("--preview", type=int, default=3, help="How many parsed rows to preview")
    p.add_argument(
        "--show-raw",
        action="store_true",
        help="Show raw text lines alongside parsed rows for problems",
    )
    p.add_argument(
        "--limit-problems", type=int, default=10, help="How many problematic rows to show in detail"
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    path = Path(args.path)
    try:
        try_multiple_quotechars(
            path=path,
            delimiter=args.delimiter,
            quotechars=args.quotechars,
            expected_columns=args.expected_columns,
            max_rows=args.max_rows,
            preview=args.preview,
            show_raw=args.show_raw,
            limit_problems=args.limit_problems,
        )
    except FileNotFoundError as e:
        print("ERROR:", e, file=sys.stderr)
        return 2
    except Exception as e:
        print("Unexpected ERROR:", repr(e), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
