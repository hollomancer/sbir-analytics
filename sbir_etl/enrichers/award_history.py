"""Historical award context building for SBIR companies and PIs.

Extracts and aggregates historical SBIR/STTR award data from the full
awards dataset, providing per-company and per-PI context useful for
diligence and trend analysis.
"""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

from loguru import logger

from sbir_etl.utils.date_utils import parse_date
from sbir_etl.utils.text_normalization import pluralize_col_key

if TYPE_CHECKING:
    from sbir_etl.utils.cloud_storage import SbirAwardsSource


def _parse_date_safe(value) -> str | None:
    """Parse a date value and return ISO format string, or None."""
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else None


def _build_history_from_df(
    df,
    group_col: str,
    extra_set_cols: list[str] | None = None,
) -> dict[str, dict]:
    """Build history dicts from a DataFrame grouped by a column.

    Used by both company and PI history to avoid duplicating aggregation logic.
    """
    df = df.fillna("")
    history: dict[str, dict] = {}

    for group_key, group_df in df.groupby(group_col, sort=False):
        name = str(group_key).strip()
        if not name:
            continue

        phases = {v for v in group_df["Phase"].astype(str).str.strip() if v}
        agencies = {v for v in group_df["Agency"].astype(str).str.strip() if v}
        programs = {v for v in group_df["Program"].astype(str).str.strip() if v}

        total_funding = 0.0
        for val in group_df["Award Amount"].astype(str):
            try:
                total_funding += float(val.replace(",", "").replace("$", ""))
            except (ValueError, TypeError):
                pass

        parsed_dates = []
        for val in group_df["Proposal Award Date"].astype(str).str.strip():
            if val:
                iso = _parse_date_safe(val)
                if iso:
                    parsed_dates.append(iso)

        titles: list[str] = []
        for t in group_df["Award Title"].astype(str).str.strip():
            if t and t not in titles:
                titles.append(t)

        entry: dict = {
            "total_awards": len(group_df),
            "phases": sorted(phases),
            "agencies": sorted(agencies),
            "programs": sorted(programs),
            "total_funding": total_funding,
            "earliest_date": min(parsed_dates) if parsed_dates else None,
            "latest_date": max(parsed_dates) if parsed_dates else None,
            "sample_titles": titles[:5],
        }

        # Extra set columns (e.g. "Company" for PI history)
        if extra_set_cols:
            for col in extra_set_cols:
                col_key = pluralize_col_key(col)
                entry[col_key] = sorted(
                    {v for v in group_df[col].astype(str).str.strip() if v}
                )

        history[name] = entry

    return history


def _build_history_from_csv(
    source: SbirAwardsSource,
    target_names: set[str],
    key_field: str,
    extra_set_fields: list[str] | None = None,
) -> dict[str, dict]:
    """Build history dicts by streaming the CSV file.

    Streams the file line-by-line to avoid loading the entire CSV into memory.
    """
    history: dict[str, dict] = {}
    with source.path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = str(row.get(key_field, "")).strip().upper()
            if name not in target_names:
                continue
            if name not in history:
                entry: dict = {
                    "total_awards": 0,
                    "phases": set(),
                    "agencies": set(),
                    "programs": set(),
                    "total_funding": 0.0,
                    "dates": [],
                    "sample_titles": [],
                }
                if extra_set_fields:
                    for ef in extra_set_fields:
                        entry[pluralize_col_key(ef)] = set()
                history[name] = entry

            h = history[name]
            h["total_awards"] += 1
            for field, set_key in [("Phase", "phases"), ("Agency", "agencies"), ("Program", "programs")]:
                val = str(row.get(field, "")).strip()
                if val:
                    h[set_key].add(val)
            if extra_set_fields:
                for ef in extra_set_fields:
                    val = str(row.get(ef, "")).strip()
                    if val:
                        h[pluralize_col_key(ef)].add(val)
            try:
                h["total_funding"] += float(
                    str(row.get("Award Amount", "0")).replace(",", "").replace("$", "")
                )
            except (ValueError, TypeError):
                pass
            d = str(row.get("Proposal Award Date", "")).strip()
            if d:
                h["dates"].append(d)
            t = str(row.get("Award Title", "")).strip()
            if t and len(h["sample_titles"]) < 5 and t not in h["sample_titles"]:
                h["sample_titles"].append(t)

    # Normalize sets to sorted lists and parse dates
    for _name, h in history.items():
        raw_dates = h.pop("dates", [])
        parsed_dates = [_parse_date_safe(d) for d in raw_dates]
        parsed_dates = [d for d in parsed_dates if d]
        h["earliest_date"] = min(parsed_dates) if parsed_dates else None
        h["latest_date"] = max(parsed_dates) if parsed_dates else None
        for key in ["phases", "agencies", "programs"]:
            if isinstance(h[key], set):
                h[key] = sorted(h[key])
        if extra_set_fields:
            for ef in extra_set_fields:
                set_key = ef.lower().replace(" ", "_") + "s"
                if isinstance(h.get(set_key), set):
                    h[set_key] = sorted(h[set_key])

    return history


