"""Feasibility of SBA 7(a) and 504 loan files for an SBIR/STTR debt readout.

Tier: exploratory. Non-citable. Evaluation only: no pipeline or Dagster asset.
Memo: docs/research/sba-7a-504-loans-feasibility.md.

Stages (run in order; each writes to the git-ignored work folder):
    uv run --with openpyxl python scripts/research/sba_loans_feasibility.py inventory
    uv run python scripts/research/sba_loans_feasibility.py extension
    uv run python scripts/research/sba_loans_feasibility.py review_sample

The first run's match stage (including R1-fuzzy) is not in this script; the extension drops
R1-fuzzy (memo, "Extension"), and the first run's figures cannot be reproduced from it.

Reused code:
- ``sbir_etl.identity.company_names.normalize_company_name`` (profile RECIPIENT_V1) and
  ``sbir_etl.identity.geography.normalize_us_jurisdiction``;
- SBIR.gov concern key: UEI, then DUNS, then exact company name (``sbir_awards`` below).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SBA_DIR = ROOT / "data/raw/sba_foia/asof_260930"
SBIR_CSV = ROOT / "data/raw/sbir/award-export/2026-09-17/award_data.csv"
WORK = ROOT / "data/derived/sba_loans_feasibility"
FILES = {
    "504_FY1991_FY2009": "FOIA_504_FY1991_FY2009_asof_260930.csv",
    "504_FY2010_Present": "FOIA_504_FY2010_Present_asof_260930.csv",
    "7a_FY1991_FY1999": "FOIA_7a_FY1991_FY1999_asof_260930.csv",
    "7a_FY2000_FY2009": "FOIA_7a_FY2000_FY2009_asof_260930.csv",
    "7a_FY2010_FY2019": "FOIA_7a_FY2010_FY2019_asof_260930.csv",
    "7a_FY2020_Present": "FOIA_7a_FY2020_Present_asof_260930.csv",
}
STATUS_FIELDS = [
    "LoanStatus",
    "PaidInFullDate",
    "ChargeOffDate",
    "GrossChargeOffAmount",
    "FirstDisbursementDate",
]


def load_dictionary() -> pd.DataFrame:
    x = pd.read_excel(SBA_DIR / "7a_504_foia_data_dictionary.xlsx", sheet_name=None, header=None)
    rows = []
    for sheet, d in x.items():
        prog = "7a" if sheet.startswith("7(a)") else "504"
        for _, r in d.iloc[1:].iterrows():
            rows.append(
                {
                    "program": prog,
                    "field": str(r[0]).strip(),
                    "definition": " ".join(str(r[1]).split()) if pd.notna(r[1]) else "",
                }
            )
    return pd.DataFrame(rows)


def load_file(label: str) -> pd.DataFrame:
    d = pd.read_csv(SBA_DIR / FILES[label], dtype=str, keep_default_na=False, low_memory=False)
    d["_file"] = label
    return d


def blank(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().eq("")


# ------------------------------------------------------------------ task 1


def blank_to_nan(s: pd.Series) -> pd.Series:
    s = s.fillna("").astype(str).str.strip()
    return s.where(s != "", np.nan)


def concern_key(df: pd.DataFrame) -> np.ndarray:
    """UEI, else DUNS, else exact company name."""
    uei, duns, name = (blank_to_nan(df[c]) for c in ("UEI", "Duns", "Company"))
    return np.where(
        uei.notna(),
        "U:" + uei.fillna(""),
        np.where(duns.notna(), "D:" + duns.fillna(""), "N:" + name.fillna("")),
    )


def sbir_awards() -> pd.DataFrame:
    """Phase I/II awards with an award year, de-duplicated on agency + award ID + phase.

    Rows with a blank award ID are kept without de-duplication. Within a duplicate group the
    earliest award year (then file order) is kept.
    """
    cols = [
        "Company",
        "Agency",
        "Phase",
        "Contract",
        "Proposal Award Date",
        "Award Year",
        "UEI",
        "Duns",
    ]
    df = pd.read_csv(SBIR_CSV, usecols=cols, dtype=str, keep_default_na=False)
    df["phase"] = df["Phase"].str.strip()
    df = df[df["phase"].isin(["Phase I", "Phase II"])].copy()
    df["ay"] = pd.to_numeric(df["Award Year"], errors="coerce")
    df = df[df["ay"].notna()].copy()
    df["ay"] = df["ay"].astype(int)
    df["file_order"] = np.arange(len(df))
    df["contract"] = blank_to_nan(df["Contract"]).str.upper()
    df["agency"] = df["Agency"].str.strip()
    keyed = df["contract"].notna()
    k = df[keyed].sort_values(["ay", "file_order"], kind="stable")
    dup = (k["agency"] + "|" + k["contract"] + "|" + k["phase"]).duplicated(keep="first")
    df = pd.concat([k[~dup], df[~keyed]]).sort_values("file_order")
    df["key"] = concern_key(df)
    return df


def inventory() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    dic = load_dictionary()
    fill, status_rows, facts = [], [], {}
    for label in FILES:
        d = load_file(label)
        prog = label.split("_")[0]
        fy = pd.to_numeric(d["ApprovalFY"], errors="coerce")
        facts[label] = {
            "rows": len(d),
            "approval_fy_min": int(fy.min()),
            "approval_fy_max": int(fy.max()),
            "programs": d["Program"].value_counts().to_dict(),
            "loan_status": d["LoanStatus"].value_counts().to_dict(),
            "processing_methods": d["ProcessingMethod"].value_counts().to_dict(),
            "uei_or_duns_columns": [c for c in d.columns if re.search(r"uei|duns", c, re.I)],
        }
        for c in [c for c in d.columns if c != "_file"]:
            fill.append(
                {
                    "file": label,
                    "program": prog,
                    "field": c,
                    "fill_rate_pct": round(100 * float((~blank(d[c])).mean()), 1),
                }
            )
        for c in STATUS_FIELDS:
            if c not in d.columns:
                continue
            filled = ~blank(d[c])
            if c == "GrossChargeOffAmount":
                filled = pd.to_numeric(d[c], errors="coerce").fillna(0) > 0
            first = fy[filled].min()
            status_rows.append(
                {
                    "file": label,
                    "field": c,
                    "rows_filled": int(filled.sum()),
                    "first_approval_fy_with_value": None if pd.isna(first) else int(first),
                }
            )
        amt = {
            c: pd.to_numeric(d[c], errors="coerce")
            for c in ("GrossApproval", "SBAGuaranteedApproval", "ThirdPartyDollars")
            if c in d.columns
        }
        facts[label]["amount_fields"] = {
            c: {"nonnull": int(v.notna().sum()), "negative": int((v < 0).sum())}
            for c, v in amt.items()
        }
    f = pd.DataFrame(fill).pivot_table(
        index=["program", "field"], columns="file", values="fill_rate_pct"
    )
    f = f.reset_index().merge(dic, on=["program", "field"], how="left")
    f.to_csv(WORK / "field_inventory.csv", index=False)
    pd.DataFrame(status_rows).to_csv(WORK / "status_field_coverage.csv", index=False)
    (WORK / "inventory_facts.json").write_text(json.dumps(facts, indent=1, default=str))
    print(
        json.dumps(
            {
                k: {
                    kk: v[kk]
                    for kk in (
                        "rows",
                        "approval_fy_min",
                        "approval_fy_max",
                        "uei_or_duns_columns",
                        "loan_status",
                    )
                }
                for k, v in facts.items()
            },
            indent=1,
        )
    )
    print(pd.DataFrame(status_rows).to_string(index=False))


# ------------------------------------------------------------------ tasks 2-4
SEED = 20261120
AWARDEE_FY = (2015, 2024)  # active awardees: any Phase I/II award in these fiscal years
PLACEBO_BULK = ROOT / "data/raw/usaspending/contract_transactions_fy2024_bulk/2026-11-20"
SAM_ZIP = ROOT / "data/raw/sam_gov/public_v2/SAM_PUBLIC_UTF-8_MONTHLY_V2_20261101.ZIP"
PPP_DIR = ROOT / "data/raw/sba_ppp/asof_240930"
INTERNAL = ROOT / "data/internal/sba_loans_feasibility"
AS_OF = pd.Timestamp("2026-09-30")
RULES = ("R1_exact", "R2")
AGE_BANDS = ((0, 5, "<5"), (5, 10, "5-9"), (10, 20, "10-19"), (20, 999, "20+"))
SIZE_BANDS = ((0, 250e3, "<250k"), (250e3, 1e6, "250k-1M"), (1e6, 5e6, "1M-5M"), (5e6, 1e18, "5M+"))
# SAM.gov Public V2 zero-based positions (official v6.0 layout)
SAM_POS = {
    "uei": 0,
    "legal": 11,
    "dba": 12,
    "p_line1": 15,
    "p_city": 17,
    "p_state": 18,
    "p_zip": 19,
    "start": 24,
    "naics": 32,
    "m_line1": 39,
    "m_city": 41,
    "m_zip": 42,
    "m_state": 45,
}


def zip5(v: object) -> str:
    d = re.sub(r"\D", "", str(v or ""))
    return d[:5] if len(d) >= 5 else ""


def street_key(v: object) -> str:
    """House number + first street token, uppercased. Deliberately coarse; a
    street-only key is only used together with a name match (rule R2)."""
    toks = re.sub(r"[^A-Z0-9 ]", " ", str(v or "").upper()).split()
    return " ".join(toks[:2]) if len(toks) >= 2 and toks[0][0].isdigit() else ""


def loans() -> pd.DataFrame:
    from sbir_etl.identity.geography import normalize_us_jurisdiction

    cols = [
        "BorrName",
        "BorrStreet",
        "BorrCity",
        "BorrState",
        "BorrZip",
        "ApprovalDate",
        "ApprovalFY",
        "Program",
        "GrossApproval",
        "NaicsCode",
        "LoanStatus",
    ]
    parts = []
    for label in FILES:
        d = pd.read_csv(SBA_DIR / FILES[label], dtype=str, keep_default_na=False, usecols=cols)
        d["_file"] = label
        d["_row"] = np.arange(len(d))
        parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    d["state"] = d["BorrState"].map(lambda s: normalize_us_jurisdiction(s) or "")
    d["zip5"] = d["BorrZip"].map(zip5)
    d["street"] = d["BorrStreet"].map(street_key)
    d["loan_id"] = d["_file"] + ":" + d["_row"].astype(str)
    return d


def awardee_firms() -> pd.DataFrame:
    """One row per (concern key, name, state) with the concern's ZIPs, streets, and award facts."""
    from sbir_etl.identity.geography import normalize_us_jurisdiction

    df = sbir_awards()
    keyed = df[["key", "phase", "ay", "agency", "Proposal Award Date"]].copy()
    raw = pd.read_csv(
        SBIR_CSV,
        usecols=["Company", "UEI", "Duns", "State", "Zip", "Address1", "Phase", "Award Year"],
        dtype=str,
        keep_default_na=False,
    )
    raw = raw[raw["Phase"].str.strip().isin(["Phase I", "Phase II"])]
    raw["key"] = concern_key(raw)
    raw["state"] = raw["State"].map(lambda s: normalize_us_jurisdiction(s) or "")
    raw["zip5"] = raw["Zip"].map(zip5)
    raw["street"] = raw["Address1"].map(street_key)
    active = set(keyed.loc[keyed["ay"].between(*AWARDEE_FY), "key"])
    firm = keyed.groupby("key").agg(
        first_award_fy=("ay", "min"), agencies=("agency", lambda s: sorted(set(s)))
    )
    p2 = keyed[keyed["phase"] == "Phase II"].copy()
    p2["d"] = pd.to_datetime(p2["Proposal Award Date"], errors="coerce").fillna(
        pd.to_datetime((p2["ay"] - 1).astype(str) + "-10-01")
    )
    firm["first_phase_ii_date"] = p2.groupby("key")["d"].min()
    geo = raw.groupby("key").agg(
        zips=("zip5", lambda s: sorted({z for z in s if z})),
        streets=("street", lambda s: sorted({z for z in s if z})),
    )
    names = raw[["key", "Company", "state"]].rename(columns={"Company": "name"}).drop_duplicates()
    out = names.merge(firm, left_on="key", right_index=True).merge(
        geo, left_on="key", right_index=True
    )
    out["active"] = out["key"].isin(active)
    return out


