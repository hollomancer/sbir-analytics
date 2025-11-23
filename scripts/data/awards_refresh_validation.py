#!/usr/bin/env python3
"""Validate the SBIR awards CSV and emit refresh metadata artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Any
from collections.abc import Iterable, Sequence


DEFAULT_SOURCE_URL = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate SBIR awards CSV and produce metadata outputs."
    )
    parser.add_argument("--csv-path", required=True, type=Path)
    parser.add_argument("--schema-path", required=True, type=Path)
    parser.add_argument("--metadata-dir", required=True, type=Path)
    parser.add_argument(
        "--summary-path",
        required=False,
        type=Path,
        default=Path("reports/awards_data_refresh/latest.md"),
    )
    parser.add_argument(
        "--previous-metadata", required=False, type=Path, help="Optional JSON file for delta calcs."
    )
    parser.add_argument(
        "--source-url",
        required=False,
        default=DEFAULT_SOURCE_URL,
        help="URL used to download the CSV.",
    )
    parser.add_argument(
        "--allow-schema-drift",
        action="store_true",
        help="Warn instead of exiting when the header does not match the expected schema.",
    )
    parser.add_argument(
        "--gha-output",
        type=Path,
        required=False,
        help="Path to $GITHUB_OUTPUT for step outputs.",
    )
    return parser.parse_args()


def load_schema(schema_path: Path) -> list[str]:
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    with schema_path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    # Allow either {"columns": [...]} or [...].
    if isinstance(data, dict):
        columns = data.get("columns")
        if not isinstance(columns, list):
            raise ValueError(f"Schema file {schema_path} missing 'columns' array.")
        return [str(col) for col in columns]
    if isinstance(data, list):
        return [str(col) for col in data]
    raise ValueError(f"Schema file {schema_path} must contain a list of columns.")


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_previous_metadata(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def validate_header(header: Sequence[str], expected: Sequence[str]) -> dict[str, Any]:
    missing = [col for col in expected if col not in header]
    extra = [col for col in header if col not in expected]
    matches = list(header) == list(expected)
    return {
        "matches_expected": matches,
        "missing_columns": missing,
        "extra_columns": extra,
        "expected_columns": list(expected),
        "observed_columns": list(header),
    }


def count_rows(csv_path: Path) -> tuple[int, list[str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as fp:
        reader = csv.reader(fp)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"{csv_path} is empty.")
        row_count = sum(1 for _ in reader)
    return row_count, header


def render_summary_markdown(metadata: dict[str, Any], warnings: Iterable[str]) -> str:
    row_delta = metadata.get("row_delta")
    row_delta_pct = metadata.get("row_delta_pct")
    row_delta_str = f"{row_delta:+,}" if isinstance(row_delta, int) else "N/A"
    if isinstance(row_delta_pct, float):
        row_delta_pct_str = f"{row_delta_pct:+.2%}"
    else:
        row_delta_pct_str = "N/A"
    bytes_total = metadata["bytes"]
    size_mb = bytes_total / (1024 * 1024)
    schema_status = "match" if metadata["schema"]["matches_expected"] else "drift"
    lines = [
        "# SBIR awards dataset refresh",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Source URL | {metadata['source_url']} |",
        f"| Downloaded (UTC) | {metadata['refreshed_at_utc']} |",
        f"| SHA-256 | `{metadata['sha256']}` |",
        f"| File size | {bytes_total:,} bytes ({size_mb:.2f} MiB) |",
        f"| Row count | {metadata['row_count']:,} |",
        f"| Row delta | {row_delta_str} ({row_delta_pct_str}) |",
        f"| Column count | {metadata['column_count']} |",
        f"| Schema status | {schema_status} |",
        "",
    ]
    warnings = list(warnings)
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for note in warnings:
            lines.append(f"- {note}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    csv_path: Path = args.csv_path
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV path not found: {csv_path}")
    metadata_dir: Path = args.metadata_dir
    metadata_dir.mkdir(parents=True, exist_ok=True)
    expected_columns = load_schema(args.schema_path)

    row_count, header = count_rows(csv_path)
    schema_report = validate_header(header, expected_columns)
    if not schema_report["matches_expected"] and not args.allow_schema_drift:
        raise SystemExit(
            "Schema drift detected. Use --allow-schema-drift to continue. "
            f"Missing: {schema_report['missing_columns']} Extra: {schema_report['extra_columns']}"
        )

    size_bytes = csv_path.stat().st_size
    checksum = compute_sha256(csv_path)
    previous_metadata = read_previous_metadata(args.previous_metadata)
    prev_row_count = previous_metadata.get("row_count") if previous_metadata else None
    row_delta = row_count - prev_row_count if isinstance(prev_row_count, int) else None
    row_delta_pct = None
    if isinstance(prev_row_count, int) and prev_row_count > 0:
        row_delta_pct = (row_count - prev_row_count) / prev_row_count

    timestamp = datetime.now(UTC)
    iso_timestamp = timestamp.isoformat().replace("+00:00", "Z")

    metadata: dict[str, Any] = {
        "dataset": "sbir_awards",
        "csv_path": str(csv_path),
        "source_url": args.source_url,
        "refreshed_at_utc": iso_timestamp,
        "sha256": checksum,
        "bytes": size_bytes,
        "row_count": row_count,
        "row_delta": row_delta,
        "row_delta_pct": row_delta_pct,
        "column_count": len(header),
        "schema": schema_report,
    }
    if previous_metadata:
        metadata["previous_metadata_path"] = str(args.previous_metadata)

    base_name = timestamp.strftime("%Y-%m-%d")
    metadata_path = metadata_dir / f"{base_name}.json"
    if metadata_path.exists():
        suffix = timestamp.strftime("%H%M%S")
        metadata_path = metadata_dir / f"{base_name}-{suffix}.json"
    with metadata_path.open("w", encoding="utf-8") as fp:
        json.dump(metadata, fp, indent=2)
        fp.write("\n")

    latest_json_path = metadata_dir / "latest.json"
    with latest_json_path.open("w", encoding="utf-8") as fp:
        json.dump(metadata, fp, indent=2)
        fp.write("\n")

    warnings: list[str] = []
    if row_delta_pct is not None and row_delta_pct < -0.05:
        warnings.append(
            f"Row count dropped by {row_delta_pct:.2%} ({row_delta:+,} rows) compared to the previous snapshot."
        )
    if not schema_report["matches_expected"]:
        warnings.append(
            "Observed header does not match expected schema; inspect metadata before merging."
        )

    summary_markdown = render_summary_markdown(metadata, warnings)
    if args.summary_path:
        args.summary_path.parent.mkdir(parents=True, exist_ok=True)
        args.summary_path.write_text(summary_markdown, encoding="utf-8")

    if args.gha_output:
        with args.gha_output.open("a", encoding="utf-8") as fp:
            fp.write(f"metadata_path={metadata_path}\n")
            fp.write(f"latest_metadata_path={latest_json_path}\n")
            if args.summary_path:
                fp.write(f"summary_path={args.summary_path}\n")

    print(f"Wrote metadata to {metadata_path}")
    if args.summary_path:
        print(f"Wrote summary to {args.summary_path}")
    if warnings:
        for note in warnings:
            print(f"WARNING: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
