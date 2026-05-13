#!/usr/bin/env python3
"""Build a per-firm Phase III prospect digest for contracting officers.

Inputs (assumed present in data/):
  - data/raw/sbir/award_data.csv                                       (SBIR.gov bulk)
  - data/processed/sbir_phase3/fy<YY>_sbir_contract_lookups.jsonl      (FPDS NAICS/PSC join)
  - data/processed/sbir_phase3/fy<YY>_sbir_grant_lookups.jsonl         (FABS CFDA join)
  - data/processed/sbir_phase3/fy<YY>_sbir_phase3_contracts.jsonl      (Phase III precedent)

Output:
  - data/processed/sbir_phase3/fy<YY>_phase3_prospect_digest.csv

One row per UEI for the given Award Year. NAICS/PSC are aggregated across
the firm's FY contracts. Industry areas are derived from NAICS 4-digit
prefix and PSC 2-char prefix — the federal procurement category dimension.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


# PSC 2-char prefix → industry area
PSC_AREA = {
    "AC": "R&D — Defense",
    "AN": "R&D — Health",
    "AJ": "R&D — General Science/Tech",
    "AF": "R&D — Education/Social",
    "AS": "R&D — Transportation",
    "AT": "R&D — Energy",
    "AB": "R&D — Agriculture",
    "AK": "R&D — Housing/Community",
    "AL": "R&D — Income Security",
    "AM": "R&D — Veterans/Other",
    "AP": "R&D — Natural Resources",
    "AQ": "R&D — Atomic Energy",
    "AR": "R&D — Space/Astronautics",
    "AZ": "R&D — Other",
    "DA": "IT — Application Development",
    "DB": "IT — Outsourcing",
    "DC": "IT — Cybersecurity",
    "DD": "IT — Service Delivery Support",
    "DE": "IT — End-User Services",
    "DF": "IT — Compute & Storage",
    "DG": "IT — Data/Analytics",
    "DH": "IT — Network/Telecom",
    "DJ": "IT — Software Maintenance",
    "DK": "IT — Other",
    "70": "IT — Products (hardware/SW)",
    "7A": "IT — Software (perpetual/SaaS)",
    "7B": "IT — Hardware",
    "R4": "Professional Support Services",
    "R7": "Logistics Support Services",
    "F0": "Natural Resources Mgmt",
    "13": "Munitions",
    "14": "Guided Missiles",
    "15": "Aircraft",
    "16": "Aircraft Components",
    "17": "Aircraft Launching Equipment",
    "18": "Space Vehicles",
    "19": "Ships",
    "58": "Communication/Electronics Equipment",
    "59": "Electrical/Electronic Components",
    "66": "Instruments & Lab Equipment",
    "69": "Training Aids/Devices",
    "U0": "Education/Training Services",
}

# NAICS 6-digit → industry area. SBIR is 98% in 541715 so 4-digit grouping
# is degenerate; 6-digit distinguishes the R&D sub-fields that matter.
NAICS_AREA_6 = {
    "541715": "R&D — Physical/Engineering/Life Sci",
    "541713": "R&D — Nanotechnology",
    "541714": "R&D — Biotechnology",
    "541720": "R&D — Social Sciences/Humanities",
    "541712": "R&D — Phys/Eng/Life (legacy)",
    "541690": "Sci/Tech Consulting",
    "541330": "Engineering Services",
    "541511": "Custom Computer Programming",
    "541512": "Computer Systems Design",
    "541519": "Other Computer Services",
    "513210": "Software Publishing",
    "518210": "Computing Infrastructure / Data Proc",
    "334413": "Semiconductor Mfg",
    "334118": "Computer Peripheral Mfg",
    "334511": "Search/Detection/Navigation Instruments",
    "336414": "Guided Missile / Space Vehicle Mfg",
    "927110": "Space R&D",
    "517410": "Satellite Telecommunications",
}

# PSC last-char → research stage (for A-series R&D codes only)
PSC_STAGE = {
    "1": "Basic Research",
    "2": "Applied Research",
    "3": "Experimental Development",
    "4": "Mgmt/Support",
    "5": "Operational Systems Dev",
    "6": "Commercialization",
}


def psc_area(code: str | None) -> str:
    if not code:
        return ""
    pfx = code[:2].upper()
    return PSC_AREA.get(pfx, f"Other (PSC {pfx}*)")


def naics_area(code: str | None) -> str:
    if not code:
        return ""
    return NAICS_AREA_6.get(code, f"Other (NAICS {code})")


def research_stage(psc: str | None) -> str:
    """Last char of A-series PSC = research stage (TRL proxy). Else empty."""
    if not psc or len(psc) < 4 or psc[0] != "A":
        return ""
    return PSC_STAGE.get(psc[3], "")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--award-year", type=int, default=2025)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    yy = args.award_year % 100
    out_path = args.out or Path(
        f"data/processed/sbir_phase3/fy{yy:02d}_phase3_prospect_digest.csv"
    )

    con = duckdb.connect()
    # Register UDFs for industry area mapping
    con.create_function("psc_area", psc_area, ["VARCHAR"], "VARCHAR")
    con.create_function("naics_area", naics_area, ["VARCHAR"], "VARCHAR")
    con.create_function("research_stage", research_stage, ["VARCHAR"], "VARCHAR")

    con.execute(
        "CREATE TABLE sbir AS SELECT * FROM read_csv_auto('data/raw/sbir/award_data.csv', "
        "header=True, sample_size=-1)"
    )
    con.execute(
        f"CREATE TABLE contracts AS SELECT * FROM read_json_auto("
        f"'data/processed/sbir_phase3/fy{yy:02d}_sbir_contract_lookups.jsonl', "
        f"format='newline_delimited')"
    )
    con.execute(
        f"CREATE TABLE grants AS SELECT * FROM read_json_auto("
        f"'data/processed/sbir_phase3/fy{yy:02d}_sbir_grant_lookups.jsonl', "
        f"format='newline_delimited')"
    )
    con.execute(
        f"CREATE TABLE p3 AS SELECT * FROM read_json_auto("
        f"'data/processed/sbir_phase3/fy{yy:02d}_sbir_phase3_contracts.jsonl', "
        f"format='newline_delimited')"
    )

    # Per-firm SBIR.gov rollup
    con.execute(
        f"""
        CREATE OR REPLACE VIEW firm_sbir AS
        SELECT
          UEI AS uei,
          any_value(Company) AS firm_name,
          any_value(City) AS city,
          any_value(State) AS state,
          any_value(Zip) AS zip,
          any_value("Number Employees") AS employees,
          any_value("Company Website") AS website,
          BOOL_OR("HUBZone Owned"='Y') AS hubzone,
          BOOL_OR("Woman Owned"='Y') AS woman_owned,
          BOOL_OR("Socially and Economically Disadvantaged"='Y') AS sed,
          SUM(CASE WHEN Phase='Phase I'  THEN 1 ELSE 0 END) AS phase_i_n,
          SUM(CASE WHEN Phase='Phase II' THEN 1 ELSE 0 END) AS phase_ii_n,
          ROUND(SUM("Award Amount"),0)::BIGINT AS fy_total_usd,
          MAX("Proposal Award Date") AS latest_award_date,
          ARG_MAX(Agency, "Proposal Award Date") AS latest_agency,
          ARG_MAX(Branch, "Proposal Award Date") AS latest_branch,
          ARG_MAX(Phase, "Proposal Award Date") AS latest_phase,
          ARG_MAX("Topic Code", "Proposal Award Date") AS latest_topic,
          ARG_MAX("Award Title", "Proposal Award Date") AS latest_title,
          ARG_MAX(SUBSTR(Abstract,1,200), "Proposal Award Date") AS abstract_excerpt
        FROM sbir
        WHERE "Award Year"={args.award_year} AND UEI IS NOT NULL AND TRIM(UEI)<>''
        GROUP BY UEI
        """
    )

    # FPDS lookup → UEI → NAICS/PSC aggregate (top code + area)
    con.execute(
        """
        CREATE OR REPLACE VIEW firm_naics_psc AS
        WITH naics_rank AS (
          SELECT "Recipient UEI" AS uei, NAICS.code AS code, COUNT(*) AS n,
                 ROW_NUMBER() OVER (PARTITION BY "Recipient UEI" ORDER BY COUNT(*) DESC) rk
          FROM contracts
          WHERE "Recipient UEI" IS NOT NULL AND NAICS IS NOT NULL
          GROUP BY 1,2
        ),
        psc_rank AS (
          SELECT "Recipient UEI" AS uei, PSC.code AS code, COUNT(*) AS n,
                 ROW_NUMBER() OVER (PARTITION BY "Recipient UEI" ORDER BY COUNT(*) DESC) rk
          FROM contracts
          WHERE "Recipient UEI" IS NOT NULL AND PSC IS NOT NULL
          GROUP BY 1,2
        ),
        all_uei AS (SELECT DISTINCT uei FROM naics_rank UNION SELECT DISTINCT uei FROM psc_rank)
        SELECT
          u.uei,
          (SELECT code FROM naics_rank WHERE uei=u.uei AND rk=1) AS top_naics,
          (SELECT STRING_AGG(code || '(' || n || ')', ';') FROM naics_rank
             WHERE uei=u.uei AND rk<=3) AS naics_top3,
          (SELECT code FROM psc_rank WHERE uei=u.uei AND rk=1) AS top_psc,
          (SELECT STRING_AGG(code || '(' || n || ')', ';') FROM psc_rank
             WHERE uei=u.uei AND rk<=3) AS psc_top3,
          (SELECT COUNT(*) FROM contracts WHERE "Recipient UEI"=u.uei) AS contracts_n
        FROM all_uei u
        """
    )

    # FABS lookup → UEI → CFDA aggregate
    con.execute(
        """
        CREATE OR REPLACE VIEW firm_cfda AS
        WITH cfda_rank AS (
          SELECT "Recipient UEI" AS uei, "CFDA Number" AS code, COUNT(*) AS n,
                 ROW_NUMBER() OVER (PARTITION BY "Recipient UEI" ORDER BY COUNT(*) DESC) rk
          FROM grants
          WHERE "Recipient UEI" IS NOT NULL AND "CFDA Number" IS NOT NULL
          GROUP BY 1,2
        )
        SELECT
          uei,
          MAX(CASE WHEN rk=1 THEN code END) AS top_cfda,
          STRING_AGG(code || '(' || n || ')', ';') FILTER (WHERE rk<=3) AS cfda_top3,
          MAX(COUNT(*)) OVER (PARTITION BY uei) AS grants_n
        FROM cfda_rank
        GROUP BY uei
        """
    )

    # Phase III precedent: which FY25 SBIR firms also appear in the Phase III file
    con.execute(
        """
        CREATE OR REPLACE VIEW firm_p3 AS
        SELECT "Recipient UEI" AS uei, COUNT(*) AS p3_awards_n,
               ROUND(SUM("Award Amount"),0)::BIGINT AS p3_total_usd
        FROM p3
        WHERE "Recipient UEI" IS NOT NULL
        GROUP BY 1
        """
    )

    digest = con.execute(
        """
        SELECT
          s.uei,
          s.firm_name,
          s.city,
          s.state,
          s.zip,
          s.phase_i_n,
          s.phase_ii_n,
          s.fy_total_usd,
          CAST(s.latest_award_date AS VARCHAR) AS latest_award_date,
          s.latest_phase,
          s.latest_agency,
          s.latest_branch,
          s.latest_topic,
          s.latest_title,
          s.abstract_excerpt,
          np.top_naics,
          naics_area(np.top_naics) AS naics_area,
          np.naics_top3,
          np.top_psc,
          psc_area(np.top_psc) AS psc_area,
          research_stage(np.top_psc) AS research_stage,
          np.psc_top3,
          COALESCE(np.contracts_n, 0) AS fy_contracts_in_fpds,
          cf.top_cfda,
          cf.cfda_top3,
          COALESCE(cf.grants_n, 0) AS fy_grants_in_fabs,
          (firm_p3.p3_awards_n IS NOT NULL) AS has_fy_phase3,
          COALESCE(firm_p3.p3_awards_n, 0) AS phase3_awards_n,
          COALESCE(firm_p3.p3_total_usd, 0) AS phase3_total_usd,
          s.hubzone, s.woman_owned, s.sed,
          s.employees, s.website
        FROM firm_sbir s
        LEFT JOIN firm_naics_psc np ON np.uei = s.uei
        LEFT JOIN firm_cfda cf      ON cf.uei = s.uei
        LEFT JOIN firm_p3           ON firm_p3.uei = s.uei
        ORDER BY s.fy_total_usd DESC
        """
    ).fetchdf()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    digest.to_csv(out_path, index=False)
    print(f"Wrote {len(digest):,} firms -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
