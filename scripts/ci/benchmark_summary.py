#!/usr/bin/env python3
"""Generate a GitHub Actions step summary from benchmark evaluation outputs.

Produces clean markdown with:
- Evaluation results table (always shown)
- Run provenance table (from run_manifest.json)
- Sensitivity report (collapsed)
- Artifact download table with links to the run page
"""

import json
import os
import sys
from pathlib import Path


def fmt(val):
    if isinstance(val, float):
        return f"{val:,.2f}" if val != int(val) else f"{int(val):,}"
    if isinstance(val, int):
        return f"{val:,}"
    return str(val)


def print_evaluation(d: dict) -> None:
    """Print the main evaluation results table."""
    print("## Benchmark Evaluation\n")
    print("| Metric | Count |")
    print("|--------|------:|")
    for key, label in [
        ("total_companies_evaluated", "Companies evaluated"),
        ("companies_subject_to_transition", "Subject to transition benchmark"),
        ("companies_failing_transition", "**Failing transition benchmark**"),
        ("companies_subject_to_commercialization", "Subject to commercialization benchmark"),
        ("companies_failing_commercialization", "**Failing commercialization benchmark**"),
    ]:
        val = d.get(key, 0)
        print(f"| {label} | {fmt(val)} |")
    print()


def print_provenance(manifest: dict) -> None:
    """Print run provenance as a readable table."""
    params = manifest.get("parameters", {})
    sources = manifest.get("data_sources", {})
    sbir = sources.get("sbir_awards", {})
    usa = sources.get("usaspending", {})

    print("<details><summary>Run Provenance</summary>\n")
    print("| Parameter | Value |")
    print("|-----------|-------|")
    if ts := manifest.get("run_timestamp"):
        print(f"| Timestamp | `{ts[:19]}Z` |")
    if fy := params.get("evaluation_fy"):
        print(f"| Fiscal year | {fy} |")
    if ma := params.get("sensitivity_margin_awards"):
        print(f"| Margin (awards) | {ma} |")
    if mr := params.get("sensitivity_margin_ratio"):
        print(f"| Margin (ratio) | {mr} |")
    if src := sbir.get("source"):
        print(f"| SBIR source | {src} |")
    if rc := sbir.get("row_count"):
        print(f"| SBIR awards rows | {fmt(rc)} |")
    if src := usa.get("source"):
        print(f"| USAspending source | {src} |")
    if qc := usa.get("companies_queried"):
        print(f"| USAspending companies queried | {fmt(qc)} |")
    print("\n</details>\n")


def print_sensitivity_report(report_path: Path) -> None:
    """Print the sensitivity report in a collapsible section."""
    content = report_path.read_text().strip()
    print("<details><summary>Sensitivity Report</summary>\n")
    print(content)
    print("\n</details>\n")


def print_artifact_links(fy: str, run_url: str) -> None:
    """Print artifact download table linking to the run page."""
    print(f"## Artifacts\n")
    print(f"Download from the [workflow run artifacts]({run_url}#artifacts).\n")
    print("| Artifact | Contents |")
    print("|----------|----------|")
    print(f"| `benchmark-results-fy{fy}` | Evaluation JSON, sensitivity report, at-risk list, manifests |")
    print(f"| `evaluation-detail-fy{fy}` | Per-company transition & commercialization CSVs |")
    print(f"| `sbir-awards-input-fy{fy}` | Raw SBIR award data used as input |")
    print(f"| `usaspending-data-fy{fy}` | USAspending API cache & obligations CSV |")
    print()


def main():
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/scripts_output")
    fy = os.environ.get("BENCHMARK_FY", "2026")
    run_url = os.environ.get("BENCHMARK_RUN_URL", "")

    # Evaluation results
    eval_path = output_dir / "benchmark_evaluation.json"
    if eval_path.exists():
        with open(eval_path) as f:
            print_evaluation(json.load(f))
    else:
        print("> [!WARNING]\n> Benchmark evaluation file not found.\n")

    # Provenance
    manifest_path = output_dir / "run_manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            print_provenance(json.load(f))

    # Sensitivity report
    report_path = output_dir / f"sensitivity_report_fy{fy}.md"
    if report_path.exists():
        print_sensitivity_report(report_path)

    # Artifact download links
    if run_url:
        print_artifact_links(fy, run_url)


if __name__ == "__main__":
    main()
