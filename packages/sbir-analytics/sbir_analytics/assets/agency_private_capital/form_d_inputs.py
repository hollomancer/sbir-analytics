"""Input adapters for agency-vs-Form-D matched cohort analysis.

The production Form D research artifacts are JSONL files, but their exact
shape has changed across analysis passes. These helpers normalize the two
shapes Phase 2 needs:

- SBIR-matched Form D details (`form_d_details.jsonl`)
- broader Form D issuer universe used for non-SBIR controls

Both outputs are ordinary DataFrames so matching and tests stay simple.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_etl.enrichers.sec_edgar.form_d_scoring import EXCLUDED_INDUSTRY_GROUPS


DEFAULT_FORM_D_MATCHES_PATH = Path("data/form_d_details.jsonl")
DEFAULT_FORM_D_CONTROL_UNIVERSE_PATH = Path("data/form_d_control_universe.jsonl")


def normalize_name(value: object) -> str:
    """Return the normalized join key used by the existing Form D analyses."""

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return " ".join(str(value).strip().upper().split())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read JSONL records, skipping blank and invalid lines."""

    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def load_form_d_matches(
    path: Path,
    *,
    tier_filter: set[str] | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
) -> pd.DataFrame:
    """Normalize SBIR-matched Form D records to one row per matched company."""

    rows = [
        row
        for row in _iter_company_form_d_rows(read_jsonl(path), matched_to_sbir=True)
        if _keep_row(row, tier_filter=tier_filter, year_min=year_min, year_max=year_max)
    ]
    return _frame(rows)


def load_form_d_control_universe(
    path: Path,
    *,
    sbir_ciks: set[str],
    year_min: int | None = None,
    year_max: int | None = None,
) -> pd.DataFrame:
    """Normalize non-SBIR Form D controls to one row per issuer CIK.

    The control universe is expected to be broader than SBIR matches. Any CIK
    already present in the SBIR matched set is removed before matching.
    """

    rows: list[dict[str, Any]] = []
    for row in _iter_company_form_d_rows(read_jsonl(path), matched_to_sbir=False):
        cik = str(row.get("form_d_cik") or "").lstrip("0")
        if not cik or cik in sbir_ciks:
            continue
        if not _keep_row(row, tier_filter=None, year_min=year_min, year_max=year_max):
            continue
        rows.append(row)
    return _frame(rows)


def _iter_company_form_d_rows(
    records: Iterable[dict[str, Any]],
    *,
    matched_to_sbir: bool,
) -> Iterable[dict[str, Any]]:
    for rec in records:
        company_name = rec.get("company_name") or rec.get("issuer_name") or rec.get("entity_name")
        cik = rec.get("form_d_cik") or rec.get("cik")
        tier = (rec.get("match_confidence") or {}).get("tier")
        offerings = rec.get("offerings")
        if not isinstance(offerings, list):
            offerings = [_offering_from_flat_record(rec)]

        kept_offerings = [
            offering
            for offering in offerings
            if offering and (offering.get("industry_group") or "") not in EXCLUDED_INDUSTRY_GROUPS
        ]
        if not kept_offerings:
            continue

        first = _first_offering(kept_offerings)
        filing_years = sorted(
            year
            for year in (_year(o.get("filing_date") or o.get("date_filed")) for o in kept_offerings)
            if year is not None
        )
        total_sold = _sum_float(o.get("total_amount_sold") for o in kept_offerings)
        total_offered = _sum_float(o.get("total_offering_amount") for o in kept_offerings)

        issuer_name = (
            first.get("entity_name")
            or first.get("issuer_name")
            or rec.get("issuer_name")
            or rec.get("entity_name")
            or company_name
        )
        state = first.get("state") or rec.get("state")
        industry_group = first.get("industry_group") or rec.get("industry_group")
        security_types = sorted(
            {
                str(t).lower()
                for offering in kept_offerings
                for t in (offering.get("securities_types") or [])
                if t
            }
        )

        yield {
            "company_name": company_name,
            "company_key": normalize_name(company_name),
            "issuer_name": issuer_name,
            "issuer_key": normalize_name(issuer_name),
            "form_d_cik": str(cik or first.get("cik") or "").lstrip("0"),
            "tier": tier,
            "matched_to_sbir": matched_to_sbir,
            "state": _state_code(state),
            "industry_group": industry_group or "Unknown",
            "first_form_d_date": first.get("filing_date") or first.get("date_filed") or "",
            "first_form_d_year": filing_years[0] if filing_years else None,
            "offering_count": len(kept_offerings),
            "total_form_d_raised": total_sold,
            "total_form_d_offered": total_offered,
            "security_types": security_types,
        }


def _offering_from_flat_record(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "cik": rec.get("cik") or rec.get("form_d_cik"),
        "entity_name": rec.get("entity_name") or rec.get("issuer_name") or rec.get("company_name"),
        "filing_date": rec.get("filing_date") or rec.get("date_filed"),
        "state": rec.get("state"),
        "industry_group": rec.get("industry_group"),
        "securities_types": rec.get("securities_types") or [],
        "total_amount_sold": rec.get("total_amount_sold") or rec.get("total_raised"),
        "total_offering_amount": rec.get("total_offering_amount"),
    }


def _first_offering(offerings: list[dict[str, Any]]) -> dict[str, Any]:
    def key(offering: dict[str, Any]) -> str:
        return str(offering.get("filing_date") or offering.get("date_filed") or "9999-99-99")

    return sorted(offerings, key=key)[0]


def _year(value: object) -> int | None:
    if value is None:
        return None
    s = str(value)
    return int(s[:4]) if len(s) >= 4 and s[:4].isdigit() else None


def _sum_float(values: Iterable[object]) -> float:
    total = 0.0
    for value in values:
        parsed = _float_or_none(value)
        if parsed is None:
            continue
        total += parsed
    return total


def _float_or_none(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def _state_code(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip().upper()[:2]


def _keep_row(
    row: dict[str, Any],
    *,
    tier_filter: set[str] | None,
    year_min: int | None,
    year_max: int | None,
) -> bool:
    if tier_filter is not None and row.get("tier") not in tier_filter:
        return False
    year = row.get("first_form_d_year")
    if year is not None and year_min is not None and int(year) < year_min:
        return False
    if year is not None and year_max is not None and int(year) > year_max:
        return False
    return bool(row.get("form_d_cik") and row.get("company_key"))


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    columns = [
        "company_name",
        "company_key",
        "issuer_name",
        "issuer_key",
        "form_d_cik",
        "tier",
        "matched_to_sbir",
        "state",
        "industry_group",
        "first_form_d_date",
        "first_form_d_year",
        "offering_count",
        "total_form_d_raised",
        "total_form_d_offered",
        "security_types",
    ]
    return pd.DataFrame(rows, columns=columns)
