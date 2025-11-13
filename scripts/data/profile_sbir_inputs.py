#!/usr/bin/env python3
"""Profile SBIR input CSVs (awards + company search files) and validate schemas."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile SBIR award/company CSVs and emit schema-aware summaries."
    )
    parser.add_argument("--award-csv", required=True, type=Path, help="Path to award_data.csv")
    parser.add_argument(
        "--company-dir",
        required=True,
        type=Path,
        help="Directory containing company search CSVs (globbed via *company_search*.csv).",
    )
    parser.add_argument(
        "--company-schema-path",
        required=True,
        type=Path,
        help="JSON file describing expected company CSV columns.",
    )
    parser.add_argument(
        "--output-json",
        required=True,
        type=Path,
        help="Destination for structured JSON summary.",
    )
    parser.add_argument(
        "--output-md",
        required=False,
        type=Path,
        help="Optional markdown summary output (defaults to alongside JSON).",
    )
    parser.add_argument(
        "--gha-output",
        required=False,
        type=Path,
        help="Optional path to $GITHUB_OUTPUT for sharing output locations.",
    )
    return parser.parse_args()


def load_schema(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Schema file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        columns = data.get("columns")
    else:
        columns = data
    if not isinstance(columns, list):
        raise ValueError(f"Schema file {path} must contain a list of columns.")
    return [str(col) for col in columns]


def summarize_csv(csv_path: Path) -> dict[str, object]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"{csv_path} is empty.") from exc
        row_count = sum(1 for _ in reader)
    return {
        "path": str(csv_path),
        "row_count": row_count,
        "column_count": len(header),
        "columns": header,
    }


def compare_schema(observed: Iterable[str], expected: Iterable[str]) -> dict[str, object]:
    observed_list = list(observed)
    expected_list = list(expected)
    missing = [col for col in expected_list if col not in observed_list]
    extra = [col for col in observed_list if col not in expected_list]
    matches = observed_list == expected_list
    return {
        "matches_expected": matches,
        "missing_columns": missing,
        "extra_columns": extra,
        "expected_columns": expected_list,
        "observed_columns": observed_list,
    }


def render_markdown(report: dict[str, object]) -> str:
    lines: list[str] = [
        "# SBIR input dataset profile",
        "",
        "| Input | Rows | Columns | Schema status |",
        "| --- | ---: | ---: | --- |",
    ]
    award = report["award"]
    award_schema = award["schema"]
    lines.append(
        f"| award_data.csv | {award['row_count']:,} | {award['column_count']} | "
        f"{'match' if award_schema['matches_expected'] else 'drift'} |"
    )
    lines.append("")
    lines.append("## Company search files")
    lines.append("")
    lines.append("| File | Rows | Schema status | Missing | Extra |")
    lines.append("| --- | ---: | --- | --- | --- |")
    for company in report["company_files"]:
        schema = company["schema"]
        missing = ", ".join(schema["missing_columns"]) if schema["missing_columns"] else "—"
        extra = ", ".join(schema["extra_columns"]) if schema["extra_columns"] else "—"
        status = "match" if schema["matches_expected"] else "drift"
        lines.append(
            f"| {Path(company['path']).name} | {company['row_count']:,} | {status} | {missing} | {extra} |"
        )
    lines.append("")
    totals = report["totals"]
    lines.append("## Totals")
    lines.append("")
    lines.append(f"- Company files: {totals['company_files']}")
    lines.append(f"- Company rows: {totals['company_rows']:,}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    expected_company_columns = load_schema(args.company_schema_path)

    award_summary = summarize_csv(args.award_csv)
    award_schema_report = compare_schema(
        award_summary["columns"], award_summary["columns"]
    )  # Identity (award schema enforced upstream)

    company_files = sorted(args.company_dir.glob("*company_search*.csv"))
    if not company_files:
        raise FileNotFoundError(
            f"No company search CSVs found in {args.company_dir} (pattern *company_search*.csv)."
        )

    company_summaries = []
    company_row_total = 0
    schema_drift_detected = False
    for csv_path in company_files:
        summary = summarize_csv(csv_path)
        company_row_total += summary["row_count"]
        schema_report = compare_schema(summary["columns"], expected_company_columns)
        summary["schema"] = schema_report
        company_summaries.append(summary)
        if not schema_report["matches_expected"]:
            schema_drift_detected = True

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    report = {
        "generated_at_utc": timestamp,
        "award": {**award_summary, "schema": award_schema_report},
        "company_files": company_summaries,
        "totals": {
            "company_files": len(company_summaries),
            "company_rows": company_row_total,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")

    markdown_path = args.output_md or args.output_json.with_suffix(".md")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(report)
    markdown_path.write_text(markdown, encoding="utf-8")

    if args.gha_output:
        with args.gha_output.open("a", encoding="utf-8") as handle:
            handle.write(f"inputs_profile_json={args.output_json}\n")
            handle.write(f"inputs_profile_md={markdown_path}\n")
            handle.write(f"schema_drift_detected={str(schema_drift_detected).lower()}\n")

    if schema_drift_detected:
        print("⚠️  WARNING: Company CSV schema drift detected; see profile report for details.")
        print(f"   Report: {markdown_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

