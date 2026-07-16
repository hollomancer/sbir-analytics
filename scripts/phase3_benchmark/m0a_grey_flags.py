"""Grey-layer Phase III flags: dark-pool contracts whose descriptions use a broader Phase III
variant ('SBIR PH III', 'PHIII', 'PH3', spelled-out 'SMALL BUSINESS INNOVATION RESEARCH PHASE III',
'PHASE III ... SMALL BUSINESS') that neither the exact 'SBIR PHASE III' API filter nor the narrower
strong text-scan (m0a_dark_analyze) caught. Excludes Phase I/II. Reproducible from the dark pool."""
import re
import pandas as pd

REPO = "/Users/hollomancer/projects/sbir-analytics"

def build():
    pool = pd.read_parquet(f"{REPO}/data/derived/m0a_dark_candidate_pool.parquet")
    strong = set(pd.read_parquet(f"{REPO}/data/derived/m0a_dark_discoverable_flags.parquet")
                 ["gen_id"].astype(str).str.upper())
    D = pool["Description"].fillna("").str.upper()
    PH3 = r"(?:PHASE\s*(?:III|3)\b|PH\.?\s*III\b|PH\s*3\b|PHIII)"
    SBIR = r"(?:SBIR|STTR|SMALL BUSINESS INNOVATION|SMALL BUSINESS TECHNOLOGY)"
    grey_pat = re.compile(rf"{SBIR}.{{0,60}}{PH3}|{PH3}.{{0,60}}{SBIR}")
    p12 = re.compile(r"\bPHASE\s*(?:I|II|1|2)\b|\bPH\.?\s*(?:I|II|1|2)\b|\bSBIR\s*(?:I|II)\b")
    is_grey = D.str.contains(grey_pat) & ~D.str.contains(p12)
    gr = pool[is_grey].copy()
    gr["gen_id"] = gr["gen_id"].astype(str).str.upper()
    gr = gr[~gr["gen_id"].isin(strong)]
    return pd.DataFrame({
        "gen_id": gr["gen_id"], "award_id": gr["Award ID"], "firm": gr["Recipient Name"],
        "amount_usd": pd.to_numeric(gr["Award Amount"], errors="coerce"),
        "sub_agency": gr["Awarding Sub Agency"], "action_date": gr["Action Date"],
        "description": gr["Description"]})

if __name__ == "__main__":
    out = build()
    out.to_parquet(f"{REPO}/data/derived/m0a_grey_flags.parquet")
    print(f"grey flags: {len(out)}  ${out['amount_usd'].sum()/1e6:.1f}M")
