"""Fetch SBA FAST cooperative agreements (assistance listing 59.058) from USAspending.

Builds the state x fiscal-year treatment panel used by the FAST border study.
Exploratory tier: no citable claim depends on this module.

USAspending rejects start dates before 2007-10-01 and holds no FAST records
before FY2010, so FY2001-FY2009 is out of reach here and must come from SBA
press releases or FOIA.

Usage:
    python scripts/usaspending/fetch_fast_awards.py --out data/reference/fast/fast_awards_fy2010_2024.csv
"""

from __future__ import annotations

import argparse
import json
import ssl
import urllib.request
from pathlib import Path

import pandas as pd

API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
ALN = "59.058"
ASSISTANCE_TYPE_CODES = ["02", "03", "04", "05"]
FIELDS = [
    "Award ID",
    "Recipient Name",
    "Start Date",
    "End Date",
    "Award Amount",
    "Place of Performance State Code",
]


def _opener(cafile: str | None) -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def fetch_awards(start: str = "2007-10-01", end: str = "2026-09-30",
                 cafile: str | None = None, max_pages: int = 60) -> pd.DataFrame:
    """Return one row per FAST assistance award."""
    opener = _opener(cafile)
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        payload = {
            "filters": {
                "award_type_codes": ASSISTANCE_TYPE_CODES,
                "program_numbers": [ALN],
                "time_period": [{"start_date": start, "end_date": end}],
            },
            "fields": FIELDS,
            "limit": 100,
            "page": page,
        }
        req = urllib.request.Request(
            API, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
        )
        with opener.open(req, timeout=120) as resp:
            body = json.loads(resp.read())
        rows.extend(body.get("results", []))
        if not body.get("page_metadata", {}).get("hasNext"):
            break
    return pd.DataFrame(rows)


def to_state_year_panel(awards: pd.DataFrame) -> pd.DataFrame:
    """Collapse awards to state x fiscal year.

    Fiscal year is derived from the award start date: October onward counts as
    the next fiscal year. `Place of Performance State Code` is used because
    `Recipient Location State Code` is null on these records.
    """
    df = awards.copy()
    start = pd.to_datetime(df["Start Date"])
    df["fiscal_year"] = start.dt.year + (start.dt.month >= 10).astype(int)
    df = df.rename(columns={"Place of Performance State Code": "state"})
    df = df[df["state"].notna()]
    panel = (
        df.groupby(["state", "fiscal_year"])
        .agg(n_awards=("Award ID", "size"), obligated_usd=("Award Amount", "sum"))
        .reset_index()
        .sort_values(["state", "fiscal_year"])
    )
    return panel


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cafile", default=None, help="CA bundle, if the sandbox proxy needs one")
    args = ap.parse_args()
    panel = to_state_year_panel(fetch_awards(cafile=args.cafile))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(args.out, index=False)
    print(f"wrote {args.out} ({len(panel)} state-years, {panel.state.nunique()} states)")


if __name__ == "__main__":
    main()
