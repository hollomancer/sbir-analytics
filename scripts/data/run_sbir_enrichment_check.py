#!/usr/bin/env python3
"""Evaluate SBIR award/company enrichment coverage using local CSV inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.enrichers.company_enricher import enrich_awards_with_companies


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run SBIR company enrichment against local award/company CSVs."
    )
    parser.add_argument("--awards-csv", required=True, type=Path, help="Path to award_data.csv.")
    parser.add_argument(
        "--company-dir",
        required=True,
        type=Path,
        help="Directory containing company search CSVs (glob: *company_search*.csv).",
    )
    parser.add_argument(
        "--output-json",
        required=True,
        type=Path,
        help="Path to write enrichment coverage JSON summary.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        help="Optional markdown summary path (defaults to output-json with .md).",
    )
    parser.add_argument(
        "--gha-output",
        type=Path,
        help="Optional path to $GITHUB_OUTPUT for emitting artifact references.",
    )
    parser.add_argument(
        "--high-threshold",
        type=int,
        default=90,
        help="High score threshold passed to enrich_awards_with_companies (default: 90).",
    )
    parser.add_argument(
        "--low-threshold",
        type=int,
        default=75,
        help="Low score threshold for candidate matches (default: 75).",
    )
    return parser.parse_args()


def load_company_catalog(company_dir: Path) -> pd.DataFrame:
    csv_paths = sorted(company_dir.glob("*company_search*.csv"))
    if not csv_paths:
        raise FileNotFoundError(
            f"No company search CSVs found in {company_dir} (expected pattern '*company_search*.csv')."
        )

    frames: list[pd.DataFrame] = []
    for path in csv_paths:
        frame = pd.read_csv(path)
        frame["_source_file"] = path.name
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def summarize_enrichment(enriched: pd.DataFrame) -> dict[str, Any]:
    method_series = enriched.get("_match_method")
    score_series = enriched.get("_match_score")

    match_counts: dict[str, int] = {}
    matched_rows = 0
    if method_series is not None:
        method_counts = method_series.fillna("unmatched").astype(str).value_counts(dropna=False)
        match_counts = method_counts.to_dict()
        matched_rows = int(method_counts.sum() - method_counts.get("unmatched", 0))
    total_rows = int(len(enriched))
    match_rate = matched_rows / total_rows if total_rows else 0.0

    avg_match_score = None
    if score_series is not None and score_series.notna().any():
        avg_match_score = float(score_series.dropna().mean())

    company_columns = sorted([col for col in enriched.columns if col.startswith("company_")])

    return {
        "total_awards": total_rows,
        "matched_awards": matched_rows,
        "match_rate": match_rate,
        "average_match_score": avg_match_score,
        "match_counts": match_counts,
        "company_columns": company_columns,
    }


def render_markdown_summary(summary: dict[str, Any], company_count: int, award_rows: int) -> str:
    lines = [
        "# SBIR company enrichment coverage",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Award rows | {award_rows:,} |",
        f"| Company rows | {company_count:,} |",
        f"| Matched awards | {summary['matched_awards']:,} |",
        f"| Match rate | {summary['match_rate']:.2%} |",
    ]
    avg_score = summary.get("average_match_score")
    if avg_score is not None:
        lines.append(f"| Average match score | {avg_score:.2f} |")
    lines.append("")
    lines.append("## Matches by method")
    lines.append("")
    lines.append("| Method | Rows |")
    lines.append("| --- | ---: |")
    for method, count in summary["match_counts"].items():
        lines.append(f"| {method} | {count:,} |")
    lines.append("")
    if summary["company_columns"]:
        lines.append("## Company columns merged")
        lines.append("")
        for col in summary["company_columns"]:
            lines.append(f"- {col}")
    else:
        lines.append("No company columns were merged into the awards DataFrame.")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    if not args.awards_csv.exists():
        raise FileNotFoundError(f"Awards CSV not found: {args.awards_csv}")

    awards_df = pd.read_csv(args.awards_csv)
    companies_df = load_company_catalog(args.company_dir)

    enriched_df = enrich_awards_with_companies(
        awards_df,
        companies_df,
        award_company_col="Company",
        company_name_col="Company Name",
        uei_col="UEI",
        duns_col="DUNs",
        high_threshold=args.high_threshold,
        low_threshold=args.low_threshold,
        return_candidates=False,
    )

    summary = summarize_enrichment(enriched_df)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "summary": summary,
                "awards_rows": int(len(awards_df)),
                "company_rows": int(len(companies_df)),
            },
            handle,
            indent=2,
        )
        handle.write("\n")

    markdown_path = args.output_md or args.output_json.with_suffix(".md")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown_summary(
        summary, company_count=int(len(companies_df)), award_rows=int(len(awards_df))
    )
    markdown_path.write_text(markdown, encoding="utf-8")

    if args.gha_output:
        with args.gha_output.open("a", encoding="utf-8") as handle:
            handle.write(f"enrichment_summary_json={args.output_json}\n")
            handle.write(f"enrichment_summary_md={markdown_path}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
