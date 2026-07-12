#!/usr/bin/env python3
"""Spot-check a single firm's commercialization benchmark verdict from scratch.

Given a UEI and eval FY, this script re-derives every input the main
benchmark uses for that firm — USAspending obligations (contracts total +
contracts under R&D NAICS + grants), SBIR.gov P1+P2 totals, Form D
offerings in window — and prints a human-readable comparison alongside
the row from the main output CSV.

The purpose is to let an auditor independently verify a single firm's
verdict in ~2 minutes without rerunning the full 143-firm pipeline.

Usage:
    .venv/bin/python scripts/data/audit_one_firm.py <UEI> [--eval-fy 2026]

Example:
    .venv/bin/python scripts/data/audit_one_firm.py RMG1AZ1ZH8Q7 --eval-fy 2026
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import duckdb
import httpx
import pandas as pd

# Reuse the constants and functions from the main script. Add the script
# directory to sys.path so the import works regardless of CWD.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import run_commercialization_benchmark as bench  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("uei", help="Firm UEI to audit")
    p.add_argument("--eval-fy", type=int, default=2026)
    p.add_argument("--awards", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    p.add_argument("--csv", type=Path, default=None,
                   help="Path to main benchmark CSV (default auto-detected)")
    args = p.parse_args()

    eval_fy = args.eval_fy
    csv_path = args.csv or Path(f"reports/validation/commercialization_benchmark_eval_fy{eval_fy}.csv")

    # 1. Cohort row (P2 count, own SBIR totals)
    cohort = bench.load_cohort(args.awards, eval_fy)
    cohort_row = cohort[cohort["uei"] == args.uei]
    if cohort_row.empty:
        print(f"ERROR: UEI {args.uei} not in cohort (<16 P2 in 10-FY).")
        return 1
    r = cohort_row.iloc[0]
    win = bench.assign_firm_window(int(r.p2_count_10fy), eval_fy)
    if win is None:
        print("ERROR: firm doesn't meet any tier minimum.")
        return 1

    print(f"\n{'=' * 70}")
    print(f"Audit: {r.firm}  (UEI {args.uei}, {r.state})")
    print(f"{'=' * 70}")
    print(f"Eval FY:                {eval_fy}")
    print(f"Sales window:           FY{win.sales_start_fy}-FY{win.sales_end_fy}")
    print(f"Tier:                   {win.tier}  (threshold ${win.threshold_usd:,.0f}/P2)")
    print(f"P2 count in window:     {win.p2_count}")
    print(f"Own SBIR P1+P2 total:   ${float(r.p1_total_10fy_usd + r.p2_total_10fy_usd):,.2f}")
    print(f"Federal excluded?       {win.exclude_federal}  ({'covered-sale rule' if win.exclude_federal else 'all federal counts'})")

    # 2. Live USAspending pulls
    print("\n--- Live USAspending API calls (3 calls, ~3s) ---")
    with httpx.Client(timeout=httpx.Timeout(120.0), headers=bench.HEADERS) as client:
        contracts = bench.fetch_usaspending_total(
            client, args.uei, win.sales_start_fy, win.sales_end_fy, bench.CONTRACT_TYPES
        )
        time.sleep(1.0)
        contracts_rd = bench.fetch_usaspending_total(
            client, args.uei, win.sales_start_fy, win.sales_end_fy, bench.CONTRACT_TYPES,
            naics_codes=bench.RD_NAICS,
        )
        time.sleep(1.0)
        grants = bench.fetch_usaspending_total(
            client, args.uei, win.sales_start_fy, win.sales_end_fy, bench.GRANT_TYPES
        )
    if contracts is None or contracts_rd is None or grants is None:
        print(f"  API ERROR — contracts={contracts}, contracts_rd={contracts_rd}, grants={grants}")
        return 2
    contracts_non_rd = max(contracts - contracts_rd, 0.0)
    federal_observed = contracts + grants
    print(f"  contracts (FPDS A/B/C/D):    ${contracts:>16,.2f}")
    print(f"  contracts under R&D NAICS:   ${contracts_rd:>16,.2f}  ({100*contracts_rd/max(contracts,1):.1f}% of contracts)")
    print(f"  contracts non-R&D NAICS:     ${contracts_non_rd:>16,.2f}")
    print(f"  grants (FABS 02/03/04/05):   ${grants:>16,.2f}")
    print(f"  federal_observed total:      ${federal_observed:>16,.2f}")

    # 3. Form D matches (state-filtered + high-conf)
    print("\n--- Form D match decisions ---")
    firm_state = bench.STATE_NAME_TO_ABBR.get(r.state or "", "")
    name_key = (r.firm or "").upper().strip()
    con = duckdb.connect()
    con.execute("CREATE TABLE fd AS SELECT * FROM read_json_auto('data/form_d_details.jsonl', format='newline_delimited', sample_size=-1)")
    fd_rows = con.execute(f"""
        WITH off AS (
          SELECT UPPER(TRIM(company_name)) AS name_key,
                 match_confidence.tier AS conf_tier,
                 o.filing_date AS fd, o.entity_name AS entity_name,
                 o.state AS fd_state, o.total_offering_amount AS amt
          FROM fd, UNNEST(offerings) AS t(o)
        )
        SELECT entity_name, fd, fd_state, conf_tier, amt
        FROM off
        WHERE name_key = '{name_key.replace("'", "''")}'
          AND fd IS NOT NULL
          AND EXTRACT(year FROM fd) BETWEEN {win.sales_start_fy - 1} AND {win.sales_end_fy}
        ORDER BY fd
    """).fetchall()
    invest_total = 0.0
    if not fd_rows:
        print(f"  No Form D matches for UPPER(name)='{name_key}'")
    else:
        for entity, fd_date, fd_st, conf, amt in fd_rows:
            included = (conf == "high") or (fd_st == firm_state)
            mark = "✓ KEPT" if included else "✗ FILTERED"
            reason = "high_conf" if conf == "high" and fd_st != firm_state else (
                "state_match" if fd_st == firm_state else "state_mismatch_low_conf"
            )
            print(f"  [{mark}] {fd_date}  {entity[:40]:40s}  {fd_st or '??'}  conf={conf or '?':6s}  ${(amt or 0)/1e6:>7.2f}M  ({reason})")
            if included:
                invest_total += float(amt or 0)
    print(f"  Total Form D investment counted: ${invest_total:,.2f}")

    # 4. Re-derive verdicts
    print("\n--- Verdicts derived locally (compare to CSV) ---")
    own_sbir = float(r.p1_total_10fy_usd + r.p2_total_10fy_usd)
    denom = max(win.p2_count, 1)

    # §638(mm) Standard tier — applies to every firm
    std_net_sales = max(federal_observed - own_sbir, 0.0)
    std_strict_sales = contracts_non_rd
    std_net_avg = (std_net_sales + invest_total) / denom
    std_strict_avg = (std_strict_sales + invest_total) / denom
    print("  §638(mm) Standard ($100K/P2):")
    for label, sales, avg in [("net   ", std_net_sales, std_net_avg), ("strict", std_strict_sales, std_strict_avg)]:
        status = "PASS" if avg >= 100_000 else "FAIL"
        print(f"    {label}  sales=${sales:>14,.0f}  avg/P2=${avg:>11,.0f}  → {status}")

    # §638(qq) Increased tier — applies only when P2 ≥ 51
    if win.tier in ("tier1", "tier2"):
        inc_avg = invest_total / denom  # federal $ excluded under covered-sale rule
        inc_status = "PASS" if inc_avg >= win.threshold_usd else "FAIL"
        print(f"  §638(qq) {win.tier} (${win.threshold_usd/1e3:.0f}K/P2, federal excluded):")
        print(f"    net    sales=$             0  avg/P2=${inc_avg:>11,.0f}  → {inc_status}")
        print(f"    strict sales=$             0  avg/P2=${inc_avg:>11,.0f}  → {inc_status}")
    else:
        print(f"  §638(qq) Increased: N/A (firm has {win.p2_count} P2 < 51, not subject)")

    # 5. Cross-check against CSV row
    print(f"\n--- Cross-check vs {csv_path} ---")
    if not csv_path.exists():
        print("  CSV not found.")
        return 0
    df = pd.read_csv(csv_path)
    csv_row = df[df["uei"] == args.uei]
    if csv_row.empty:
        print("  UEI not in CSV.")
        return 0
    cr = csv_row.iloc[0]
    print(f"  CSV federal_observed:  ${cr['federal_observed_usd']:>14,.0f}  (live: ${federal_observed:,.0f}  Δ${federal_observed - cr['federal_observed_usd']:+,.0f})")
    print(f"  CSV contracts_rd:      ${cr['contracts_rd_usd']:>14,.0f}  (live: ${contracts_rd:,.0f}  Δ${contracts_rd - cr['contracts_rd_usd']:+,.0f})")
    print(f"  CSV investment_form_d: ${cr['investment_form_d_usd']:>14,.0f}  (live: ${invest_total:,.0f})")
    for label in ["standard_net", "standard_strict"]:
        print(f"  CSV {label:16s} status: {cr[f'{label}_status']}  avg/P2=${cr[f'{label}_avg_per_p2_usd']:>11,.0f}")
    if pd.notna(cr.get("increased_net_status")):
        for label in ["increased_net", "increased_strict"]:
            print(f"  CSV {label:16s} status: {cr[f'{label}_status']}  avg/P2=${cr[f'{label}_avg_per_p2_usd']:>11,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