def get_company_history(
    awards: list[dict],
    source: SbirAwardsSource | None = None,
    extractor: object | None = None,
    table: str | None = None,
) -> dict[str, dict]:
    """Extract historical SBIR award context per company from the full dataset.

    Accepts optional shared source/extractor/table to avoid redundant CSV
    downloads and DuckDB imports when called alongside get_pi_history().

    Returns a dict keyed by upper-cased company name.
    """
    company_names = {str(a.get("Company", "")).strip().upper() for a in awards}
    company_names.discard("")
    if not company_names:
        return {}

    if extractor is not None and table is not None:
        # Build IN clause with escaped names
        escaped = [f"'{n.replace(chr(39), chr(39)+chr(39))}'" for n in sorted(company_names)]
        in_clause = ", ".join(escaped)
        query = (
            f'SELECT UPPER("Company") AS _group_key, "Phase", "Agency", '
            f'"Award Amount", "Proposal Award Date", "Award Title", "Program" '
            f"FROM {table} "
            f'WHERE UPPER("Company") IN ({in_clause}) '
            f'ORDER BY "Proposal Award Date" DESC'
        )
        df = extractor.duckdb_client.execute_query_df(query)
        if df.empty:
            return {}
        return _build_history_from_df(df, "_group_key")

    if source is None:
        logger.debug("get_company_history: no source or extractor provided")
        return {}

    # Fallback: stream the CSV
    return _build_history_from_csv(source, company_names, "Company")


def get_pi_history(
    awards: list[dict],
    source: SbirAwardsSource | None = None,
    extractor: object | None = None,
    table: str | None = None,
) -> dict[str, dict]:
    """Extract historical SBIR context per Principal Investigator.

    Accepts optional shared source/extractor/table to avoid redundant CSV
    downloads and DuckDB imports.

    Returns a dict keyed by upper-cased PI name.
    """
    pi_names = set()
    for a in awards:
        pi = str(a.get("PI Name", "")).strip().upper()
        if pi:
            pi_names.add(pi)

    if not pi_names:
        return {}

    if extractor is not None and table is not None:
        escaped = [f"'{n.replace(chr(39), chr(39)+chr(39))}'" for n in sorted(pi_names)]
        in_clause = ", ".join(escaped)
        query = (
            f'SELECT UPPER("PI Name") AS _group_key, "Company", "Phase", "Agency", '
            f'"Award Amount", "Proposal Award Date", "Award Title", "Program" '
            f"FROM {table} "
            f'WHERE UPPER("PI Name") IN ({in_clause}) '
            f'ORDER BY "Proposal Award Date" DESC'
        )
        df = extractor.duckdb_client.execute_query_df(query)
        if df.empty:
            return {}
        return _build_history_from_df(df, "_group_key", extra_set_cols=["Company"])

    if source is None:
        logger.debug("get_pi_history: no source or extractor provided")
        return {}

    # Fallback: stream the CSV
    return _build_history_from_csv(source, pi_names, "PI Name", extra_set_fields=["Company"])
