#!/usr/bin/env python3
"""Build local DoD awards and CET inputs from the public SBIR.gov bulk CSV."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pandas as pd

from sbir_etl.reporting.dod_supply_chain_baseline import latest_complete_fiscal_year
from sbir_etl.reporting.local_cet_classifier import load_local_cet_rule_classifier


DEFAULT_SOURCE = Path("data/raw/sbir/award_data.csv")
DEFAULT_AWARDS_OUTPUT = Path("data/processed/enriched_sbir_awards.parquet")
DEFAULT_CLASSIFICATIONS_OUTPUT = Path("data/processed/cet_award_classifications.parquet")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--awards-output", type=Path, default=DEFAULT_AWARDS_OUTPUT)
    parser.add_argument(
        "--classifications-output", type=Path, default=DEFAULT_CLASSIFICATIONS_OUTPUT
    )
    parser.add_argument("--min-fiscal-year", type=int, default=2012)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    return parser.parse_args()


def _source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_scalar(value: object) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    try:
        if bool(value != value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _base_award_id(row: pd.Series) -> str:
    tracking = _clean_scalar(row.get("agency_tracking_number"))
    contract = _clean_scalar(row.get("contract"))
    if tracking and contract:
        return f"{tracking}_{contract}"
    if tracking or contract:
        return tracking or contract
    fallback = "|".join(
        _clean_scalar(row.get(name))
        for name in ("agency", "award_year", "company_name", "title", "award_amount")
    )
    return f"sbirgov:{hashlib.sha256(fallback.encode()).hexdigest()[:20]}"


def _deduplicate_award_ids(frame: pd.DataFrame) -> pd.Series:
    base = frame.apply(_base_award_id, axis=1)
    duplicated = base.duplicated(keep=False)
    result = base.copy()
    for index in frame.index[duplicated]:
        fingerprint = "|".join(_clean_scalar(frame.at[index, column]) for column in frame.columns)
        result.at[index] = (
            f"{base.at[index]}#{hashlib.sha256(fingerprint.encode()).hexdigest()[:12]}"
        )
    if result.duplicated().any():
        raise ValueError("stable award IDs remain duplicated after source fingerprinting")
    return result


def build_local_awards(source: Path, *, min_fy: int, max_fy: int) -> pd.DataFrame:
    """Read the public CSV and normalize the completed-year DoD research cohort."""

    query = """
        SELECT
            "Company" AS company_name,
            "Award Title" AS title,
            "Abstract" AS abstract,
            "Topic Code" AS topic_code,
            "Agency" AS agency,
            "Branch" AS branch,
            "Phase" AS phase,
            "Program" AS program,
            "Agency Tracking Number" AS agency_tracking_number,
            "Contract" AS contract,
            TRY_CAST("Proposal Award Date" AS DATE) AS award_date,
            TRY_CAST("Contract End Date" AS DATE) AS contract_end_date,
            TRY_CAST("Award Year" AS INTEGER) AS award_year,
            TRY_CAST("Award Amount" AS DOUBLE) AS award_amount,
            NULLIF(TRIM("UEI"), '') AS company_uei,
            NULLIF(TRIM("Duns"), '') AS company_duns,
            "City" AS company_city,
            "State" AS company_state,
            "Zip" AS company_zip
        FROM read_csv_auto(?, all_varchar=true, ignore_errors=true)
        WHERE "Agency" = 'Department of Defense'
          AND TRY_CAST("Award Year" AS INTEGER) BETWEEN ? AND ?
    """
    frame = duckdb.connect().execute(query, [str(source), min_fy, max_fy]).fetchdf()
    frame = frame.drop_duplicates().reset_index(drop=True)
    missing_dates = frame["award_date"].isna() & frame["award_year"].notna()
    frame.loc[missing_dates, "award_date"] = pd.to_datetime(
        frame.loc[missing_dates, "award_year"].astype("Int64").astype(str) + "-01-01"
    )
    frame["award_id"] = _deduplicate_award_ids(frame)
    frame["state"] = frame["company_state"]
    frame["source_system"] = "SBIR.gov bulk award_data.csv"
    return frame


def write_inputs(
    awards: pd.DataFrame,
    *,
    source: Path,
    awards_output: Path,
    classifications_output: Path,
    min_fy: int,
    max_fy: int,
) -> dict[str, object]:
    """Persist awards, rule classifications, and a provenance manifest."""

    classifier = load_local_cet_rule_classifier()
    classifications = classifier.classify_frame(awards)
    awards_output.parent.mkdir(parents=True, exist_ok=True)
    classifications_output.parent.mkdir(parents=True, exist_ok=True)
    awards.to_parquet(awards_output, index=False)
    classifications.to_parquet(classifications_output, index=False)
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_path": str(source),
        "source_sha256": _source_sha256(source),
        "min_fiscal_year": min_fy,
        "latest_complete_fiscal_year": max_fy,
        "award_rows": len(awards),
        "classified_rows": len(classifications),
        "classification_coverage": len(classifications) / len(awards) if len(awards) else 0.0,
        "taxonomy_version": classifier.taxonomy_version,
        "classifier_version": classifier.version,
        "method_limitations": [
            "SBIR.gov identifiers only; no SAM.gov or USAspending recipient enrichment",
            "deterministic keyword screening; not the missing trained production model",
            "transition survival evidence is generated separately",
        ],
    }
    manifest_path = classifications_output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    args = parse_args()
    if not args.source.exists():
        raise FileNotFoundError(args.source)
    max_fy = latest_complete_fiscal_year(args.as_of)
    awards = build_local_awards(args.source, min_fy=args.min_fiscal_year, max_fy=max_fy)
    manifest = write_inputs(
        awards,
        source=args.source,
        awards_output=args.awards_output,
        classifications_output=args.classifications_output,
        min_fy=args.min_fiscal_year,
        max_fy=max_fy,
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
