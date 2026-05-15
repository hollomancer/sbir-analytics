#!/usr/bin/env python3
"""Run the SBA Commercialization Rate Benchmark using public-data proxies.

SBA's official Company Commercialization Report is not publicly downloadable.
This script substitutes:
  - Sales        → USAspending prime contract obligations to the firm in the
                   commercialization window (FY<start>-FY<end>). Includes Phase
                   I/II SBIR awards (R&D inputs) by default; --net subtracts the
                   SBIR.gov Phase I/II totals to approximate commercialization.
  - Investment   → SEC Form D total offering amounts in window, matched on
                   company name (data/form_d_details.jsonl).
  - Patents      → SKIPPED. USPTO data on disk is fixture-only; ingestion has
                   not been run on this branch. Standard-tier firms with patent-
                   only paths get a "PATENTS_UNAVAILABLE" status.

SBA thresholds (per 15 USC §638(mm) and SBA Policy Directive):
  - Standard      (16 ≤ P2 < 51):   ≥$100K avg sales+investment per P2  OR ≥15% patents per P2
  - Increased T1  (51 ≤ P2 < 101):  ≥$250K avg sales+investment per P2  (no patent path)
  - Increased T2  (P2 ≥ 101):       ≥$450K avg sales+investment per P2  (no patent path)

Throttle: 1s base sleep between USAspending calls, exponential backoff on 429/5xx.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import duckdb
import httpx
import pandas as pd

API = "https://api.usaspending.gov/api/v2/search/spending_over_time/"
HEADERS = {"User-Agent": "sbir-analytics-research/0.1 (chollomon@gmail.com)"}

THRESHOLDS = {
    "standard": {"min_p2": 16, "max_p2": 50, "dollar": 100_000, "patent": 0.15},
    "tier1":    {"min_p2": 51, "max_p2": 100, "dollar": 250_000, "patent": None},
    "tier2":    {"min_p2": 101, "max_p2": float("inf"), "dollar": 450_000, "patent": None},
}


def assign_tier(p2: int) -> str | None:
    if p2 >= 101: return "tier2"
    if p2 >= 51:  return "tier1"
    if p2 >= 16:  return "standard"
    return None


def load_cohort(awards_csv: Path, start_fy: int, end_fy: int) -> pd.DataFrame:
    con = duckdb.connect()
    con.execute(f"CREATE TABLE s AS SELECT * FROM read_csv_auto('{awards_csv}', header=True, sample_size=-1)")
    return con.execute(f"""
        SELECT
          UEI AS uei,
          any_value(Company) AS firm,
          any_value(State) AS state,
          SUM(CASE WHEN Phase='Phase II' AND "Award Year" BETWEEN {start_fy} AND {end_fy} THEN 1 ELSE 0 END) AS p2_count,
          SUM(CASE WHEN Phase='Phase II' AND "Award Year" BETWEEN {start_fy} AND {end_fy} THEN "Award Amount" ELSE 0 END) AS p2_total_usd,
          SUM(CASE WHEN Phase='Phase I'  AND "Award Year" BETWEEN {start_fy} AND {end_fy} THEN "Award Amount" ELSE 0 END) AS p1_total_usd
        FROM s WHERE UEI IS NOT NULL AND TRIM(UEI)<>''
        GROUP BY UEI HAVING p2_count >= 16
        ORDER BY p2_count DESC
    """).fetchdf()


def fetch_usaspending_total(client: httpx.Client, uei: str, start_fy: int, end_fy: int) -> float:
    body = {
        "group": "fiscal_year",
        "filters": {
            "time_period": [{"start_date": f"{start_fy - 1}-10-01", "end_date": f"{end_fy}-09-30"}],
            "award_type_codes": ["A", "B", "C", "D"],
            "recipient_search_text": [uei],
        },
        "subawards": False,
    }
    for attempt in range(5):
        try:
            r = client.post(API, json=body)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            sleep = 2 ** attempt
            print(f"    {type(e).__name__} on {uei}, backoff {sleep}s", flush=True)
            time.sleep(sleep)
            continue
        if r.status_code == 200:
            return sum(row.get("aggregated_amount", 0) for row in r.json().get("results", []))
        if r.status_code in (429, 500, 502, 503, 504):
            sleep = 2 ** attempt
            print(f"    HTTP {r.status_code} on {uei}, backoff {sleep}s", flush=True)
            time.sleep(sleep)
            continue
        r.raise_for_status()
    print(f"    GAVE UP on {uei} — returning 0", flush=True)
    return 0.0


def load_form_d_investment(start_fy: int, end_fy: int) -> dict[str, float]:
    """Map UPPER(name) → total offering $ filed in window."""
    con = duckdb.connect()
    con.execute("CREATE TABLE fd AS SELECT * FROM read_json_auto('data/form_d_details.jsonl', format='newline_delimited', sample_size=-1)")
    rows = con.execute(f"""
        WITH off AS (
          SELECT UPPER(TRIM(company_name)) AS name_key, o.filing_date AS fd, o.total_offering_amount AS amt
          FROM fd, UNNEST(offerings) AS t(o)
        )
        SELECT name_key, SUM(amt) AS total
        FROM off
        WHERE fd IS NOT NULL
          AND EXTRACT(year FROM fd) BETWEEN {start_fy - 1} AND {end_fy}
        GROUP BY 1
    """).fetchall()
    return {r[0]: float(r[1] or 0) for r in rows}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--eval-fy", type=int, default=2026, help="Determination year (default 2026)")
    p.add_argument("--awards", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    p.add_argument("--net", action="store_true",
                   help="Subtract SBIR.gov P1+P2 totals from sales (proxy: commercialization-only)")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    # 10-FY window, exclude 2 most recent
    end_fy = (args.eval_fy - 1) - 2
    start_fy = end_fy - 10 + 1
    print(f"Commercialization window: FY{start_fy}-FY{end_fy} (eval_fy={args.eval_fy})")
    print(f"Sales proxy: USAspending prime contracts; investment proxy: Form D")
    if args.net:
        print("Net mode: subtracting SBIR.gov P1+P2 totals from federal sales total")

    cohort = load_cohort(args.awards, start_fy, end_fy)
    print(f"\nSubject cohort: {len(cohort)} firms")
    fd_map = load_form_d_investment(start_fy, end_fy)
    print(f"Form D firms with offerings in window: {len(fd_map):,}")

    rows = []
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=30.0), headers=HEADERS) as client:
        for i, r in cohort.iterrows():
            print(f"  [{i+1:3d}/{len(cohort)}] {r.firm[:40]:40s} P2={int(r.p2_count):3d} querying USAspending...",
                  end="", flush=True)
            sales = fetch_usaspending_total(client, r.uei, start_fy, end_fy)
            print(f"\r", end="", flush=True)
            net_sales = sales - (r.p1_total_usd + r.p2_total_usd) if args.net else sales
            invest = fd_map.get((r.firm or "").upper().strip(), 0.0)
            denom = max(int(r.p2_count), 1)
            avg = (max(net_sales, 0) + invest) / denom
            tier = assign_tier(int(r.p2_count))
            req = THRESHOLDS[tier]["dollar"]
            status = "PASS" if avg >= req else "FAIL"
            rows.append({
                "uei": r.uei, "firm": r.firm, "state": r.state,
                "tier": tier, "p2_count": int(r.p2_count),
                "sales_usaspending_usd": round(sales),
                "p1_p2_subtract_usd": round(r.p1_total_usd + r.p2_total_usd),
                "net_sales_usd": round(max(net_sales, 0)),
                "investment_form_d_usd": round(invest),
                "avg_per_p2_usd": round(avg),
                "required_per_p2_usd": req,
                "margin_per_p2_usd": round(avg - req),
                "status": status,
            })
            print(f"  [{i+1:3d}/{len(cohort)}] {r.firm[:40]:40s} P2={int(r.p2_count):3d} "
                  f"sales=${sales/1e6:>8,.1f}M  invest=${invest/1e6:>6,.1f}M  "
                  f"avg/P2=${avg/1e3:>8,.0f}K vs ${req/1e3:.0f}K  {status}",
                  flush=True)
            time.sleep(1.0)

    df = pd.DataFrame(rows)
    out = args.out or Path(f"reports/validation/commercialization_benchmark_eval_fy{args.eval_fy}{'_net' if args.net else ''}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nWrote {len(df)} rows -> {out}")

    by_status = df.groupby(["tier","status"]).size().unstack(fill_value=0)
    print("\n=== Status summary ===")
    print(by_status.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
