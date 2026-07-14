"""M0a recipient-scope prep: resolved SBIR Phase II firms (FY2016-2025) + their UEIs.

Defines exactly which recipients the M0a FPDS-ATOM pull must query. Deterministic; reuses the
repo canonicalizer. No external pull."""
import sys, json
import pandas as pd
sys.path.insert(0, "/Users/hollomancer/projects/sbir-analytics")
from sbir_etl.utils.company_canonicalizer import canonicalize_companies_from_awards
from sbir_etl.utils.text_normalization import normalize_company_name

CSV = "/Users/hollomancer/projects/sbir-analytics/data/raw/sbir/award_data.csv"
OUT = "/private/tmp/claude-501/-Users-hollomancer-projects-sbir-analytics/e3bbeac4-dccf-4d5b-bb43-a9565ac6d983/scratchpad/m0a_recipient_firms.json"

df = pd.read_csv(CSV, dtype=str, keep_default_na=False, na_values=[""])
df = df.rename(columns={"Company": "company", "UEI": "uei", "Duns": "duns"})
df["award_year"] = pd.to_numeric(df["Award Year"], errors="coerce")

def award_key(r):
    if pd.notna(r["uei"]): return f"UEI:{r['uei']}"
    if pd.notna(r["duns"]): return f"DUNS:{r['duns']}"
    return f"NAME:{normalize_company_name(r['company'])}"

canon = canonicalize_companies_from_awards(df, high_threshold=90, low_threshold=75)
df["_key"] = df.apply(award_key, axis=1)
df["_canon"] = df["_key"].map(canon).fillna(df["_key"])

# recipient frame: resolved entities with >=1 Phase II award in FY2016-2025
p2 = df[(df["Phase"] == "Phase II") & (df["award_year"].between(2016, 2025))]
firms = []
for c, g in df[df["_canon"].isin(p2["_canon"].unique())].groupby("_canon"):
    ueis = sorted(g["uei"].dropna().unique())
    dunss = sorted(g["duns"].dropna().unique())
    name = g["company"].str.strip().mode().iloc[0]
    firms.append({"canonical_id": c, "name": name, "ueis": ueis, "duns": dunss})

n_entities = len(firms)
with_uei = [f for f in firms if f["ueis"]]
no_uei = [f for f in firms if not f["ueis"]]
distinct_ueis = sorted({u for f in firms for u in f["ueis"]})

json.dump({"n_entities": n_entities, "n_with_uei": len(with_uei), "n_no_uei": len(no_uei),
           "n_distinct_ueis_to_query": len(distinct_ueis), "firms": firms},
          open(OUT, "w"))
print(f"resolved Phase II entities (FY2016-2025): {n_entities}")
print(f"  with >=1 UEI (queryable by UEI on FPDS): {len(with_uei)} ({100*len(with_uei)/n_entities:.0f}%)")
print(f"  NO UEI (name-only; FPDS-by-UEI coverage gap): {len(no_uei)} ({100*len(no_uei)/n_entities:.0f}%)")
print(f"  distinct UEIs to query: {len(distinct_ueis)}")
print(f"  firms with >1 UEI (identifier drift, query all): {sum(1 for f in with_uei if len(f['ueis'])>1)}")
print(f"persisted -> {OUT}")