def rnorm(v: object) -> str:
    from sbir_etl.identity.company_names import CompanyNameProfile, normalize_company_name

    return normalize_company_name(v, profile=CompanyNameProfile.RECIPIENT_V1)


def state(v: object) -> str:
    from sbir_etl.identity.geography import normalize_us_jurisdiction

    return normalize_us_jurisdiction(v) or ""


def band(x: float, bands: tuple) -> str:
    for lo, hi, lab in bands:
        if lo <= x < hi:
            return lab
    return ""


def sam_records(ueis: set[str]) -> pd.DataFrame:
    import csv
    import io
    import zipfile

    zf = zipfile.ZipFile(SAM_ZIP)
    zf = zipfile.ZipFile(io.BytesIO(zf.read(zf.namelist()[0])))  # Nov 2026 file nests a ZIP
    rows = []
    with zf.open(zf.namelist()[0]) as fh:
        for row in csv.reader(
            io.TextIOWrapper(fh, encoding="utf-8"), delimiter="|", quoting=csv.QUOTE_NONE
        ):
            if len(row) == 142 and row[0] in ueis:
                rows.append({k: row[i] for k, i in SAM_POS.items()})
    return pd.DataFrame(rows).drop_duplicates("uei").set_index("uei")


def bulk_recipients() -> pd.DataFrame:
    """FY2024 contract recipients from the USAspending bulk transaction file (amendment A4).

    One row per UEI with at least one transaction whose contracting officer's business-size
    determination is SMALL BUSINESS: the FY2024 obligated amount on those transactions, and every
    recipient name and address seen on them.
    """
    import glob
    import zipfile

    cols = [
        "recipient_uei",
        "recipient_name",
        "recipient_name_raw",
        "recipient_address_line_1",
        "recipient_state_code",
        "recipient_zip_4_code",
        "federal_action_obligation",
        "contracting_officers_determination_of_business_size",
    ]
    parts = []
    for z in glob.glob(str(PLACEBO_BULK / "*.zip")):
        zf = zipfile.ZipFile(z)
        for n in zf.namelist():
            if n.endswith(".csv"):
                for ch in pd.read_csv(
                    zf.open(n), dtype=str, keep_default_na=False, usecols=cols, chunksize=1_000_000
                ):
                    ch = ch[
                        (
                            ch["contracting_officers_determination_of_business_size"]
                            == "SMALL BUSINESS"
                        )
                        & (ch["recipient_uei"].str.strip() != "")
                    ]
                    parts.append(
                        ch.drop(columns="contracting_officers_determination_of_business_size")
                    )
    d = pd.concat(parts, ignore_index=True)
    d["amt"] = pd.to_numeric(d["federal_action_obligation"], errors="coerce").fillna(0.0)
    g = d.groupby("recipient_uei")
    return pd.DataFrame(
        {
            "amount": g["amt"].sum(),
            "names": g.apply(
                lambda x: (
                    {rnorm(n) for n in x["recipient_name"]}
                    | {rnorm(n) for n in x["recipient_name_raw"]}
                )
                - {""}
            ),
            "states": g["recipient_state_code"].apply(lambda s: {state(x) for x in s} - {""}),
            "zips": g["recipient_zip_4_code"].apply(lambda s: {zip5(x) for x in s} - {""}),
            "streets": g["recipient_address_line_1"].apply(
                lambda s: {street_key(x) for x in s} - {""}
            ),
            "transactions": g.size(),
        }
    )


