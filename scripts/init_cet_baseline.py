#!/usr/bin/env python3
"""
Initialize CET baseline metrics from processed artifacts.

This script computes a baseline for CET analytics (award coverage and company
specialization) from existing processed artifacts and writes a baseline JSON
to `reports/benchmarks/baseline.json` by default.

Typical usage (defaults assume assets have been run and produced dashboards):
    python scripts/init_cet_baseline.py

Options:
    --coverage-path PATH      Path to coverage JSON/CSV produced by `cet_analytics_aggregates`
                              (default: reports/analytics/cet_coverage_by_year.json)
    --companies-path PATH     Path to company profiles parquet/json (default:
                              data/processed/cet_company_profiles.parquet)
    --awards-parquet PATH     Alternative: path to cet_award_classifications.parquet to compute
                              coverage directly from award-level classifications.
    --output PATH             Output baseline JSON path (default: reports/benchmarks/baseline.json)
    --coverage-min FLOAT      Optional explicit minimum coverage threshold to record.
    --specialization-min FLOAT Optional explicit minimum specialization threshold to record.
    --force                   Overwrite existing baseline.json if present.
    --set-thresholds          When set, derive thresholds from current metrics (no margin).
    --quiet                   Reduce console output.

The script is robust to missing optional dependencies (pandas). It will attempt
to read JSON/NDJSON/parquet where available and fall back to conservative defaults.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def try_import_pandas():
    try:
        import pandas as pd  # type: ignore

        return pd
    except Exception:
        return None


def read_json_records(path: Path) -> list[dict[str, Any]]:
    """Read a JSON array file or NDJSON (one JSON object per line) and return list of records."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
        text = text.strip()
        if not text:
            return []
        # Try array JSON first
        if text.startswith("["):
            data = json.loads(text)
            if isinstance(data, list):
                return data
        # Fallback to NDJSON
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        records.append(obj)
                except Exception:
                    # ignore malformed line
                    continue
        return records
    except Exception as e:
        logger.debug("Failed to read JSON records from %s: %s", path, e)
        return []


def read_parquet_dataframe(path: Path, pd) -> pd.DataFrame | None:
    """Attempt to read a parquet into a DataFrame using pandas if available."""
    if pd is None:
        return None
    try:
        if path.exists():
            return pd.read_parquet(path)
    except Exception as e:
        logger.debug("Failed to read parquet %s: %s", path, e)
    return None


def compute_coverage_from_awards_parquet(path: Path, pd) -> dict[str, Any] | None:
    """Compute overall coverage metrics from award-level classifications parquet/ndjson."""
    if pd is None:
        return None
    df = read_parquet_dataframe(path, pd)
    if df is None:
        # Try NDJSON fallback
        ndjson_path = path.with_suffix(".json")
        records = read_json_records(ndjson_path)
        if not records:
            return None
        try:
            df = pd.DataFrame(records)
        except Exception:
            return None
    if df is None or df.empty:
        return None

    total_awards = len(df)
    if "primary_cet" in df.columns:
        num_classified = int(df["primary_cet"].notna().sum())
    else:
        # Try to infer primary fields
        num_classified = int(df.apply(lambda r: r.get("primary_cet") is not None, axis=1).sum())

    coverage = float(num_classified) / max(1, total_awards)
    # Best-effort derive latest year if classified_at exists
    latest_year = None
    if "classified_at" in df.columns:
        try:
            # parse ISO-ish times safely
            years = []
            for v in df["classified_at"].dropna().astype(str):
                try:
                    # Replace trailing Z with +00:00 for fromisoformat
                    years.append(datetime.fromisoformat(v.replace("Z", "+00:00")).year)
                except Exception:
                    continue
            if years:
                latest_year = max(years)
        except Exception:
            latest_year = None

    return {
        "total_awards": total_awards,
        "num_classified": num_classified,
        "coverage_rate": coverage,
        "latest_year": latest_year,
    }


