"""Annual refresh for ``data/reference/tax/state_effective_rates.csv``.

Requirement 3 of ``specs/state-local-tax-rates/``: download Tax Foundation
income and sales tax tables (or accept a curated JSON bundle), merge a new
``fiscal_year`` into the reference CSV, and preserve property rates from the
prior year (Census ASGF is not published on Tax Foundation pages).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from .state_rates import DEFAULT_CSV_PATH

CSV_COLUMNS = [
    "state_fips",
    "state_abbr",
    "fiscal_year",
    "income_rate",
    "sales_rate",
    "property_rate",
    "has_income_tax",
    "has_sales_tax",
    "income_source",
    "sales_source",
    "property_source",
]

# Full state names as they appear on Tax Foundation pages (before parenthetical notes).
_STATE_NAME_TO_ABBR: dict[str, str] = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "washington dc": "DC",
    "d.c.": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}

_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_INCOME_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*([^|]+)\|")


def _normalize_state_name(raw: str) -> str:
    name = raw.strip().lower()
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    if name.startswith("- "):
        name = name[2:].strip()
    return name


def state_abbr_from_name(raw: str) -> str | None:
    """Map a Tax Foundation state label to a two-letter abbreviation."""
    key = _normalize_state_name(raw)
    return _STATE_NAME_TO_ABBR.get(key)


def _parse_percentages(cell: str) -> list[float]:
    if not cell or cell.strip().lower() in {"none", "n.a.", "n/a"}:
        return []
    return [float(match) / 100.0 for match in _PERCENT_RE.findall(cell)]


def parse_income_tax_table(text: str) -> dict[str, float]:
    """Extract top marginal single-filer income tax rate per state from TF markdown."""
    rates: dict[str, float] = {}
    current_abbr: str | None = None

    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        if "Single Filer (Rates)" in line or line.startswith("| ---"):
            continue

        match = _INCOME_ROW_RE.match(line)
        if not match:
            continue

        label, rate_cell = match.group(1).strip(), match.group(2)
        if label.startswith("- "):
            if current_abbr is None:
                continue
            abbr = current_abbr
        else:
            parsed_abbr = state_abbr_from_name(label)
            if parsed_abbr is None:
                current_abbr = None
                continue
            abbr = parsed_abbr
            current_abbr = abbr

        parsed = _parse_percentages(rate_cell)
        if not parsed:
            if rate_cell.strip().lower() in {"none", "n.a.", "n/a"}:
                rates[abbr] = 0.0
            continue
        rates[abbr] = max(parsed)

    return rates


def parse_sales_tax_table(text: str) -> dict[str, float]:
    """Extract combined state+local sales tax rate per state from TF markdown."""
    rates: dict[str, float] = {}
    in_table = False

    for line in text.splitlines():
        if "Combined Tax Rate" in line and line.startswith("|"):
            in_table = True
            continue
        if not in_table or not line.startswith("|"):
            continue
        if line.startswith("| ---"):
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 6:
            continue

        state_label, combined_cell = cells[0], cells[4]
        abbr = state_abbr_from_name(state_label)
        if abbr is None:
            continue

        parsed = _parse_percentages(combined_cell)
        if not parsed:
            if combined_cell.strip().lower() in {"0.00%", "0.00 %"} or combined_cell == "0.00%":
                rates[abbr] = 0.0
            continue
        rates[abbr] = parsed[0]

    return rates


def income_tax_page_url(fiscal_year: int) -> str:
    if fiscal_year >= 2026:
        return f"https://taxfoundation.org/data/all/state/state-income-tax-rates-{fiscal_year}/"
    if fiscal_year == 2025:
        return "https://taxfoundation.org/data/all/state/state-income-tax-rates/"
    return f"https://taxfoundation.org/data/all/state/state-income-tax-rates-{fiscal_year}/"


def sales_tax_page_url(fiscal_year: int) -> str:
    if fiscal_year >= 2026:
        return f"https://taxfoundation.org/data/all/state/{fiscal_year}-sales-tax-rates-midyear/"
    if fiscal_year == 2025:
        return "https://taxfoundation.org/data/all/state/sales-tax-rates-midyear-2025/"
    return f"https://taxfoundation.org/data/all/state/{fiscal_year}-sales-tax-rates-midyear/"


def fetch_tax_foundation_rates(
    fiscal_year: int,
    *,
    timeout: float = 30.0,
) -> tuple[dict[str, float], dict[str, float], str]:
    """Download and parse Tax Foundation income + sales tables for a fiscal year."""
    headers = {"User-Agent": "sbir-etl/refresh-state-rates (fiscal data refresh)"}
    income_url = income_tax_page_url(fiscal_year)
    sales_url = sales_tax_page_url(fiscal_year)

    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        income_resp = client.get(income_url)
        income_resp.raise_for_status()
        sales_resp = client.get(sales_url)
        sales_resp.raise_for_status()

    income_rates = parse_income_tax_table(income_resp.text)
    sales_rates = parse_sales_tax_table(sales_resp.text)

    if len(income_rates) < 40 or len(sales_rates) < 40:
        raise ValueError(
            f"Parsed too few states (income={len(income_rates)}, sales={len(sales_rates)}); "
            "Tax Foundation page layout may have changed."
        )

    edition = (
        f"Tax Foundation {fiscal_year} — State Individual Income Tax Rates and Brackets; "
        f"Tax Foundation {fiscal_year} — State and Local Sales Tax Rates"
    )
    return income_rates, sales_rates, edition


def load_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _prior_row_for_state(rows: list[dict[str, str]], state_abbr: str) -> dict[str, str] | None:
    matches = [row for row in rows if row["state_abbr"].upper() == state_abbr.upper()]
    if not matches:
        return None
    return max(matches, key=lambda row: int(row["fiscal_year"]))


def _income_source_note(abbr: str, rate: float, fiscal_year: int) -> str:
    if rate == 0.0 and abbr in {"AK", "FL", "NV", "SD", "TN", "TX", "WA", "WY"}:
        return f"Tax Foundation {fiscal_year} — State Individual Income Tax Rates and Brackets (no state income tax)"
    if abbr == "NH" and rate == 0.0:
        return (
            f"Tax Foundation {fiscal_year} — State Individual Income Tax Rates and Brackets "
            "(no broad-based state income tax on earned income; taxes interest/dividends only)"
        )
    if abbr == "WA" and rate == 0.0:
        return (
            f"Tax Foundation {fiscal_year} — State Individual Income Tax Rates and Brackets "
            "(no state income tax on wages; capital gains tax enacted 2022 not modeled here)"
        )
    return f"Tax Foundation {fiscal_year} — State Individual Income Tax Rates and Brackets"


def _sales_source_note(abbr: str, rate: float, fiscal_year: int) -> str:
    if rate == 0.0 and abbr in {"DE", "MT", "NH", "OR"}:
        return (
            f"Tax Foundation {fiscal_year} — State and Local Sales Tax Rates (no state sales tax)"
        )
    return f"Tax Foundation {fiscal_year} — State and Local Sales Tax Rates"


def merge_fiscal_year(
    existing_rows: list[dict[str, str]],
    *,
    fiscal_year: int,
    income_by_state: dict[str, float],
    sales_by_state: dict[str, float],
    edition: str,
) -> tuple[list[dict[str, str]], int]:
    """Return updated rows with ``fiscal_year`` replaced/inserted for each state."""
    retained = [row for row in existing_rows if int(row["fiscal_year"]) != fiscal_year]
    updated = 0
    new_rows: list[dict[str, str]] = []

    all_states = sorted(set(income_by_state) | set(sales_by_state))
    for abbr in all_states:
        if abbr not in income_by_state or abbr not in sales_by_state:
            logger.warning("Skipping {} — missing income or sales rate", abbr)
            continue

        prior = _prior_row_for_state(existing_rows, abbr)
        if prior is None:
            logger.warning("Skipping {} — no prior CSV row to copy FIPS/property from", abbr)
            continue

        income_rate = income_by_state[abbr]
        sales_rate = sales_by_state[abbr]
        new_rows.append(
            {
                "state_fips": prior["state_fips"],
                "state_abbr": abbr,
                "fiscal_year": str(fiscal_year),
                "income_rate": f"{income_rate:.3f}".rstrip("0").rstrip("."),
                "sales_rate": f"{sales_rate:.3f}".rstrip("0").rstrip("."),
                "property_rate": prior["property_rate"],
                "has_income_tax": "True" if income_rate > 0 else "False",
                "has_sales_tax": "True" if sales_rate > 0 else "False",
                "income_source": _income_source_note(abbr, income_rate, fiscal_year),
                "sales_source": _sales_source_note(abbr, sales_rate, fiscal_year),
                "property_source": prior["property_source"],
            }
        )
        updated += 1

    merged = retained + new_rows
    merged.sort(key=lambda row: (row["state_abbr"], int(row["fiscal_year"])))
    return merged, updated


def write_csv_rows(csv_path: Path, rows: list[dict[str, str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def load_rates_bundle(path: Path) -> tuple[dict[str, float], dict[str, float], str]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    edition = str(payload.get("edition", f"manual bundle ({path.name})"))
    income = {k.upper(): float(v) for k, v in payload["income"].items()}
    sales = {k.upper(): float(v) for k, v in payload["sales"].items()}
    return income, sales, edition


def refresh_state_rates(
    *,
    fiscal_year: int,
    csv_path: Path,
    income_by_state: dict[str, float],
    sales_by_state: dict[str, float],
    edition: str,
    dry_run: bool = False,
) -> int:
    existing = load_csv_rows(csv_path)
    merged, count = merge_fiscal_year(
        existing,
        fiscal_year=fiscal_year,
        income_by_state=income_by_state,
        sales_by_state=sales_by_state,
        edition=edition,
    )
    logger.info(
        "Tax Foundation edition: {} — updating {} states for fiscal_year={}",
        edition,
        count,
        fiscal_year,
    )
    if dry_run:
        logger.info("Dry run — CSV not written")
        return count
    write_csv_rows(csv_path, merged)
    logger.info("Wrote {}", csv_path)
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh state effective tax rates in the reference CSV.",
    )
    parser.add_argument(
        "--fiscal-year",
        type=int,
        required=True,
        help="Fiscal year to write (overwrites existing rows for that year).",
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help=f"Target CSV (default: {DEFAULT_CSV_PATH}).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--fetch",
        action="store_true",
        help="Download income and sales tables from taxfoundation.org.",
    )
    source.add_argument(
        "--rates-json",
        type=Path,
        help="JSON bundle with {edition, income: {ST: rate}, sales: {ST: rate}}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and log without writing the CSV.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.fetch:
            income, sales, edition = fetch_tax_foundation_rates(args.fiscal_year)
        else:
            income, sales, edition = load_rates_bundle(args.rates_json)
    except Exception as exc:
        logger.warning("Refresh failed: {}", exc)
        return 1

    try:
        count = refresh_state_rates(
            fiscal_year=args.fiscal_year,
            csv_path=args.csv_path,
            income_by_state=income,
            sales_by_state=sales,
            edition=edition,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        logger.error("Could not update CSV: {}", exc)
        return 1

    if count == 0:
        logger.warning("No states updated")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
