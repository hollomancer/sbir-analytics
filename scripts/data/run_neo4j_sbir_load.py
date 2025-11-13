#!/usr/bin/env python3
"""Load validated SBIR awards into Neo4j and emit metrics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from dagster import build_asset_context

import src.assets.sbir_neo4j_loading as loading_module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load validated SBIR awards into Neo4j and emit metrics."
    )
    parser.add_argument(
        "--validated-csv",
        required=True,
        type=Path,
        help="Path to validated awards CSV.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory to write loader metrics and summary.",
    )
    parser.add_argument(
        "--summary-md",
        type=Path,
        help="Optional markdown summary path (defaults to output_dir/neo4j_load_summary.md).",
    )
    parser.add_argument(
        "--gha-output",
        type=Path,
        help="Optional path to $GITHUB_OUTPUT for exposing artifact locations.",
    )
    return parser.parse_args()


def _output_value(output: Any) -> Any:
    return getattr(output, "value", output)


def _output_metadata(output: Any) -> dict[str, Any]:
    return getattr(output, "metadata", {}) or {}


def _serialize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Convert Dagster metadata values to JSON-serializable plain values."""
    result = {}
    for key, value in metadata.items():
        # Dagster metadata values have a 'value' attribute containing the actual data
        if hasattr(value, 'value'):
            result[key] = value.value
        else:
            result[key] = value
    return result


def render_markdown_summary(load_result: dict[str, Any]) -> str:
    """Render Neo4j load results as markdown."""
    lines = [
        "# Neo4j SBIR Awards Load",
        "",
        f"**Status:** {load_result.get('status', 'unknown')}",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]

    if load_result.get("status") == "success":
        lines.append(f"| Awards loaded | {load_result.get('awards_loaded', 0)} |")
        lines.append(f"| Awards updated | {load_result.get('awards_updated', 0)} |")
        lines.append(f"| Companies loaded | {load_result.get('companies_loaded', 0)} |")
        lines.append(f"| Companies updated | {load_result.get('companies_updated', 0)} |")
        lines.append(f"| Relationships created | {load_result.get('relationships_created', 0)} |")
        lines.append(f"| Errors | {load_result.get('errors', 0)} |")
        lines.append(f"| Duration (seconds) | {load_result.get('duration_seconds', 0):.2f} |")
    else:
        reason = load_result.get("reason") or load_result.get("error", "unknown")
        lines.append(f"| Reason | {reason} |")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    if not args.validated_csv.exists():
        print(f"Validated CSV not found: {args.validated_csv}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Load validated DataFrame
    validated_df = pd.read_csv(args.validated_csv)

    # Materialize the Neo4j loading asset
    context = build_asset_context()
    load_output = loading_module.neo4j_sbir_awards(context=context, validated_sbir_awards=validated_df)
    load_result = _output_value(load_output)
    load_metadata = _output_metadata(load_output)

    if not isinstance(load_result, dict):
        print(f"Unexpected load result type: {type(load_result)}", file=sys.stderr)
        return 1

    # Write metrics JSON
    metrics_json_path = args.output_dir / "neo4j_load_metrics.json"
    with metrics_json_path.open("w", encoding="utf-8") as f:
        json.dump({"result": load_result, "metadata": _serialize_metadata(load_metadata)}, f, indent=2)
        f.write("\n")

    # Write markdown summary
    summary_md_path = args.summary_md or (args.output_dir / "neo4j_load_summary.md")
    summary_md = render_markdown_summary(load_result)
    summary_md_path.write_text(summary_md, encoding="utf-8")

    if args.gha_output:
        with args.gha_output.open("a", encoding="utf-8") as f:
            f.write(f"neo4j_load_metrics_json={metrics_json_path}\n")
            f.write(f"neo4j_load_summary_md={summary_md_path}\n")
            f.write(f"neo4j_load_status={load_result.get('status', 'unknown')}\n")

    # Run asset check
    check_result = loading_module.neo4j_sbir_awards_load_check(neo4j_sbir_awards=load_result)
    if not check_result.passed:
        print("Neo4j load check failed", file=sys.stderr)
        print(f"Description: {check_result.description}", file=sys.stderr)
        return 1

    if load_result.get("status") != "success":
        reason = load_result.get("reason") or load_result.get("error", "unknown")
        print(f"Neo4j load failed: {reason}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

