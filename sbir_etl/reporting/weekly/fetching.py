"""Data loading, cleaning, and historical-context queries for the weekly report."""

import sys
from datetime import UTC, datetime, timedelta


from sbir_etl.extractors.sbir import SbirDuckDBExtractor
from sbir_etl.extractors.sbir_gov_api import SBIR_AWARDS_CSV_URL as SBIR_AWARDS_URL
from sbir_etl.utils.text_normalization import normalize_name as _normalize_name
from sbir_etl.validators.sbir_awards import validate_sbir_award_record as _validate_record
from sbir_etl.enrichers.award_history import (
    get_company_history as _lib_get_company_history,
    get_pi_history as _lib_get_pi_history,
)
from sbir_etl.utils.cloud_storage import (
    SbirAwardsSource as DataSource,
    check_sbir_data_freshness as _check_data_freshness_lib,
    resolve_sbir_awards_csv as _resolve_csv_path_lib,
)


def _resolve_csv_path() -> DataSource:
    source = _resolve_csv_path_lib(download_url=SBIR_AWARDS_URL)
    print(f"Resolved CSV: {source.path} (origin={source.origin})", file=sys.stderr)
    return source


def _check_data_freshness(source: DataSource, max_award_date: str | None, days: int) -> list[str]:
    return _check_data_freshness_lib(source, max_award_date, days)


def fetch_weekly_awards(
    days: int = 7,
) -> tuple[list[dict], list[str], DataSource, SbirDuckDBExtractor, str]:
    """Load SBIR CSV and filter for awards in the past N days.

    Uses SbirDuckDBExtractor for fast columnar import and SQL-based
    date filtering.

    Returns (awards, freshness_warnings, source, extractor, table).
    The source/extractor/table can be reused for historical queries to avoid
    re-downloading and re-importing the ~376 MB CSV.
    """
    source = _resolve_csv_path()
    cutoff_str = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")

    extractor = SbirDuckDBExtractor(
        csv_path=source.path,
        duckdb_path=":memory:",
        use_s3_first=False,  # we already resolved the path
    )
    extractor.import_csv()

    table = extractor._table_identifier
    query = (
        f"SELECT * FROM {table} "
        f"WHERE \"Proposal Award Date\" >= '{cutoff_str}' "
        f'ORDER BY "Proposal Award Date" DESC, '
        f'TRY_CAST("Award Amount" AS DOUBLE) DESC'
    )

    df = extractor.duckdb_client.execute_query_df(query)
    print(f"Found {len(df)} awards since {cutoff_str} (DuckDB)", file=sys.stderr)
    awards = df.fillna("").to_dict("records")

    # Get max date across the full dataset for freshness check
    max_date_df = extractor.duckdb_client.execute_query_df(
        f'SELECT MAX("Proposal Award Date") AS max_date FROM {table}'
    )
    max_award_date = str(max_date_df.iloc[0]["max_date"]) if len(max_date_df) else None

    # Verify data freshness
    freshness_warnings = _check_data_freshness(source, max_award_date, days)
    for w in freshness_warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    return awards, freshness_warnings, source, extractor, table


def _company_key(award: dict) -> str:
    """Return a normalized company key for grouping.

    Uses _normalized_company if the cleaning pass has run, otherwise
    falls back to upper-cased raw name.
    """
    norm = award.get("_normalized_company", "")
    if norm:
        return norm
    return str(award.get("Company", "")).strip().upper()


def clean_and_dedup_awards(awards: list[dict]) -> tuple[list[dict], dict]:
    """Validate, normalize, and deduplicate weekly awards.

    Uses the existing sbir_etl validation pipeline when available:
    - validate_sbir_award_record() for per-row validation (phase, amount,
      required fields, format checks, date consistency, etc.)
    - normalize_name() for company name normalization

    Falls back to basic checks when sbir_etl is not installed.

    Returns:
        (cleaned_awards, stats) where stats is a dict with counts.
    """
    import pandas as pd

    stats: dict = {
        "input": len(awards),
        "validation_errors": 0,
    }

    cleaned: list[dict] = []

    if _validate_record is not None:
        for i, a in enumerate(awards):
            row = pd.Series(a)
            issues = _validate_record(row, i)
            errors = [
                iss
                for iss in issues
                if (iss.severity.value if hasattr(iss.severity, "value") else iss.severity)
                == "error"
            ]
            if errors:
                stats["validation_errors"] += 1
                continue
            a["_normalized_company"] = _normalize_name(
                str(a.get("Company", "")), remove_suffixes=True
            )
            # Collapse multiple spaces in name fields (common when middle name is empty)
            for name_field in ("PI Name", "Contact Name"):
                if name_field in a:
                    a[name_field] = " ".join(str(a[name_field]).split())
            cleaned.append(a)

    stats["output"] = len(cleaned)
    stats["total_removed"] = stats["input"] - stats["output"]

    if stats["total_removed"] > 0:
        print(
            f"Data cleaning: {stats['input']} -> {stats['output']} awards "
            f"({stats['validation_errors']} failed validation)",
            file=sys.stderr,
        )
    else:
        print(
            f"Data cleaning: {stats['input']} awards, all valid",
            file=sys.stderr,
        )

    return cleaned, stats


def _resolve_shared_extractor(
    source: DataSource | None = None,
) -> tuple[DataSource, SbirDuckDBExtractor, str]:
    """Resolve a CSV path and create a shared DuckDB extractor.

    Returns (source, extractor, table_name).
    """
    if source is None:
        source = _resolve_csv_path()

    extractor = SbirDuckDBExtractor(
        csv_path=source.path,
        duckdb_path=":memory:",
        use_s3_first=False,
    )
    extractor.import_csv()
    table = extractor._table_identifier

    return source, extractor, table


def get_company_history(
    awards: list[dict],
    source: DataSource | None = None,
    extractor: object | None = None,
    table: str | None = None,
) -> dict[str, dict]:
    """Extract historical SBIR award context per company from the full dataset."""
    if source is None:
        source, extractor, table = _resolve_shared_extractor()
    return _lib_get_company_history(awards, source=source, extractor=extractor, table=table)


def get_pi_history(
    awards: list[dict],
    source: DataSource | None = None,
    extractor: object | None = None,
    table: str | None = None,
) -> dict[str, dict]:
    """Extract historical SBIR context per Principal Investigator."""
    if source is None:
        source, extractor, table = _resolve_shared_extractor()
    return _lib_get_pi_history(awards, source=source, extractor=extractor, table=table)
