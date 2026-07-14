"""M0a undercount: join description-Phase-III to the coded SR3/ST3 set; emit uncoded flags.

Undercount = DoD contracts described 'SBIR PHASE III' that lack the SR3/ST3 code. Flags are for
human review — never a violation determination. Output: data/derived/m0a_status_denial_flags.parquet."""
import re, json
import pandas as pd

REPO = "/Users/hollomancer/projects/sbir-analytics"
coded = pd.read_parquet(f"{REPO}/data/derived/m0a_coded_dod.parquet")
desc = pd.read_parquet(f"{REPO}/data/derived/m0a_desc_phase3_dod.parquet")

def norm(x): return str(x).strip().upper() if x is not None else ""
def coded_genid(r):
    p, a = norm(r["order_piid"]), norm(r["order_agency"]) or "-NONE-"
    ip, ia = norm(r["idv_piid"]) or "-NONE-", norm(r["idv_agency"]) or "-NONE-"
    return f"CONT_AWD_{p}_{a}_{ip}_{ia}"
coded_keys = set(coded.apply(coded_genid, axis=1))

desc["gen_id"] = desc["generated_internal_id"].map(norm)
desc["is_coded"] = desc["gen_id"].isin(coded_keys)
flags = desc.loc[~desc["is_coded"]].copy()  # uncoded = status-denial flags (for review)
flags = flags.rename(columns={"Award ID": "award_id", "Description": "description",
                              "Awarding Sub Agency": "awarding_sub_agency", "Action Date": "action_date",
                              "Recipient Name": "firm", "Award Amount": "amount_usd"})
flags["flag_reason"] = "described 'SBIR PHASE III'; no SR3/ST3 code on the award"
flags["disposition"] = None  # nullable — human adjudication flows back as a label
flags["_amt"] = pd.to_numeric(flags.get("amount_usd"), errors="coerce")
flags = flags.sort_values("_amt", ascending=False)  # review-priority order (largest $ first)
flags[["award_id", "gen_id", "firm", "amount_usd", "awarding_sub_agency", "action_date",
       "description", "flag_reason", "disposition"]].to_parquet(
    f"{REPO}/data/derived/m0a_status_denial_flags.parquet")

n = len(desc); u = len(flags); flagged_usd = float(flags["_amt"].sum())
summary = {
    "window": "FY2016-2025 (SIGNED_DATE)", "agency": "DoD (dept 9700)",
    "coded_universe": {"transactions": 28264, "distinct_awards": int(len(coded)),
                       "distinct_firms": int(coded["uei"].nunique())},
    "description_phase3_set": n,
    "coded_of_description_set": int(desc["is_coded"].sum()),
    "uncoded_flags": u, "undercount_rate": round(u / n, 4),
    "flagged_obligations_usd": round(flagged_usd, 0),
    "by_sub_agency": {k: {"total": int(v), "uncoded": int(flags["awarding_sub_agency"].eq(k).sum()),
                          "uncoded_usd": round(float(flags.loc[flags["awarding_sub_agency"].eq(k), "_amt"].sum()), 0)}
                      for k, v in desc.get("Awarding Sub Agency").value_counts().head(10).items()},
    "caveat": ("14.7% is a LOWER BOUND — measures only contracts whose description says 'SBIR PHASE "
               "III'. Non-obvious uncoded Phase III (dark undercount) needs Product 1 inferential flags. "
               "Flags are for human review, not violation findings."),
}
json.dump(summary, open(f"{REPO}/data/derived/m0a_undercount_summary.json", "w"), indent=2)
print(json.dumps(summary, indent=2))
print(f"\nwrote {u} status-denial flags -> data/derived/m0a_status_denial_flags.parquet")
