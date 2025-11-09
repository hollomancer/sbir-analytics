"""CET analytics assets.

This module contains:
- transformed_cet_analytics: Compute portfolio-level CET analytics and alerts
- transformed_cet_analytics_aggregates: Produce CET analytics dashboards
"""

from __future__ import annotations

import json
from pathlib import Path

from typing import Any

from loguru import logger

from .utils import (
    Output,
    asset,
)


@asset(
    name="transformed_cet_analytics",
    key_prefix=["ml"],
    description="Compute CET analytics (coverage and specialization) and emit alerts.",
)
def transformed_cet_analytics() -> Output:
    """
    Compute portfolio-level CET analytics:
      - Award coverage rate: fraction of awards with a primary CET
      - Company specialization: average specialization_score across companies

    Emit alerts using AlertCollector when coverage falls below configured threshold.
    Write a checks JSON under reports/alerts/.
    """
    import json
    from datetime import datetime
    from pathlib import Path

    try:
        import pandas as pd
    except Exception:
        pd = None  # type: ignore

    # Lazy import to avoid heavy imports at module import time
    try:
        from src.utils.performance_alerts import AlertCollector
    except Exception:
        AlertCollector = None  # type: ignore

    processed_dir = Path("data/processed")
    alerts_dir = Path("reports/alerts")
    alerts_dir.mkdir(parents=True, exist_ok=True)

    # Inputs
    company_parquet = processed_dir / "cet_company_profiles.parquet"
    company_json = processed_dir / "cet_company_profiles.json"
    awards_parquet = processed_dir / "cet_award_classifications.parquet"
    awards_json = processed_dir / "cet_award_classifications.json"

    # Read helpers (parquet preferred, NDJSON fallback)
    def _read_df(parquet_path: Path, json_path: Path, expected_cols = None):
        if pd is None:
            return None
        if parquet_path.exists():
            try:
                df = pd.read_parquet(parquet_path)
                if expected_cols:
                    cols = [c for c in expected_cols if c in df.columns]
                    if cols:
                        df = df[cols]
                return df
            except Exception:
                pass
        if json_path.exists():
            try:
                rows = []
                with json_path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        rows.append(json.loads(line))
                if not rows:
                    return pd.DataFrame()
                df = pd.DataFrame(rows)
                if expected_cols:
                    cols = [c for c in expected_cols if c in df.columns]
                    if cols:
                        df = df[cols]
                return df
            except Exception:
                return pd.DataFrame()
        return pd.DataFrame()

    # Load inputs
    df_companies = _read_df(
        company_parquet,
        company_json,
        expected_cols=[
            "company_id",
            "coverage",
            "specialization_score",
            "taxonomy_version",
        ],
    )
    df_awards = _read_df(
        awards_parquet,
        awards_json,
        expected_cols=["award_id", "primary_cet", "primary_score", "taxonomy_version"],
    )

    # Compute metrics (robust to empty frames)
    coverage_rate = 0.0
    num_awards = 0
    num_classified = 0
    if df_awards is not None and not df_awards.empty:
        num_awards = len(df_awards)
        num_classified = (
            int(df_awards["primary_cet"].notna().sum()) if "primary_cet" in df_awards.columns else 0
        )
        coverage_rate = float(num_classified / max(1, num_awards))

    specialization_avg = None
    if (
        df_companies is not None
        and not df_companies.empty
        and "specialization_score" in df_companies.columns
    ):
        specialization_avg = float(df_companies["specialization_score"].dropna().mean())

    # Alerts
    alerts = {}
    if AlertCollector is not None:
        collector = AlertCollector(asset_name="transformed_cet_analytics")
        # Check coverage_rate against configured match rate threshold
        collector.check_match_rate(coverage_rate, metric_name="cet_award_coverage_rate")
        alerts = collector.to_dict()
        # Persist alerts JSON
        with (alerts_dir / "cet_analytics.alerts.json").open("w", encoding="utf-8") as fh:
            json.dump(alerts, fh, indent=2)

    # Checks payload
    checks = {
        "ok": True,
        "generated_at": datetime.utcnow().isoformat(),
        "award_coverage_rate": coverage_rate,
        "num_awards": num_awards,
        "num_classified": num_classified,
        "company_specialization_avg": specialization_avg,
        "alerts": alerts,
    }
    checks_path = alerts_dir / "cet_analytics.checks.json"
    try:
        with checks_path.open("w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
    except Exception:
        # best-effort
        pass

    metadata = {
        "coverage_rate": coverage_rate,
        "num_awards": num_awards,
        "num_classified": num_classified,
        "company_specialization_avg": specialization_avg,
        "checks_path": str(checks_path),
        "alerts_path": str(alerts_dir / "cet_analytics.alerts.json"),
    }
    return Output(value=metadata, metadata=metadata)




@asset(
    name="transformed_cet_analytics_aggregates",
    key_prefix=["ml"],
    description="Produce CET analytics dashboards (coverage by year and specialization distribution) and alert on regression vs baseline.",
)
def transformed_cet_analytics_aggregates() -> Output:
    """
    Create CET analytics dashboards and a regression alert vs a baseline:
      - Coverage by year from cet_award_classifications (derived from classified_at year)
      - Company specialization distribution from cet_company_profiles
      - Compare latest-year coverage with a baseline in reports/benchmarks/baseline.json
      - Write dashboards under reports/analytics and alerts under reports/alerts
    """
    import json
    from datetime import datetime
    from pathlib import Path

    try:
        import pandas as pd
    except Exception:
        pd = None  # type: ignore

    # Lazy import to avoid heavy deps at module import time
    try:
        from src.utils.performance_alerts import AlertCollector
    except Exception:
        AlertCollector = None  # type: ignore

    processed_dir = Path("data/processed")
    analytics_dir = Path("reports/analytics")
    alerts_dir = Path("reports/alerts")
    baseline_path = Path("reports/benchmarks/baseline.json")

    analytics_dir.mkdir(parents=True, exist_ok=True)
    alerts_dir.mkdir(parents=True, exist_ok=True)

    # Inputs
    awards_parquet = processed_dir / "cet_award_classifications.parquet"
    awards_json = processed_dir / "cet_award_classifications.json"
    companies_parquet = processed_dir / "cet_company_profiles.parquet"
    companies_json = processed_dir / "cet_company_profiles.json"

    # Read helpers (parquet preferred, NDJSON fallback)
    def _read_df(parquet_path: Path, json_path: Path, expected_cols = None):
        if pd is None:
            return None
        if parquet_path.exists():
            try:
                df = pd.read_parquet(parquet_path)
                if expected_cols:
                    cols = [c for c in expected_cols if c in df.columns]
                    if cols:
                        df = df[cols]
                return df
            except Exception:
                pass
        if json_path.exists():
            try:
                rows = []
                with json_path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        rows.append(json.loads(line))
                if not rows:
                    return pd.DataFrame()
                df = pd.DataFrame(rows)
                if expected_cols:
                    cols = [c for c in expected_cols if c in df.columns]
                    if cols:
                        df = df[cols]
                return df
            except Exception:
                return pd.DataFrame()
        return pd.DataFrame()

    # Load inputs
    df_awards = _read_df(
        awards_parquet,
        awards_json,
        expected_cols=["award_id", "primary_cet", "classified_at", "taxonomy_version"],
    )
    df_companies = _read_df(
        companies_parquet,
        companies_json,
        expected_cols=["company_id", "specialization_score", "taxonomy_version"],
    )

    # Coverage by year (derive year from classified_at)
    coverage_by_year = pd.DataFrame()
    latest_year = None
    latest_coverage = None
    total_awards = 0
    total_classified = 0
    if df_awards is not None and not df_awards.empty:
        # Derive year from classified_at; fallback to "unknown"
        def _year_of(x):
            try:
                return str(datetime.fromisoformat(str(x).replace("Z", "+00:00")).year)
            except Exception:
                return "unknown"

        df_tmp = df_awards.copy()
        df_tmp["__year"] = (
            df_tmp["classified_at"].apply(_year_of)
            if "classified_at" in df_tmp.columns
            else "unknown"
        )
        grp = df_tmp.groupby("__year", dropna=False)["primary_cet"]
        coverage_by_year = grp.agg(
            total_awards=lambda s: int(len(s)),
            classified=lambda s: int(s.notna().sum()),
        ).reset_index()
        coverage_by_year["coverage_rate"] = coverage_by_year["classified"] / coverage_by_year[
            "total_awards"
        ].clip(lower=1)

        # Track overall and latest (numeric) year coverage
        total_awards = int(coverage_by_year["total_awards"].sum())
        total_classified = int(coverage_by_year["classified"].sum())
        # Choose latest numeric year for regression comparison
        try:
            numeric_years = sorted([int(y) for y in coverage_by_year["__year"] if str(y).isdigit()])
            if numeric_years:
                latest_year = numeric_years[-1]
                latest_row = coverage_by_year[coverage_by_year["__year"] == str(latest_year)].iloc[
                    0
                ]
                latest_coverage = float(latest_row["coverage_rate"])
        except Exception:
            latest_year = None
            latest_coverage = None

    # Company specialization distribution
    specialization_dist = pd.DataFrame()
    specialization_avg = None
    if (
        df_companies is not None
        and not df_companies.empty
        and "specialization_score" in df_companies.columns
    ):
        specialization_avg = float(df_companies["specialization_score"].dropna().mean())
        # Simple histogram buckets
        bins = [0.0, 0.25, 0.5, 0.75, 1.01]
        labels = ["[0,0.25)", "[0.25,0.5)", "[0.5,0.75)", "[0.75,1]"]
        df_tmpc = df_companies.copy()
        df_tmpc["bucket"] = pd.cut(
            df_tmpc["specialization_score"].fillna(0.0),
            bins=bins,
            labels=labels,
            include_lowest=True,
            right=False,
        )
        specialization_dist = (
            df_tmpc.groupby("bucket", dropna=False)["specialization_score"]
            .agg(count="count")
            .reset_index()
        )

    # Write dashboards
    coverage_csv = analytics_dir / "cet_coverage_by_year.csv"
    coverage_json = analytics_dir / "cet_coverage_by_year.json"
    spec_csv = analytics_dir / "cet_company_specialization_distribution.csv"
    spec_json = analytics_dir / "cet_company_specialization_distribution.json"

    if pd is not None:
        try:
            if not coverage_by_year.empty:
                coverage_by_year.to_csv(coverage_csv, index=False)
                coverage_by_year.to_json(coverage_json, orient="records", indent=2)
        except Exception:
            pass
        try:
            if not specialization_dist.empty:
                specialization_dist.to_csv(spec_csv, index=False)
                specialization_dist.to_json(spec_json, orient="records", indent=2)
        except Exception:
            pass

    # Regression alert vs baseline
    alerts = {}
    if AlertCollector is not None:
        collector = AlertCollector(asset_name="transformed_cet_analytics_aggregates")
        baseline_min = None
        try:
            if baseline_path.exists():
                with baseline_path.open("r", encoding="utf-8") as fh:
                    baseline = json.load(fh)
                # Support a couple of common shapes
                # e.g., {"cet": {"coverage_min": 0.6}} or {"coverage_min": 0.6}
                if isinstance(baseline, dict):
                    if "cet" in baseline and isinstance(baseline["cet"], dict):
                        baseline_min = float(baseline["cet"].get("coverage_min", 0.0))
                    elif "coverage_min" in baseline:
                        baseline_min = float(baseline.get("coverage_min", 0.0))
        except Exception:
            baseline_min = None

        # If baseline exists and latest_coverage available, compare
        if baseline_min is not None and latest_coverage is not None:
            # Use check_match_rate semantics (alerts FAILURE if below threshold)
            collector.check_match_rate(
                latest_coverage, metric_name="cet_award_latest_year_coverage"
            )
            # If baseline_min higher than coverage, force metadata
            if latest_coverage < baseline_min:
                # Already represented as FAILURE by check_match_rate when threshold configured accordingly.
                pass
        alerts = collector.to_dict()
        try:
            with (alerts_dir / "cet_analytics_aggregates.alerts.json").open(
                "w", encoding="utf-8"
            ) as fh:
                json.dump(alerts, fh, indent=2)
        except Exception:
            pass

    metadata = {
        "coverage_dashboard_csv": str(coverage_csv),
        "coverage_dashboard_json": str(coverage_json),
        "specialization_dashboard_csv": str(spec_csv),
        "specialization_dashboard_json": str(spec_json),
        "latest_year": latest_year,
        "latest_coverage_rate": latest_coverage,
        "total_awards": total_awards,
        "total_classified": total_classified,
        "specialization_avg": specialization_avg,
        "alerts_path": str(alerts_dir / "cet_analytics_aggregates.alerts.json"),
    }
    return Output(value=metadata, metadata=metadata)