def firm_frames() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Awardee and placebo-pool firm tables with SAM fields, bands, and name/address sets."""
    aw = (
        pd.read_parquet(INTERNAL / "awardee_firms.parquet")
        if (INTERNAL / "awardee_firms.parquet").exists()
        else awardee_firms()
    )
    act = aw[aw["active"]]
    aw_ueis = {k[2:] for k in act["key"] if k.startswith("U:")}
    agg = bulk_recipients()
    vol = agg["amount"]
    all_sbir_ueis = {k[2:] for k in aw["key"] if k.startswith("U:")}
    sbir_name_state = set(zip(aw["name"].map(rnorm), aw["state"], strict=True))
    pool_ueis = set(agg.index) - all_sbir_ueis
    sam = sam_records(aw_ueis | pool_ueis)
    log = {
        "bulk_small_business_ueis": len(agg),
        "active_awardee_ueis": len(aw_ueis),
        "active_awardees_in_aggregate": len(aw_ueis & set(agg.index)),
    }

    def build(ueis, src_names, src_states, src_zips, src_streets):
        out = []
        for u in ueis:
            if u not in sam.index:
                continue
            r = sam.loc[u]
            if not r["naics"] or not r["start"][:8].isdigit():
                continue
            start = pd.Timestamp(r["start"][:4] + "-" + r["start"][4:6] + "-" + r["start"][6:8])
            age = (pd.Timestamp("2024-10-01") - start).days / 365.25
            base_names = {rnorm(r["legal"])} - {""}
            var_names = base_names | ({rnorm(r["dba"])} - {""}) | src_names.get(u, set())
            base_states = {state(r["p_state"])} - {""}
            var_states = base_states | ({state(r["m_state"])} - {""}) | src_states.get(u, set())
            base_zips = {zip5(r["p_zip"])} - {""}
            var_zips = base_zips | ({zip5(r["m_zip"])} - {""}) | src_zips.get(u, set())
            base_streets = {street_key(r["p_line1"])} - {""}
            var_streets = (
                base_streets | ({street_key(r["m_line1"])} - {""}) | src_streets.get(u, set())
            )
            v = float(vol.get(u, 0.0) or 0.0)
            out.append(
                {
                    "uei": u,
                    "state": state(r["p_state"]),
                    "naics4": r["naics"][:4],
                    "naics3": r["naics"][:3],
                    "start": start,
                    "age_band": band(age, AGE_BANDS),
                    "size_band": band(v, SIZE_BANDS) if v > 0 else "",
                    "volume": v,
                    "base_names": base_names,
                    "base_states": base_states,
                    "base_zips": base_zips,
                    "base_streets": base_streets,
                    "var_names": var_names,
                    "var_states": var_states,
                    "var_zips": var_zips,
                    "var_streets": var_streets,
                }
            )
        return pd.DataFrame(out).set_index("uei")

    a_src = act[act["key"].str.startswith("U:")].assign(uei=lambda x: x["key"].str[2:])
    an = a_src.groupby("uei")["name"].apply(lambda s: {rnorm(n) for n in s} - {""}).to_dict()
    ast = a_src.groupby("uei")["state"].apply(lambda s: set(s) - {""}).to_dict()
    az = a_src.groupby("uei")["zips"].apply(lambda s: {z for zz in s for z in zz}).to_dict()
    ass = a_src.groupby("uei")["streets"].apply(lambda s: {z for zz in s for z in zz}).to_dict()
    awardees = build(aw_ueis, an, ast, az, ass)
    agencies = act.assign(uei=act["key"].str[2:]).groupby("uei")["agencies"].first()
    awardees["agencies"] = [agencies.get(u, []) for u in awardees.index]

    sub = agg.loc[sorted(pool_ueis)]
    pn, pst, pz, pss = (sub[c].to_dict() for c in ("names", "states", "zips", "streets"))
    pool = build(pool_ueis, pn, pst, pz, pss)
    # exclude pool firms whose SAM legal name and state match any SBIR/STTR awardee
    clash = [
        bool({(n, s) for n in r.base_names for s in r.base_states} & sbir_name_state)
        for r in pool.itertuples()
    ]
    log["pool_name_state_clash_excluded"] = int(sum(clash))
    pool = pool[[not c for c in clash]]
    log.update(
        {
            "awardees_with_sam_naics_and_start": len(awardees),
            "awardees_with_size": int((awardees["size_band"] != "").sum()),
            "pool_firms": len(pool),
        }
    )
    return awardees, pool, log


def match_pairs(
    awardees: pd.DataFrame, pool: pd.DataFrame, use_size: bool, rng: np.random.Generator
) -> tuple[pd.DataFrame, dict]:
    keys = ["state", "naics4", "age_band"] + (["size_band"] if use_size else [])
    keys3 = ["state", "naics3", "age_band"] + (["size_band"] if use_size else [])
    a = awardees[awardees["size_band"] != ""] if use_size else awardees
    order = a.index.to_numpy().copy()
    rng.shuffle(order)
    idx4 = {k: list(g.index) for k, g in pool.groupby(keys)}
    idx3 = {k: list(g.index) for k, g in pool.groupby(keys3)}
    for v in (*idx4.values(), *idx3.values()):
        rng.shuffle(v)
    used, pairs, fb, un = set(), [], 0, 0
    for u in order:
        r = a.loc[u]
        pick = next((p for p in idx4.get(tuple(r[k] for k in keys), []) if p not in used), None)
        if pick is None:
            pick = next(
                (p for p in idx3.get(tuple(r[k] for k in keys3), []) if p not in used), None
            )
            fb += pick is not None
        if pick is None:
            un += 1
            continue
        used.add(pick)
        pairs.append((u, pick))
    return pd.DataFrame(pairs, columns=["awardee", "placebo"]), {
        "eligible_awardees": len(a),
        "pairs": len(pairs),
        "naics3_fallback": fb,
        "unmatched": un,
    }


def loan_index(loan: pd.DataFrame) -> dict:
    loan = loan.copy()
    loan["n"] = loan["BorrName"].map(rnorm)
    loan["d"] = pd.to_datetime(loan["ApprovalDate"], errors="coerce")
    idx: dict = {}
    for i, n, s in zip(loan.index, loan["n"], loan["state"], strict=True):
        if n and s:
            idx.setdefault((n, s), []).append(i)
    return {"idx": idx, "loan": loan}


def firm_matches(firm: pd.Series, li: dict, variant: str) -> dict:
    """For one firm: matched loan rows under R1-exact and R2 within the exposure window."""
    names, states = firm[f"{variant}_names"], firm[f"{variant}_states"]
    zips, streets = firm[f"{variant}_zips"], firm[f"{variant}_streets"]
    loan = li["loan"]
    hits = {i for n in names for s in states for i in li["idx"].get((n, s), [])}
    out = {"R1_exact": set(), "R2": set()}
    for i in hits:
        d = loan.at[i, "d"]
        if pd.isna(d) or d < firm["start"] or d > AS_OF:
            continue
        out["R1_exact"].add(i)
        if (loan.at[i, "zip5"] and loan.at[i, "zip5"] in zips) or (
            loan.at[i, "street"] and loan.at[i, "street"] in streets
        ):
            out["R2"].add(i)
    return out


def boot_ratio(a: np.ndarray, p: np.ndarray, rng: np.random.Generator, n: int = 1000) -> tuple:
    if p.mean() == 0:
        return (None, None, None)
    idx = rng.integers(0, len(a), size=(n, len(a)))
    ra, rp = a[idx].mean(axis=1), p[idx].mean(axis=1)
    ok = rp > 0
    r = ra[ok] / rp[ok]
    return (
        round(a.mean() / p.mean(), 3),
        round(float(np.percentile(r, 2.5)), 3),
        round(float(np.percentile(r, 97.5)), 3),
    )


def rate_table(
    pairs: pd.DataFrame, A: dict, P: dict, prog_of: dict, rng: np.random.Generator
) -> list[dict]:
    rows = []
    for rule in RULES:
        for prog in ("either", "7A", "504"):

            def hit(m, rule=rule, prog=prog):
                s = m[rule]
                return bool(s) if prog == "either" else any(prog_of[i] == prog for i in s)

            a = np.array([hit(A[u]) for u in pairs["awardee"]])
            p = np.array([hit(P[u]) for u in pairs["placebo"]])
            ratio, lo, hi = boot_ratio(a, p, rng)
            rows.append(
                {
                    "rule": rule,
                    "program": prog,
                    "pairs": len(pairs),
                    "awardee_matched": int(a.sum()),
                    "awardee_rate_pct": round(100 * a.mean(), 2),
                    "placebo_matched": int(p.sum()),
                    "placebo_rate_pct": round(100 * p.mean(), 2),
                    "ratio": ratio,
                    "ci_low": lo,
                    "ci_high": hi,
                }
            )
    return rows


def ppp_index(name_keys: set[str]) -> dict:
    """PPP loans whose normalized name is among the firms' names (prefiltered by first token)."""
    import glob

    first = {n.split()[0] for n in name_keys if n}
    parts = []
    for f in sorted(glob.glob(str(PPP_DIR / "public_*.csv"))):
        for ch in pd.read_csv(
            f,
            dtype=str,
            keep_default_na=False,
            chunksize=500_000,
            encoding="latin-1",  # PPP files are not valid UTF-8
            usecols=[
                "BorrowerName",
                "BorrowerAddress",
                "BorrowerState",
                "BorrowerZip",
                "DateApproved",
            ],
        ):
            tok = (
                ch["BorrowerName"]
                .str.lower()
                .str.replace(r"[^a-z0-9 ]", " ", regex=True)
                .str.split()
                .str[0]
            )
            ch = ch[tok.isin(first)]
            if len(ch):
                parts.append(ch)
    d = pd.concat(parts, ignore_index=True)
    d = d.rename(
        columns={
            "BorrowerName": "BorrName",
            "BorrowerAddress": "BorrStreet",
            "BorrowerState": "BorrState",
            "DateApproved": "ApprovalDate",
        }
    )
    d["state"] = d["BorrState"].map(state)
    d["zip5"] = d["BorrowerZip"].map(zip5)
    d["street"] = d["BorrStreet"].map(street_key)
    d["Program"] = "PPP"
    return loan_index(d)