def compute_specialization_from_companies(path: Path, pd) -> dict[str, Any] | None:
    """Compute average specialization_score from company profiles parquet/ndjson."""
    if pd is None:
        return None
    df = read_parquet_dataframe(path, pd)
    if df is None:
        ndjson_path = path.with_suffix(".json")
        records = read_json_records(ndjson_path)
        if not records:
            return None
        try:
            df = pd.DataFrame(records)
        except Exception:
            return None
    if df is None or df.empty:
        return None
    if "specialization_score" in df.columns:
        vals = pd.to_numeric(df["specialization_score"], errors="coerce").dropna()
        if vals.empty:
            return {"specialization_avg": None, "company_count": len(df)}
        return {"specialization_avg": float(vals.mean()), "company_count": int(len(df))}
    # fallback to cet_specialization_score
    if "cet_specialization_score" in df.columns:
        vals = pd.to_numeric(df["cet_specialization_score"], errors="coerce").dropna()
        if vals.empty:
            return {"specialization_avg": None, "company_count": len(df)}
        return {"specialization_avg": float(vals.mean()), "company_count": int(len(df))}
    return {"specialization_avg": None, "company_count": len(df)}


def write_baseline(out_path: Path, payload: dict[str, Any], force: bool = False) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and not force:
        logger.error("Baseline file %s already exists; use --force to overwrite", out_path)
        raise FileExistsError(str(out_path))
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(out_path)
    logger.info("Baseline written to %s", out_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize CET baseline from processed artifacts")
    parser.add_argument(
        "--coverage-path",
        type=str,
        default="reports/analytics/cet_coverage_by_year.json",
        help="Path to coverage JSON/NDJSON/CSV produced by cet_analytics_aggregates",
    )
    parser.add_argument(
        "--companies-path",
        type=str,
        default="data/processed/cet_company_profiles.parquet",
        help="Path to company profiles parquet or JSON",
    )
    parser.add_argument(
        "--awards-parquet",
        type=str,
        default="data/processed/cet_award_classifications.parquet",
        help="Alternative: awards parquet to compute coverage directly",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="reports/benchmarks/baseline.json",
        help="Output baseline JSON path",
    )
    parser.add_argument(
        "--coverage-min",
        type=float,
        default=None,
        help="Optional explicit minimum coverage threshold to record in baseline",
    )
    parser.add_argument(
        "--specialization-min",
        type=float,
        default=None,
        help="Optional explicit minimum specialization threshold to record in baseline",
    )
    parser.add_argument(
        "--set-thresholds",
        action="store_true",
        help="Set thresholds equal to current metrics (no margin).",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing baseline file.")
    parser.add_argument("--quiet", action="store_true", help="Suppress info logs.")
    args = parser.parse_args(argv)

    if args.quiet:
        logger.setLevel(logging.WARNING)

    pd = try_import_pandas()
    if pd is None:
        logger.debug("Pandas not available; will attempt JSON/NDJSON fallbacks where possible")

    # Try coverage path (prefer precomputed dashboard)
    coverage_path = Path(args.coverage_path)
    latest_coverage_rate = None
    latest_year = None

    if coverage_path.exists():
        logger.info("Reading coverage dashboard from %s", coverage_path)
        records = read_json_records(coverage_path)
        if records:
            # Expect records to include fields: __year or year, coverage_rate or coverage
            # Normalize to a list of dicts with keys "__year" and "coverage_rate"
            normalized = []
            for r in records:
                year = (
                    r.get("__year")
                    or r.get("year")
                    or r.get("classified_year")
                    or r.get("year_str")
                )
                # Some dashboards use 'coverage_rate' or 'coverage'
                cov = r.get("coverage_rate")
                if cov is None:
                    cov = r.get("coverage")
                try:
                    cov = float(cov) if cov is not None else None
                except Exception:
                    cov = None
                normalized.append(
                    {"__year": str(year) if year is not None else "unknown", "coverage_rate": cov}
                )
            # Choose latest numeric year if present
            numeric_years = [int(x["__year"]) for x in normalized if str(x["__year"]).isdigit()]
            if numeric_years:
                try:
                    my = max(numeric_years)
                    latest_year = my
                    for x in normalized:
                        if str(x["__year"]) == str(my):
                            latest_coverage_rate = x.get("coverage_rate")
                            break
                except Exception:
                    latest_year = None
                    latest_coverage_rate = None
            else:
                # Fallback: if only one record, use it
                if normalized:
                    latest_coverage_rate = normalized[-1].get("coverage_rate")
                    latest_year = normalized[-1].get("__year")
    else:
        logger.info(
            "Coverage dashboard %s not found; will attempt to compute from awards parquet",
            coverage_path,
        )

    if latest_coverage_rate is None:
        # Try compute from awards parquet
        awards_parquet = Path(args.awards_parquet)
        cov = compute_coverage_from_awards_parquet(awards_parquet, pd)
        if cov:
            latest_coverage_rate = cov.get("coverage_rate")
            latest_year = cov.get("latest_year")
            logger.info(
                "Computed coverage from awards parquet: coverage=%s, year=%s",
                latest_coverage_rate,
                latest_year,
            )
        else:
            logger.warning(
                "Unable to determine coverage rate from available artifacts; defaulting to 0.0"
            )
            latest_coverage_rate = 0.0

    # Specialization
    companies_path = Path(args.companies_path)
    spec = compute_specialization_from_companies(companies_path, pd)
    specialization_avg = None
    if spec:
        specialization_avg = spec.get("specialization_avg")
        logger.info("Computed company specialization average: %s", specialization_avg)
    else:
        logger.warning("Unable to determine specialization average; defaulting to null")
        specialization_avg = None

    # Derive thresholds
    coverage_min = args.coverage_min
    specialization_min = args.specialization_min

    if args.set_thresholds:
        coverage_min = latest_coverage_rate
        specialization_min = specialization_avg

    # If neither provided, create conservative thresholds (e.g., current - 5% absolute with floor 0)
    if coverage_min is None:
        if latest_coverage_rate is not None and not math.isnan(latest_coverage_rate):
            coverage_min = max(0.0, latest_coverage_rate - 0.05)
        else:
            coverage_min = 0.0
    if specialization_min is None:
        if specialization_avg is not None and not math.isnan(specialization_avg):
            specialization_min = max(0.0, specialization_avg - 0.05)
        else:
            specialization_min = None

    baseline_payload: dict[str, Any] = {
        "created_at": datetime.utcnow().isoformat(),
        "coverage": {
            "latest_year": latest_year,
            "latest_coverage_rate": None
            if latest_coverage_rate is None
            else float(latest_coverage_rate),
            "coverage_min_threshold": None if coverage_min is None else float(coverage_min),
        },
        "specialization": {
            "specialization_avg": None if specialization_avg is None else float(specialization_avg),
            "specialization_min_threshold": None
            if specialization_min is None
            else float(specialization_min),
        },
        "source": {
            "coverage_dashboard": str(coverage_path) if coverage_path.exists() else None,
            "awards_parquet": str(Path(args.awards_parquet))
            if Path(args.awards_parquet).exists()
            else None,
            "companies_parquet": str(companies_path) if companies_path.exists() else None,
        },
        "notes": {
            "generated_by": "scripts/init_cet_baseline.py",
            "generated_at": datetime.utcnow().isoformat(),
        },
    }

    output_path = Path(args.output)
    try:
        write_baseline(output_path, baseline_payload, force=args.force)
    except FileExistsError:
        logger.error("Baseline file exists and --force not provided. Exiting.")
        return 2
    except Exception as e:
        logger.exception("Failed to write baseline: %s", e)
        return 3

    logger.info("Baseline initialization complete.")
    logger.info(
        "Baseline summary: coverage %.3f (min %.3f), specialization_avg %s (min %s)",
        baseline_payload["coverage"]["latest_coverage_rate"] or 0.0,
        baseline_payload["coverage"]["coverage_min_threshold"] or 0.0,
        baseline_payload["specialization"]["specialization_avg"],
        baseline_payload["specialization"]["specialization_min_threshold"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
