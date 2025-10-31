#!/usr/bin/env python3
"""Quality validation script for enrichment output with detailed breakdowns.

This script analyzes enriched SBIR-USAspending output and generates comprehensive
quality reports with breakdowns by:
- Award phase (SBIR Phase I, Phase II, etc)
- Company size (employee count ranges)
- Identifier type (UEI vs DUNS)
- Match method (exact vs fuzzy)

Generates HTML reports with charts, tables, and trend analysis.

Usage:
    python scripts/validate_enrichment_quality.py \
        --enriched-file data/enriched_sbir_awards.parquet \
        --output reports/quality/assessment.html
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


class EnrichmentQualityValidator:
    """Validator for enrichment quality with detailed breakdowns."""

    def __init__(self, enriched_df: pd.DataFrame):
        """Initialize validator with enriched data.

        Args:
            enriched_df: DataFrame with enriched SBIR-USAspending data
        """
        self.df = enriched_df
        self.report = {}

    def validate(self) -> dict[str, Any]:
        """Run full quality validation.

        Returns:
            Dictionary with comprehensive quality assessment
        """
        logger.info(f"Starting quality validation on {len(self.df)} records")

        # Overall statistics
        self.report["overall"] = self._calculate_overall_stats()

        # Breakdowns by dimension
        self.report["by_phase"] = self._breakdown_by_phase()
        self.report["by_company_size"] = self._breakdown_by_company_size()
        self.report["by_identifier_type"] = self._breakdown_by_identifier_type()
        self.report["by_match_method"] = self._breakdown_by_match_method()

        # Quality metrics
        self.report["quality_metrics"] = self._calculate_quality_metrics()

        # Confidence distribution
        self.report["confidence_distribution"] = self._calculate_confidence_distribution()

        # Issues and recommendations
        self.report["issues"] = self._identify_issues()
        self.report["recommendations"] = self._generate_recommendations()

        logger.info("Quality validation complete")
        return self.report

    def _calculate_overall_stats(self) -> dict[str, Any]:
        """Calculate overall enrichment statistics."""
        total = len(self.df)
        matched = self.df["_usaspending_match_method"].notna().sum()
        exact = self.df["_usaspending_match_method"].str.contains("exact", na=False).sum()
        fuzzy = self.df["_usaspending_match_method"].str.contains("fuzzy", na=False).sum()
        unmatched = total - matched

        return {
            "total_records": total,
            "matched_records": matched,
            "exact_matches": exact,
            "fuzzy_matches": fuzzy,
            "unmatched_records": unmatched,
            "overall_match_rate": matched / total if total > 0 else 0,
            "exact_match_rate": exact / total if total > 0 else 0,
            "fuzzy_match_rate": fuzzy / total if total > 0 else 0,
            "timestamp": datetime.now().isoformat(),
        }

    def _breakdown_by_phase(self) -> dict[str, Any]:
        """Break down metrics by SBIR award phase."""
        phase_col = self._find_phase_column()
        if phase_col is None:
            logger.warning("Could not identify phase column")
            return {}

        breakdown = {}
        for phase in sorted(self.df[phase_col].unique()):
            if pd.isna(phase):
                continue
            phase_df = self.df[self.df[phase_col] == phase]
            matched = phase_df["_usaspending_match_method"].notna().sum()
            breakdown[str(phase)] = {
                "total": len(phase_df),
                "matched": matched,
                "match_rate": matched / len(phase_df) if len(phase_df) > 0 else 0,
            }

        return breakdown

    def _breakdown_by_company_size(self) -> dict[str, Any]:
        """Break down metrics by company size (if available)."""
        size_col = self._find_company_size_column()
        if size_col is None:
            logger.warning("Could not identify company size column")
            return {}

        breakdown = {}
        for size_range in sorted(self.df[size_col].unique()):
            if pd.isna(size_range):
                continue
            size_df = self.df[self.df[size_col] == size_range]
            matched = size_df["_usaspending_match_method"].notna().sum()
            breakdown[str(size_range)] = {
                "total": len(size_df),
                "matched": matched,
                "match_rate": matched / len(size_df) if len(size_df) > 0 else 0,
            }

        return breakdown

    def _breakdown_by_identifier_type(self) -> dict[str, Any]:
        """Break down metrics by identifier type (UEI vs DUNS)."""
        breakdown = {
            "both_uei_and_duns": {},
            "uei_only": {},
            "duns_only": {},
            "neither": {},
        }

        # Records with both
        both = self.df[
            (self.df["UEI"].notna())
            & (self.df["UEI"] != "")
            & (self.df["Duns"].notna())
            & (self.df["Duns"] != "")
        ]
        matched_both = both["_usaspending_match_method"].notna().sum()
        breakdown["both_uei_and_duns"] = {
            "total": len(both),
            "matched": matched_both,
            "match_rate": matched_both / len(both) if len(both) > 0 else 0,
        }

        # UEI only
        uei_only = self.df[
            (self.df["UEI"].notna())
            & (self.df["UEI"] != "")
            & ((self.df["Duns"].isna()) | (self.df["Duns"] == ""))
        ]
        matched_uei = uei_only["_usaspending_match_method"].notna().sum()
        breakdown["uei_only"] = {
            "total": len(uei_only),
            "matched": matched_uei,
            "match_rate": matched_uei / len(uei_only) if len(uei_only) > 0 else 0,
        }

        # DUNS only
        duns_only = self.df[
            ((self.df["UEI"].isna()) | (self.df["UEI"] == ""))
            & (self.df["Duns"].notna())
            & (self.df["Duns"] != "")
        ]
        matched_duns = duns_only["_usaspending_match_method"].notna().sum()
        breakdown["duns_only"] = {
            "total": len(duns_only),
            "matched": matched_duns,
            "match_rate": matched_duns / len(duns_only) if len(duns_only) > 0 else 0,
        }

        # Neither
        neither = self.df[
            ((self.df["UEI"].isna()) | (self.df["UEI"] == ""))
            & ((self.df["Duns"].isna()) | (self.df["Duns"] == ""))
        ]
        matched_neither = neither["_usaspending_match_method"].notna().sum()
        breakdown["neither"] = {
            "total": len(neither),
            "matched": matched_neither,
            "match_rate": matched_neither / len(neither) if len(neither) > 0 else 0,
        }

        return breakdown

    def _breakdown_by_match_method(self) -> dict[str, Any]:
        """Break down metrics by match method."""
        breakdown = {}
        for method in sorted(self.df["_usaspending_match_method"].dropna().unique()):
            method_df = self.df[self.df["_usaspending_match_method"] == method]
            breakdown[str(method)] = {
                "count": len(method_df),
                "percentage": len(method_df) / len(self.df) * 100,
            }

        # Unmatched
        unmatched = self.df[self.df["_usaspending_match_method"].isna()]
        breakdown["unmatched"] = {
            "count": len(unmatched),
            "percentage": len(unmatched) / len(self.df) * 100,
        }

        return breakdown

    def _calculate_quality_metrics(self) -> dict[str, Any]:
        """Calculate quality metrics."""
        metrics = {
            "completeness": self._calculate_completeness(),
            "consistency": self._calculate_consistency(),
            "accuracy": self._calculate_accuracy(),
        }
        return metrics

    def _calculate_completeness(self) -> float:
        """Calculate percentage of required fields populated."""
        required_fields = [
            "_usaspending_match_method",
            "_usaspending_match_score",
            "Company",
        ]

        total_required = len(required_fields) * len(self.df)
        populated = sum(
            self.df[field].notna().sum() for field in required_fields if field in self.df.columns
        )

        return populated / total_required if total_required > 0 else 0

    def _calculate_consistency(self) -> float:
        """Calculate consistency (matches across same company)."""
        # For same company names, should get same enrichment
        consistency_issues = 0
        total_groups = 0

        for company in self.df["Company"].unique():
            if pd.isna(company):
                continue
            company_df = self.df[self.df["Company"] == company]
            if len(company_df) > 1:
                total_groups += 1
                methods = company_df["_usaspending_match_method"].unique()
                if len(methods) > 1:
                    consistency_issues += 1

        if total_groups == 0:
            return 1.0
        return 1.0 - (consistency_issues / total_groups)

    def _calculate_accuracy(self) -> float:
        """Calculate accuracy based on fuzzy match scores."""
        if "_usaspending_match_score" not in self.df.columns:
            return 0

        fuzzy_matches = self.df[
            self.df["_usaspending_match_method"].str.contains("fuzzy", na=False)
        ]

        if len(fuzzy_matches) == 0:
            return 0

        # Assume scores >= 85 are accurate
        accurate = (fuzzy_matches["_usaspending_match_score"] >= 85).sum()
        return accurate / len(fuzzy_matches)

    def _calculate_confidence_distribution(self) -> dict[str, int]:
        """Calculate distribution of match confidence scores."""
        if "_usaspending_match_score" not in self.df.columns:
            return {}

        scores = self.df[self.df["_usaspending_match_score"].notna()]["_usaspending_match_score"]

        bins = [0, 75, 80, 85, 90, 95, 100]
        labels = ["<75", "75-80", "80-85", "85-90", "90-95", "95-100"]

        distribution = (
            pd.cut(scores, bins=bins, labels=labels, right=False).value_counts().sort_index()
        )

        return {str(label): int(count) for label, count in distribution.items()}

    def _identify_issues(self) -> list[str]:
        """Identify quality issues."""
        issues = []

        # Low match rate
        overall = self.report["overall"]
        if overall["overall_match_rate"] < 0.70:
            issues.append(
                f"Low overall match rate: {overall['overall_match_rate']:.1%} " f"(target: >=70%)"
            )

        # Poor identifier coverage
        identifiers = self.report["by_identifier_type"]
        if identifiers.get("neither", {}).get("total", 0) > len(self.df) * 0.1:
            issues.append(
                f"High percentage of records without UEI or DUNS: "
                f"{identifiers['neither']['percentage']:.1%}"
            )

        # Consistency issues
        consistency = self.report["quality_metrics"]["consistency"]
        if consistency < 0.95:
            issues.append(
                f"Consistency issues: {1-consistency:.1%} of company groups "
                f"have inconsistent enrichment"
            )

        # Low confidence matches
        confidence = self.report["confidence_distribution"]
        low_conf = confidence.get("<75", 0) + confidence.get("75-80", 0)
        if low_conf > len(self.df) * 0.1:
            issues.append(f"High percentage of low-confidence fuzzy matches: {low_conf} records")

        return issues

    def _generate_recommendations(self) -> list[str]:
        """Generate recommendations for improvement."""
        recommendations = []

        # Based on overall match rate
        overall = self.report["overall"]
        if overall["overall_match_rate"] < 0.70:
            recommendations.append(
                "Improve company name matching algorithm - current match rate below target"
            )

        # Based on identifier types
        identifiers = self.report["by_identifier_type"]
        if identifiers.get("neither", {}).get("total", 0) > 0:
            recommendations.append("Acquire missing UEI and DUNS data to improve matching coverage")

        # Based on phase breakdown
        phases = self.report.get("by_phase", {})
        if phases:
            poor_phases = [
                phase for phase, stats in phases.items() if stats.get("match_rate", 0) < 0.70
            ]
            if poor_phases:
                recommendations.append(
                    f"Focus enrichment improvement on low-performing phases: {', '.join(poor_phases)}"
                )

        # Based on consistency
        consistency = self.report["quality_metrics"]["consistency"]
        if consistency < 0.95:
            recommendations.append(
                "Review and fix company name normalization to improve consistency"
            )

        return recommendations

    def _find_phase_column(self) -> str | None:
        """Find phase column in DataFrame."""
        phase_candidates = [
            col for col in self.df.columns if "phase" in col.lower() or "award_type" in col.lower()
        ]
        return phase_candidates[0] if phase_candidates else None

    def _find_company_size_column(self) -> str | None:
        """Find company size column in DataFrame."""
        size_candidates = [
            col for col in self.df.columns if "size" in col.lower() or "employees" in col.lower()
        ]
        return size_candidates[0] if size_candidates else None


def generate_html_report(report: dict[str, Any], output_path: Path) -> None:
    """Generate HTML report from validation results.

    Args:
        report: Validation report dictionary
        output_path: Path to save HTML report
    """
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>SBIR-USAspending Enrichment Quality Report</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background-color: #2c3e50;
            color: white;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .section {{
            background-color: white;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #34495e;
            color: white;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .metric {{
            display: inline-block;
            margin: 10px 20px 10px 0;
            padding: 15px;
            background-color: #ecf0f1;
            border-radius: 5px;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #2c3e50;
        }}
        .metric-label {{
            font-size: 12px;
            color: #7f8c8d;
        }}
        .good {{
            color: #27ae60;
        }}
        .warning {{
            color: #f39c12;
        }}
        .bad {{
            color: #e74c3c;
        }}
        .issues {{
            background-color: #fff3cd;
            padding: 10px;
            border-left: 4px solid #ffc107;
            margin: 10px 0;
        }}
        .recommendations {{
            background-color: #d1ecf1;
            padding: 10px;
            border-left: 4px solid #17a2b8;
            margin: 10px 0;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>SBIR-USAspending Enrichment Quality Assessment</h1>
        <p>Generated: {report['overall']['timestamp']}</p>
    </div>

    <div class="section">
        <h2>Overall Statistics</h2>
        <div class="metric">
            <div class="metric-value">{report['overall']['total_records']}</div>
            <div class="metric-label">Total Records</div>
        </div>
        <div class="metric">
            <div class="metric-value {('good' if report['overall']['overall_match_rate'] >= 0.70 else 'bad')}">{report['overall']['overall_match_rate']:.1%}</div>
            <div class="metric-label">Match Rate</div>
        </div>
        <div class="metric">
            <div class="metric-value">{report['overall']['matched_records']}</div>
            <div class="metric-label">Matched Records</div>
        </div>
        <div class="metric">
            <div class="metric-value">{report['overall']['unmatched_records']}</div>
            <div class="metric-label">Unmatched Records</div>
        </div>
    </div>

    <div class="section">
        <h2>Match Method Breakdown</h2>
        <table>
            <tr>
                <th>Method</th>
                <th>Count</th>
                <th>Percentage</th>
            </tr>
            {"".join([
                f'<tr><td>{method}</td><td>{data["count"]}</td><td>{data["percentage"]:.1f}%</td></tr>'
                for method, data in report.get('by_match_method', {}).items()
            ])}
        </table>
    </div>

    <div class="section">
        <h2>Breakdown by Identifier Type</h2>
        <table>
            <tr>
                <th>Identifier Type</th>
                <th>Total</th>
                <th>Matched</th>
                <th>Match Rate</th>
            </tr>
            {"".join([
                f'<tr><td>{itype}</td><td>{data["total"]}</td><td>{data["matched"]}</td>'
                f'<td class="{("good" if data["match_rate"] >= 0.70 else "bad")}">{data["match_rate"]:.1%}</td></tr>'
                for itype, data in report.get('by_identifier_type', {}).items()
            ])}
        </table>
    </div>

    <div class="section">
        <h2>Quality Metrics</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Value</th>
            </tr>
            {"".join([
                f'<tr><td>{metric}</td><td>{value:.1%}</td></tr>'
                for metric, value in report.get('quality_metrics', {}).items()
                if isinstance(value, (int, float))
            ])}
        </table>
    </div>

    {"".join([
        f'<div class="section issues"><strong>⚠ Issues:</strong><ul>{"".join([f"<li>{issue}</li>" for issue in report.get("issues", [])])}</ul></div>'
        if report.get('issues') else ''
    ])}

    {"".join([
        f'<div class="section recommendations"><strong>💡 Recommendations:</strong><ul>{"".join([f"<li>{rec}</li>" for rec in report.get("recommendations", [])])}</ul></div>'
        if report.get('recommendations') else ''
    ])}
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html_content)
    logger.info(f"HTML report saved to {output_path}")


def main():
    """Run quality validation."""
    parser = argparse.ArgumentParser(
        description="Validate enrichment quality with detailed breakdowns"
    )
    parser.add_argument(
        "--enriched-file",
        type=Path,
        default="data/enriched/sbir_enriched.parquet",
        help="Path to enriched SBIR data (parquet or CSV)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default="reports/quality/assessment.html",
        help="Output path for HTML report",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional path to save JSON report",
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("SBIR-USAspending Enrichment Quality Validation")
    logger.info("=" * 80)

    try:
        # Load enriched data
        logger.info(f"\nLoading enriched data from {args.enriched_file}")
        if args.enriched_file.suffix == ".parquet":
            df = pd.read_parquet(args.enriched_file)
        else:
            df = pd.read_csv(args.enriched_file)
        logger.info(f"Loaded {len(df)} records")

        # Validate
        logger.info("\nRunning quality validation...")
        validator = EnrichmentQualityValidator(df)
        report = validator.validate()

        # Generate HTML report
        logger.info(f"\nGenerating HTML report: {args.output}")
        generate_html_report(report, args.output)

        # Optionally save JSON
        if args.json_output:
            logger.info(f"Saving JSON report: {args.json_output}")
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.json_output, "w") as f:
                json.dump(report, f, indent=2, default=str)

        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("QUALITY ASSESSMENT SUMMARY")
        logger.info("=" * 80)
        overall = report["overall"]
        logger.info(f"Total Records: {overall['total_records']}")
        logger.info(f"Match Rate: {overall['overall_match_rate']:.1%}")
        logger.info(f"Matched: {overall['matched_records']}")
        logger.info(f"Unmatched: {overall['unmatched_records']}")
        logger.info(f"Exact Matches: {overall['exact_matches']}")
        logger.info(f"Fuzzy Matches: {overall['fuzzy_matches']}")
        logger.info("=" * 80 + "\n")

        return 0

    except Exception as e:
        logger.error(f"Quality validation failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