def extension() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    INTERNAL.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    awardees, pool, log = firm_frames()
    res: dict = {"log": log}
    loan = loans()
    li = loan_index(loan)
    prog_of = dict(
        zip(
            loan.index,
            loan["Program"].str.strip().str.upper().str.replace("7(A)", "7A"),
            strict=True,
        )
    )
    res["program_values"] = loan["Program"].value_counts().to_dict()
    # normalizer switch: canonical RECIPIENT_V1 vs the first run's text_normalization
    from sbir_etl.utils.text_normalization import normalize_name

    sample_names = loan["BorrName"].drop_duplicates()
    res["normalizer_switch"] = {
        "distinct_borrower_names": int(len(sample_names)),
        "names_normalizing_differently": int(
            sum(rnorm(n) != normalize_name(n, remove_suffixes=True) for n in sample_names)
        ),
    }
    ppp = None
    for analysis, use_size in (("primary", True), ("secondary", False)):
        pairs, mlog = match_pairs(awardees, pool, use_size, rng)
        res[f"{analysis}_matching"] = mlog
        pairs.to_csv(INTERNAL / f"pairs_{analysis}.csv", index=False)
        for variant in ("base", "var"):
            A = {u: firm_matches(awardees.loc[u], li, variant) for u in pairs["awardee"]}
            P = {u: firm_matches(pool.loc[u], li, variant) for u in pairs["placebo"]}
            res[f"{analysis}_{variant}_sba"] = rate_table(pairs, A, P, prog_of, rng)
            if analysis == "primary" and variant == "base":
                keep = [
                    (a, p, r)
                    for a, p in zip(pairs["awardee"], pairs["placebo"], strict=True)
                    for r in RULES
                ]
                save = [
                    {
                        "awardee": a,
                        "placebo": p,
                        "rule": r,
                        "awardee_loans": sorted(A[a][r]),
                        "placebo_loans": sorted(P[p][r]),
                    }
                    for a, p, r in keep
                ]
                pd.DataFrame(save).to_json(INTERNAL / "primary_base_matches.json", orient="records")
            # recall control B: PPP, pairs where both firms started on or before 2020-12-31
            if analysis == "primary":
                if ppp is None:
                    names = set().union(*awardees["var_names"], *pool["var_names"])
                    ppp = ppp_index(names)
                    ppp_prog = dict.fromkeys(ppp["loan"].index, "PPP")
                p20 = pairs[
                    [
                        awardees.at[a, "start"] <= pd.Timestamp("2020-12-31")
                        and pool.at[p, "start"] <= pd.Timestamp("2020-12-31")
                        for a, p in zip(pairs["awardee"], pairs["placebo"], strict=True)
                    ]
                ]
                PA = {u: firm_matches(awardees.loc[u], ppp, variant) for u in p20["awardee"]}
                PP = {u: firm_matches(pool.loc[u], ppp, variant) for u in p20["placebo"]}
                res[f"primary_{variant}_ppp"] = [
                    r for r in rate_table(p20, PA, PP, ppp_prog, rng) if r["program"] == "either"
                ]
                # recall-adjusted ratio on the same 2020-active pairs (paired bootstrap)
                adj = {}
                for rule in RULES:
                    a_l = np.array([bool(A[u][rule]) for u in p20["awardee"]])
                    p_l = np.array([bool(P[u][rule]) for u in p20["placebo"]])
                    a_p = np.array([bool(PA[u][rule]) for u in p20["awardee"]])
                    p_p = np.array([bool(PP[u][rule]) for u in p20["placebo"]])
                    idx = rng.integers(0, len(p20), size=(1000, len(p20)))
                    num = a_l[idx].mean(1) / np.where(
                        p_l[idx].mean(1) > 0, p_l[idx].mean(1), np.nan
                    )
                    den = a_p[idx].mean(1) / np.where(
                        p_p[idx].mean(1) > 0, p_p[idx].mean(1), np.nan
                    )
                    r = num / den
                    r = r[np.isfinite(r)]
                    point = (
                        (a_l.mean() / p_l.mean()) / (a_p.mean() / p_p.mean())
                        if p_l.mean() and p_p.mean() and a_p.mean()
                        else None
                    )
                    adj[rule] = {
                        "pairs_2020_active": len(p20),
                        "point": None if point is None else round(point, 3),
                        "ci_low": round(float(np.percentile(r, 2.5)), 3) if len(r) else None,
                        "ci_high": round(float(np.percentile(r, 97.5)), 3) if len(r) else None,
                    }
                res[f"primary_{variant}_recall_adjusted"] = adj
    (WORK / "extension_results.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))


def review_sample() -> None:
    """50 matches per group per rule from the primary baseline run; shuffled, group hidden."""
    awardees, pool, _ = firm_frames()
    loan = loans()
    m = pd.read_json(INTERNAL / "primary_base_matches.json")
    rows = []
    for rule in RULES:
        for grp, col, lcol, frame in (
            ("awardee", "awardee", "awardee_loans", awardees),
            ("placebo", "placebo", "placebo_loans", pool),
        ):
            cand = [
                (f, x)
                for f, ls, r in zip(m[col], m[lcol], m["rule"], strict=True)
                if r == rule
                for x in ls
            ]
            rs = np.random.default_rng(SEED).permutation(len(cand))[:50]
            for k in rs:
                f, li = cand[k]
                fr, lr = frame.loc[f], loan.loc[li]
                rows.append(
                    {
                        "group": grp,
                        "rule": rule,
                        "firm_names": "; ".join(sorted(fr["base_names"])),
                        "firm_state": fr["state"],
                        "firm_zips": "; ".join(sorted(fr["base_zips"])),
                        "firm_streets": "; ".join(sorted(fr["base_streets"])),
                        "firm_naics4": fr["naics4"],
                        "borr_name": lr["BorrName"],
                        "borr_street": lr["BorrStreet"],
                        "borr_city": lr["BorrCity"],
                        "borr_state": lr["BorrState"],
                        "borr_zip": lr["zip5"],
                        "loan_naics": lr["NaicsCode"],
                        "approval_date": lr["ApprovalDate"],
                    }
                )
    d = pd.DataFrame(rows).sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    d.insert(0, "review_id", [f"V{i + 1:03d}" for i in range(len(d))])
    d[["review_id", "group", "rule"]].to_csv(INTERNAL / "ext_blind_review_key.csv", index=False)
    d.drop(columns=["group", "rule"]).assign(review_label="").to_csv(
        INTERNAL / "ext_blind_review.csv", index=False
    )
    print(len(d), "rows")


# --- Amendment A5: all awardees, by awarding agency and award instrument -------------------

# Agencies whose ID-classified SBIR awards are at least 97% one instrument (grant and
# cooperative agreement counted together as assistance). Their unclassifiable IDs, including
# blanks, take that instrument as an inferred default. Mixed agencies get no default.
AGENCY_DEFAULT = {
    "Department of Agriculture": "grant",
    "Department of Defense": "contract",
    "Department of Energy": "grant",
    "Department of Transportation": "contract",
    "Environmental Protection Agency": "contract",
    "National Aeronautics and Space Administration": "contract",
    "National Science Foundation": "grant",
}
AGENCY_SHORT = {
    "Department of Agriculture": "USDA",
    "Department of Commerce": "DOC",
    "Department of Defense": "DoD",
    "Department of Education": "ED",
    "Department of Energy": "DOE",
    "Department of Health and Human Services": "HHS",
    "Department of Homeland Security": "DHS",
    "Department of Transportation": "DOT",
    "Department of the Interior": "DOI",
    "Environmental Protection Agency": "EPA",
    "National Aeronautics and Space Administration": "NASA",
    "National Science Foundation": "NSF",
    "Nuclear Regulatory Commission": "NRC",
}
HHS = "Department of Health and Human Services"
CONTRACT_LETTERS = set("ACDFGMPV")
ASSIST_DIGIT = {
    "1": "grant",
    "2": "cooperative agreement",
    "3": "other transaction",
    "9": "other transaction",
}


def classify_award(agency: str, cid: str) -> tuple[str, str]:
    raw = str(cid or "").strip().upper()
    a = re.sub(r"[^A-Z0-9]", "", raw)
    if not a or a in {"NULL", "NA", "NONE"} or a.startswith("SBAASSIGNED"):
        return "unclassified", "blank"
    if agency == HHS:
        m = re.match(r"^\d?([RUN])4[1-4][A-Z]{2}", a)
        if m:
            return {"R": "grant", "U": "cooperative agreement", "N": "contract"}[
                m.group(1)
            ], f"nih-activity-{m.group(1)}4x"
        if re.match(r"^\d?SB1[A-Z]{2}", a):
            return "grant", "nih-activity-SB1"
        if a.startswith(("HHSN", "75N", "75D", "75F", "75A")) or re.match(r"^2\d{2}20\d{2}", a):
            return "contract", "hhs-contract-prefix"
    if agency == "Department of Energy":
        if a.startswith("DEAR"):
            return "cooperative agreement", "doe-arpa-e"
        if a.startswith(("DEFG", "DESC", "DEEE", "DENE", "DEFE")) or re.match(
            r"^\d{2}\d{2}ER\d", a
        ):
            return "grant", "doe-assistance-prefix"
        if a.startswith("DEAC"):
            return "contract", "doe-contract-prefix"
    if agency == "National Science Foundation" and re.fullmatch(r"\d{6,8}", a):
        return "grant", "nsf-numeric"
    if agency == "Department of Agriculture" and re.fullmatch(r"\d{2,4}33610\d{4,5}", a):
        return "grant", "usda-nifa-33610"
    if agency == "Department of Commerce":
        if re.match(r"^70NANB\d{2}H", a):
            return "cooperative agreement", "nist-70nanb-h"
        if re.match(r"^NA\d{2}[A-Z]{3}", a):
            return "grant", "noaa-assistance"
    if agency == "Department of Education" and re.match(r"^(H133|R305|R324|H327|H180)", a):
        return "grant", "ed-grant-prefix"
    if agency == "Department of Education" and re.match(r"^(EDIES\d{2}C|ED\d{2}(PO|CO))", a):
        return "contract", "ed-ies-or-po-contract"
    m = re.match(r"^([A-Z0-9]{6})(\d{2})([A-Z0-9])", a)
    if m and len(a) >= 11:
        L = m.group(3)
        if L in CONTRACT_LETTERS:
            return "contract", f"piid-position-9-{L}"
        if L in ASSIST_DIGIT and re.search("[A-Z]", m.group(1)):
            return ASSIST_DIGIT[L], f"assistance-position-9-{L}"
    return "unclassified", "no-rule"


def instrument(agency: str, cid: str) -> tuple[str, str]:
    """(instrument, source): an ID rule, else the agency default, else unclassified."""
    c, rule = classify_award(agency, cid)
    if c != "unclassified":
        return c, f"id:{rule}"
    if agency in AGENCY_DEFAULT:
        return AGENCY_DEFAULT[agency], f"default:{rule}"
    return "unclassified", rule


def awards_frame() -> pd.DataFrame:
    """Every deduplicated Phase I/II award with its concern key and instrument."""
    df = sbir_awards()
    ins = [instrument(a, c) for a, c in zip(df["agency"], df["Contract"], strict=True)]
    df["instrument"] = [x[0] for x in ins]
    df["instrument_source"] = [x[1] for x in ins]
    df["agency_short"] = df["agency"].map(AGENCY_SHORT)
    return df


USAS_GROUPS = {
    "contract": ["A", "B", "C", "D"],
    "assistance": ["02", "03", "04", "05"],  # one award-type group per request
}


def usaspending_lookup(aid: str) -> list[tuple[str, str]]:
    import time
    import urllib.request

    out = []
    for group, codes in USAS_GROUPS.items():
        body = {
            "filters": {
                "award_ids": [aid],
                "award_type_codes": codes,
                "time_period": [{"start_date": "2007-10-01", "end_date": "2026-09-30"}],
            },
            "fields": ["Award ID", "Award Type", "Contract Award Type"],
            "limit": 5,
            "page": 1,
        }
        req = urllib.request.Request(
            "https://api.usaspending.gov/api/v2/search/spending_by_award/",
            json.dumps(body).encode(),
            {"User-Agent": "generic research script", "Content-Type": "application/json"},
        )
        for attempt in range(3):
            try:
                res = json.load(urllib.request.urlopen(req, timeout=60))["results"]
                break
            except Exception:
                time.sleep(5 * (attempt + 1))
        else:
            res = []
        out += [
            (group, x.get("Award Type") or x.get("Contract Award Type") or "")
            for x in res
            if re.sub(r"[^A-Z0-9]", "", str(x.get("Award ID", "")).upper()) == aid
        ]
    return out


def instrument_check() -> None:
    """Task 1 check: a stratified sample of FY2009-FY2024 award IDs against USAspending.

    Up to 12 IDs per (agency, classification source). Rows are appended as they finish, so an
    interrupted run resumes.
    """
    from concurrent.futures import ThreadPoolExecutor

    df = awards_frame()
    a = df[df["ay"].between(2009, 2024) & (df["instrument_source"] != "default:blank")].copy()
    a["aid"] = a["Contract"].str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    a["core"] = a["aid"].str.extract(r"^\d?([RUN]4[1-4][A-Z]{2}\d{6})")[0]
    rng = np.random.default_rng(SEED)
    picks = []
    for _, g in a.groupby(["agency_short", "instrument_source"]):
        picks += [g.index[i] for i in rng.permutation(len(g))[:12]]
    out = WORK / "a5_instrument_check.csv"
    done = set(pd.read_csv(out)["row"]) if out.exists() else set()
    todo = [i for i in picks if i not in done]

    def one(i: int) -> dict:
        r = a.loc[i]
        hits = usaspending_lookup(r["aid"])
        if not hits and isinstance(r["core"], str):
            hits = usaspending_lookup(r["core"])
        return {
            "row": i,
            "agency": r["agency_short"],
            "source": r["instrument_source"],
            "classified": r["instrument"],
            "award_year": int(r["ay"]),
            "usaspending": "; ".join(sorted({f"{x[0]}:{x[1]}" for x in hits})),
        }

    with ThreadPoolExecutor(4) as ex:
        for k, row in enumerate(ex.map(one, todo)):
            pd.DataFrame([row]).to_csv(out, mode="a", header=not out.exists(), index=False)
            if k % 50 == 0:
                print(k, "of", len(todo), flush=True)
    print(len(picks), "sampled")


COHORTS = (
    (0, 1990, "<=FY1989"),
    (1990, 1995, "FY1990-94"),
    (1995, 2000, "FY1995-99"),
    (2000, 2005, "FY2000-04"),
    (2005, 2010, "FY2005-09"),
    (2010, 2015, "FY2010-14"),
    (2015, 2020, "FY2015-19"),
    (2020, 2100, "FY2020+"),
)
AWARD_BANDS = ((1, 2, "1"), (2, 4, "2-3"), (4, 10, "4-9"), (10, 25, "10-24"), (25, 10**6, "25+"))
MIN_RATED = 30
PPP_WINDOW_FY = (2016, 2020)  # recall control: firms with an award in FY2016-FY2020


def award_firms() -> tuple[pd.DataFrame, dict]:
    """Task 2: one row per concern key with agency, instrument mix, dates, and name/address sets."""
    from sbir_etl.identity.geography import normalize_us_jurisdiction

    a = awards_frame()
    pad = pd.to_datetime(a["Proposal Award Date"], errors="coerce")
    a["date"] = pad.fillna(pd.to_datetime((a["ay"] - 1).astype(str) + "-10-01"))
    a = a.sort_values(["date", "file_order"], kind="stable")
    raw = pd.read_csv(
        SBIR_CSV,
        usecols=["Company", "UEI", "Duns", "State", "Zip", "Address1", "Phase", "Award Year"],
        dtype=str,
        keep_default_na=False,
    )
    raw = raw[raw["Phase"].str.strip().isin(["Phase I", "Phase II"])].copy()
    raw["key"] = concern_key(raw)
    raw["ay"] = pd.to_numeric(raw["Award Year"], errors="coerce")
    raw["st"] = raw["State"].map(lambda v: normalize_us_jurisdiction(v) or "")
    raw["z"] = raw["Zip"].map(zip5)
    raw["s"] = raw["Address1"].map(street_key)
    raw["n"] = raw["Company"].map(rnorm)
    raw = raw.sort_values("ay", kind="stable")

    g = a.groupby("key")
    firm = pd.DataFrame(
        {
            "agency_first": g["agency_short"].first(),
            "agencies": g["agency_short"].agg(lambda x: tuple(sorted(set(x)))),
            "n_awards": g.size(),
            "first_fy": g["ay"].min(),
            "first_date": g["date"].min(),
            "last_date": g["date"].max(),
            "first_p2_date": a[a["phase"] == "Phase II"].groupby("key")["date"].min(),
            "has_grant": g["instrument"].agg(
                lambda x: bool(set(x) & {"grant", "cooperative agreement"})
            ),
            "has_contract": g["instrument"].agg(lambda x: "contract" in set(x)),
            "has_ot": g["instrument"].agg(lambda x: "other transaction" in set(x)),
            "ppp_window": g["ay"].agg(lambda x: bool(x.between(*PPP_WINDOW_FY).any())),
        }
    )
    firm["mix"] = np.select(
        [firm["has_grant"] & firm["has_contract"], firm["has_grant"], firm["has_contract"]],
        ["both", "grant-only", "contract-only"],
        "unclassified",
    )
    firm["cohort"] = firm["first_fy"].map(lambda v: band(v, COHORTS))
    firm["award_band"] = firm["n_awards"].map(lambda v: band(v, AWARD_BANDS))

    rg = raw.groupby("key")
    last = rg.tail(1).set_index("key")  # address on the most recent award (baseline)
    modal = raw[raw["n"] != ""].groupby("key")["n"].agg(lambda x: x.value_counts().index[0])
    firm["base_names"] = modal.reindex(firm.index).map(
        lambda v: {v} if isinstance(v, str) else set()
    )
    firm["state"] = last["st"].reindex(firm.index).fillna("")
    firm["base_states"] = firm["state"].map(lambda v: {v} - {""})
    firm["base_zips"] = last["z"].reindex(firm.index).fillna("").map(lambda v: {v} - {""})
    firm["base_streets"] = last["s"].reindex(firm.index).fillna("").map(lambda v: {v} - {""})
    for col, src in (
        ("var_names", "n"),
        ("var_states", "st"),
        ("var_zips", "z"),
        ("var_streets", "s"),
    ):
        firm[col] = rg[src].agg(lambda x: set(x) - {""}).reindex(firm.index)
        firm[col] = firm[col].map(lambda v: v if isinstance(v, set) else set())
    firm["start"] = pd.Timestamp("1900-01-01")  # any approval in the files counts (A5)

    ueis = {k[2:] for k in firm.index if k.startswith("U:")}
    sam = sam_records(ueis)
    firm["naics2"] = [
        sam.at[k[2:], "naics"][:2] if k.startswith("U:") and k[2:] in sam.index else ""
        for k in firm.index
    ]
    log = {
        "awards": len(a),
        "firms": len(firm),
        "instrument_by_source": a.groupby(
            ["instrument", a["instrument_source"].str.split(":").str[0]]
        )
        .size()
        .pipe(lambda x: {f"{i}:{src}": int(v) for (i, src), v in x.items()}),
        "contract_field_filled": int((a["Contract"].str.strip() != "").sum()),
    }
    return firm, log


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def cell(k: int, n: int) -> dict:
    if n >= MIN_RATED:
        lo, hi = wilson(k, n)
        return {
            "matched": k,
            "firms": n,
            "rate_pct": round(100 * k / n, 2),
            "ci_low_pct": round(100 * lo, 2),
            "ci_high_pct": round(100 * hi, 2),
        }
    return {"matched": k, "firms": n, "rate_pct": "too few to rate"}


def by(firm: pd.DataFrame, keys: list[str], outcome: str) -> list[dict]:
    out = []
    for k, g in firm.groupby(keys, dropna=False):
        k = k if isinstance(k, tuple) else (k,)
        out.append(dict(zip(keys, k, strict=True)) | cell(int(g[outcome].sum()), len(g)))
    return out


def indirect(
    firm: pd.DataFrame,
    group: str,
    outcome: str,
    strata: list[str],
    rng: np.random.Generator,
    n_boot: int = 1000,
) -> dict:
    """Indirect standardization: observed / expected from population stratum rates."""
    rate = firm.groupby(strata)[outcome].mean().rename("_r")
    f = firm.join(rate, on=strata)
    overall = firm[outcome].mean()
    out = {}
    for gname, g in f.groupby(group):
        if len(g) < MIN_RATED:
            out[gname] = {"firms": len(g), "standardized_pct": "too few to rate"}
            continue
        o, e = g[outcome].to_numpy(float), g["_r"].to_numpy()
        boots = []
        for _ in range(n_boot):
            i = rng.integers(0, len(g), len(g))
            boots.append(o[i].sum() / e[i].sum() * overall)
        out[gname] = {
            "firms": len(g),
            "observed": int(o.sum()),
            "expected": round(float(e.sum()), 1),
            "standardized_pct": round(100 * o.sum() / e.sum() * overall, 2),
            "ci_low_pct": round(100 * float(np.percentile(boots, 2.5)), 2),
            "ci_high_pct": round(100 * float(np.percentile(boots, 97.5)), 2),
            "_o": o,
            "_e": e,
        }
    return out


def ratio_ci(
    a: dict, b: dict, overall: float, rng: np.random.Generator, n_boot: int = 1000
) -> dict:
    """Ratio of two standardized rates (a / b), firm bootstrap within each group."""
    if "_o" not in a or "_o" not in b:
        return {"ratio": "too few to rate"}
    r = []
    for _ in range(n_boot):
        i = rng.integers(0, len(a["_o"]), len(a["_o"]))
        j = rng.integers(0, len(b["_o"]), len(b["_o"]))
        sa = a["_o"][i].sum() / a["_e"][i].sum()
        sb = b["_o"][j].sum() / b["_e"][j].sum()
        r.append(sa / sb if sb else np.nan)
    pt = (a["_o"].sum() / a["_e"].sum()) / (b["_o"].sum() / b["_e"].sum())
    return {
        "ratio": round(float(pt), 3),
        "ci_low": round(float(np.nanpercentile(r, 2.5)), 3),
        "ci_high": round(float(np.nanpercentile(r, 97.5)), 3),
    }


def strip_private(d: dict) -> dict:
    return {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in d.items()}


def agency_cut() -> None:
    """Tasks 3-9 of amendment A5."""
    rng = np.random.default_rng(SEED)
    firm, log = award_firms()
    loan = loans()
    loan["prog"] = loan["Program"].str.strip()
    li = loan_index(loan)
    for v in ("base", "var"):
        for prog in ("7A", "504"):
            for rule in RULES:
                firm[f"{v}_{prog}_{rule}"] = False
        firm[f"{v}_first7a"] = pd.NaT
    keep = {}
    for k, f in firm.iterrows():
        for v in ("base", "var"):
            m = firm_matches(f, li, v)
            for rule in RULES:
                for prog in ("7A", "504"):
                    ids = [i for i in m[rule] if loan.at[i, "prog"] == prog]
                    firm.at[k, f"{v}_{prog}_{rule}"] = bool(ids)
            r2 = [i for i in m["R2"] if loan.at[i, "prog"] == "7A"]
            if r2:
                firm.at[k, f"{v}_first7a"] = min(li["loan"].at[i, "d"] for i in r2)
                if v == "base":
                    keep[k] = sorted(r2)
    y = "base_7A_R2"
    res: dict = {"log": log}
    res["counts_first_agency_by_mix"] = pd.crosstab(
        firm["agency_first"], firm["mix"], margins=True
    ).to_dict(orient="index")
    any_ag = firm.explode("agencies").reset_index(drop=True)
    res["counts_any_agency_by_mix"] = pd.crosstab(any_ag["agencies"], any_ag["mix"]).to_dict(
        orient="index"
    )
    res["mix_counts"] = firm["mix"].value_counts().to_dict()
    res["has_ot_firms"] = int(firm["has_ot"].sum())
    res["overall"] = {
        f"{v}_{p}_{r}": cell(int(firm[f"{v}_{p}_{r}"].sum()), len(firm))
        for v in ("base", "var")
        for p in ("7A", "504")
        for r in RULES
    }
    tables = {}
    for name, keys in (
        ("first_agency", ["agency_first"]),
        ("mix", ["mix"]),
        ("first_agency_x_mix", ["agency_first", "mix"]),
    ):
        t = pd.DataFrame(by(firm, keys, y))
        for extra in ("base_7A_R1_exact", "base_504_R2", "var_7A_R2"):
            t[extra] = [r["matched"] for r in by(firm, keys, extra)]
        tables[name] = t.to_dict(orient="records")
    t = pd.DataFrame(by(any_ag, ["agencies"], y))
    tables["any_agency"] = t.to_dict(orient="records")
    res["tables"] = tables

    # Task 6: timing of the first matched 7(a) approval (baseline, R2)
    m = firm[firm[y]].copy()
    d = m["base_first7a"]
    m["timing"] = np.select(
        [d < m["first_date"], m["first_p2_date"].isna(), d < m["first_p2_date"]],
        [
            "before first award",
            "after first award, firm has no Phase II",
            "between first award and first Phase II",
        ],
        "after first Phase II",
    )
    res["timing"] = {
        "matched_firms": len(m),
        "categories": m["timing"].value_counts().to_dict(),
        "after_last_award": int((d > m["last_date"]).sum()),
        "first_award_before_fy1991": int((m["first_fy"] < 1991).sum()),
    }

    # Task 7: exposure
    res["cohort"] = by(firm, ["cohort"], y)
    for yrs in (5, 10):
        end = firm["first_date"] + pd.DateOffset(years=yrs)
        elig = (end <= AS_OF) & (firm["first_fy"] >= 1991)
        w = (firm["base_first7a"] >= firm["first_date"]) & (firm["base_first7a"] <= end)
        firm[f"within{yrs}"] = w.fillna(False) & firm[y]
        e = firm[elig]
        res[f"within_{yrs}y"] = {
            "eligible_rule": f"first award FY1991 or later and {yrs} full years before {AS_OF.date()}",
            "overall": cell(int(e[f"within{yrs}"].sum()), len(e)),
            "by_cohort": by(e, ["cohort"], f"within{yrs}"),
            "by_mix": by(e, ["mix"], f"within{yrs}"),
            "by_first_agency": by(e, ["agency_first"], f"within{yrs}"),
        }
    res["mix_x_cohort"] = by(firm, ["cohort", "mix"], y)

    # Task 8: standardization
    overall = firm[y].mean()
    std = {}
    for label, strata in (
        ("state_cohort_awardband", ["state", "cohort", "award_band"]),
        ("cohort_only", ["cohort"]),
    ):
        sa = indirect(firm, "agency_first", y, strata, rng)
        sm = indirect(firm, "mix", y, strata, rng)
        std[label] = {
            "first_agency": strip_private(sa),
            "mix": strip_private(sm),
            "grant_only_over_contract_only": ratio_ci(
                sm["grant-only"], sm["contract-only"], overall, rng
            ),
            "both_over_contract_only": ratio_ci(sm["both"], sm["contract-only"], overall, rng),
        }
    raw_mix = indirect(firm.assign(_one=1), "mix", y, ["_one"], rng)
    std["raw_ratio_grant_only_over_contract_only"] = ratio_ci(
        raw_mix["grant-only"], raw_mix["contract-only"], overall, rng
    )
    nf = firm[firm["naics2"] != ""]
    sn = indirect(nf, "mix", y, ["state", "cohort", "award_band", "naics2"], rng)
    std["naics_side"] = {
        "firms_with_naics": len(nf),
        "mix": strip_private(sn),
        "grant_only_over_contract_only": ratio_ci(
            sn["grant-only"], sn["contract-only"], nf[y].mean(), rng
        ),
    }
    res["standardized"] = std

    # Task 9: recall
    res["award_band_base_vs_var"] = [
        {
            "award_band": b,
            "firms": len(g),
            "base": cell(int(g[y].sum()), len(g)),
            "var": cell(int(g["var_7A_R2"].sum()), len(g)),
        }
        for b, g in firm.groupby("award_band")
    ]
    sv = indirect(firm, "mix", "var_7A_R2", ["state", "cohort", "award_band"], rng)
    res["var_grant_only_over_contract_only_std"] = ratio_ci(
        sv["grant-only"], sv["contract-only"], firm["var_7A_R2"].mean(), rng
    )
    pf = firm[firm["ppp_window"]].copy()
    ppp = ppp_index(set().union(*pf["base_names"]))
    pf["ppp_R2"] = [bool(firm_matches(f, ppp, "base")["R2"]) for _, f in pf.iterrows()]
    res["ppp"] = {
        "window": f"firms with an award in FY{PPP_WINDOW_FY[0]}-FY{PPP_WINDOW_FY[1]}",
        "overall": cell(int(pf["ppp_R2"].sum()), len(pf)),
        "by_mix": by(pf, ["mix"], "ppp_R2"),
        "by_first_agency": by(pf, ["agency_first"], "ppp_R2"),
    }
    sp = indirect(pf, "mix", "ppp_R2", ["state", "cohort", "award_band"], rng)
    sl = indirect(pf, "mix", y, ["state", "cohort", "award_band"], rng)
    res["ppp"]["grant_only_over_contract_only_std"] = ratio_ci(
        sp["grant-only"], sp["contract-only"], pf["ppp_R2"].mean(), rng
    )
    res["ppp"]["sba_same_firms_grant_only_over_contract_only_std"] = ratio_ci(
        sl["grant-only"], sl["contract-only"], pf[y].mean(), rng
    )

    INTERNAL.mkdir(parents=True, exist_ok=True)
    firm[
        ["agency_first", "mix", "n_awards", "first_fy", y, "var_7A_R2", "base_first7a"]
    ].to_parquet(INTERNAL / "a5_firms.parquet")
    pd.Series(keep).to_json(INTERNAL / "a5_base_r2_7a_matches.json")
    (WORK / "a5_results.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({"firms": len(firm), "overall": res["overall"][y]}, default=str))


def a5_review_sample() -> None:
    """Task 10: up to 30 matches per instrument group, shuffled, group hidden, unlabeled."""
    firm, _ = award_firms()
    loan = loans()
    keep = pd.read_json(INTERNAL / "a5_base_r2_7a_matches.json", typ="series")
    rows = []
    rng = np.random.default_rng(SEED)
    for mix in sorted(firm["mix"].unique()):
        ks = [k for k in keep.index if firm.at[k, "mix"] == mix]
        for j in rng.permutation(len(ks))[:30]:
            k = ks[j]
            f, lr = firm.loc[k], loan.loc[keep[k][0]]
            rows.append(
                {
                    "group": mix,
                    "firm_names": "; ".join(sorted(f["base_names"])),
                    "firm_state": f["state"],
                    "firm_zips": "; ".join(sorted(f["base_zips"])),
                    "firm_streets": "; ".join(sorted(f["base_streets"])),
                    "borr_name": lr["BorrName"],
                    "borr_street": lr["BorrStreet"],
                    "borr_city": lr["BorrCity"],
                    "borr_state": lr["BorrState"],
                    "borr_zip": lr["zip5"],
                    "approval_date": lr["ApprovalDate"],
                }
            )
    d = pd.DataFrame(rows).sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    d.insert(0, "review_id", [f"A{i + 1:03d}" for i in range(len(d))])
    d[["review_id", "group"]].to_csv(INTERNAL / "a5_review_key.csv", index=False)
    d.drop(columns=["group"]).assign(review_label="").to_csv(
        INTERNAL / "a5_review.csv", index=False
    )
    print(
        len(d),
        "rows;",
        d.merge(pd.read_csv(INTERNAL / "a5_review_key.csv"))["group"].value_counts().to_dict(),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "stage",
        choices=[
            "inventory",
            "extension",
            "review_sample",
            "instrument_check",
            "agency_cut",
            "a5_review_sample",
        ],
    )
    args = ap.parse_args()
    {
        "inventory": inventory,
        "extension": extension,
        "review_sample": review_sample,
        "instrument_check": instrument_check,
        "agency_cut": agency_cut,
        "a5_review_sample": a5_review_sample,
    }[args.stage]()


if __name__ == "__main__":
    main()
