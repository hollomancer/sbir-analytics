#!/usr/bin/env python3
"""Materialize SBIR ingestion assets against a CSV and emit validation artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
from dagster import build_asset_context

import src.assets.sbir_ingestion as assets_module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run SBIR ingestion assets on a CSV and emit validation outputs."
    )
    parser.add_argument("--csv-path", required=True, type=Path, help="Path to award_data.csv")
    parser.add_argument(
        "--duckdb-path",
        required=True,
        type=Path,
        help="DuckDB database path to use for extraction (will be overwritten).",
    )
    parser.add_argument(
        "--table-name",
        default="sbir_awards_refresh",
        help="DuckDB table name for import (default: sbir_awards_refresh).",
    )
    parser.add_argument(
        "--pass-rate-threshold",
        type=float,
        default=0.95,
        help="Validation pass-rate threshold (default: 0.95).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory to write summary artifacts.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        help="Optional override for validation report JSON (defaults to output_dir/sbir_validation_report.json).",
    )
    parser.add_argument(
        "--summary-md",
        type=Path,
        help="Optional markdown summary path (defaults to output_dir/ingestion_summary.md).",
    )
    parser.add_argument(
        "--gha-output",
        type=Path,
        help="Optional path to $GITHUB_OUTPUT for exposing artifact locations.",
    )
    return parser.parse_args()


def _make_config(csv_path: Path, duckdb_path: Path, table_name: str, threshold: float) -> Any:
    sbir = SimpleNamespace(
        csv_path=str(csv_path), database_path=str(duckdb_path), table_name=table_name
    )
    extraction = SimpleNamespace(sbir=sbir)
    data_quality = SimpleNamespace(
        sbir_awards=SimpleNamespace(pass_rate_threshold=threshold)
    )
    return SimpleNamespace(extraction=extraction, data_quality=data_quality)


def _output_value(output: Any) -> Any:
    return getattr(output, "value", output)


def _output_metadata(output: Any) -> dict[str, Any]:
    return getattr(output, "metadata", {}) or {}


def render_markdown_summary(raw_meta: dict[str, Any], validated_meta: dict[str, Any], report: dict[str, Any]) -> str:
    lines = [
        "# SBIR ingestion validation",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Raw records | {raw_meta.get('num_records', 'N/A')} |",
        f"| Raw columns | {raw_meta.get('num_columns', 'N/A')} |",
        f"| Validation pass rate | {validated_meta.get('pass_rate', 'N/A')} |",
        f"| Passed records | {validated_meta.get('passed_records', 'N/A')} |",
        f"| Failed records | {validated_meta.get('failed_records', 'N/A')} |",
        f"| Validation status | {validated_meta.get('validation_status', 'N/A')} |",
        f"| Report total issues | {len(report.get('issues', []))} |",
        "",
        "## Issues by severity",
        "",
    ]
    issues_by_severity = report.get("issues_by_severity", {})
    if issues_by_severity:
        for severity, count in issues_by_severity.items():
            lines.append(f"- {severity}: {count}")
    else:
        lines.append("- None")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    if not args.csv_path.exists():
        raise FileNotFoundError(f"CSV path not found: {args.csv_path}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.duckdb_path.parent.mkdir(parents=True, exist_ok=True)

    config = _make_config(args.csv_path, args.duckdb_path, args.table_name, args.pass_rate_threshold)
    # Monkeypatch get_config to use our runtime configuration.
    assets_module.get_config = lambda: config  # type: ignore[assignment]

    raw_ctx = build_asset_context()
    raw_output = assets_module.raw_sbir_awards(context=raw_ctx)
    raw_df = _output_value(raw_output)
    if not isinstance(raw_df, pd.DataFrame):
        raise TypeError("raw_sbir_awards did not return a pandas DataFrame.")
    raw_metadata = _output_metadata(raw_output)

    validated_ctx = build_asset_context()
    validated_output = assets_module.validated_sbir_awards(
        context=validated_ctx, raw_sbir_awards=raw_df
    )
    validated_df = _output_value(validated_output)
    if not isinstance(validated_df, pd.DataFrame):
        raise TypeError("validated_sbir_awards did not return a pandas DataFrame.")
    validated_metadata = _output_metadata(validated_output)

    report_ctx = build_asset_context()
    report_output = assets_module.sbir_validation_report(
        context=report_ctx, raw_sbir_awards=raw_df
    )
    report_dict = _output_value(report_output)
    if not isinstance(report_dict, dict):
        raise TypeError("sbir_validation_report did not return a dict.")
    report_metadata = _output_metadata(report_output)

    raw_meta_path = args.output_dir / "raw_sbir_awards_metadata.json"
    validated_meta_path = args.output_dir / "validated_sbir_awards_metadata.json"
    report_json_path = args.report_json or (args.output_dir / "sbir_validation_report.json")
    summary_md_path = args.summary_md or (args.output_dir / "ingestion_summary.md")

    with raw_meta_path.open("w", encoding="utf-8") as handle:
        json.dump({"metadata": raw_metadata}, handle, indent=2)
        handle.write("\n")

    with validated_meta_path.open("w", encoding="utf-8") as handle:
        json.dump({"metadata": validated_metadata}, handle, indent=2)
        handle.write("\n")

    with report_json_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {"report": report_dict, "metadata": report_metadata},
            handle,
            indent=2,
        )
        handle.write("\n")

    summary_md = render_markdown_summary(raw_metadata, validated_metadata, report_dict)
    summary_md_path.write_text(summary_md, encoding="utf-8")

    if args.gha_output:
        with args.gha_output.open("a", encoding="utf-8") as handle:
            handle.write(f"raw_metadata_path={raw_meta_path}\n")
            handle.write(f"validated_metadata_path={validated_meta_path}\n")
            handle.write(f"validation_report_path={report_json_path}\n")
            handle.write(f"ingestion_summary_path={summary_md_path}\n")

    # If validation failed, exit non-zero to alert workflow.
    if report_dict.get("passed") is False:
        json.dump(
            {"error": "Validation failed", "report": report_dict},
            sys.stderr,
            indent=2,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

