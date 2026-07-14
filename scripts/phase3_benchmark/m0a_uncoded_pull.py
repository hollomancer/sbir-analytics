"""Pull the DoD 'SBIR PHASE III' description-matched contract set (~962) with compound keys.

This is the independent Phase-III ground-truth for the undercount measurement: of contracts that
openly describe themselves as SBIR Phase III, how many carry the SR3/ST3 code? Joins to the coded
set on USAspending generated_internal_id = CONT_AWD_{piid}_{agency}_{parent}_{parent_agency}."""
import json, time, urllib.request
import pandas as pd

REPO = "/Users/hollomancer/projects/sbir-analytics"
URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
UA = "sbir-analytics-research/1.0"
FIELDS = ["Award ID", "Description", "Awarding Agency", "Awarding Sub Agency",
          "Contract Award Type", "Action Date", "Start Date",
          "Recipient Name", "Award Amount"]  # firm + $ for the enriched review queue

def page(types, p):
    body = {"filters": {"award_type_codes": types,
        "time_period": [{"start_date": "2015-10-01", "end_date": "2025-09-30"}],
        "description": "SBIR PHASE III",
        "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of Defense"}]},
        "fields": FIELDS, "limit": 100, "page": p}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=50) as r:
        return json.loads(r.read())

rows = []
for types in (["A", "B", "C", "D"], ["IDV_A", "IDV_B", "IDV_C", "IDV_D", "IDV_E"]):
    p = 1
    while True:
        d = page(types, p)
        res = d.get("results", [])
        rows.extend(res)
        if not d.get("page_metadata", {}).get("hasNext"):
            break
        p += 1; time.sleep(0.3)
df = pd.DataFrame(rows)
# USAspending compound key is generated_internal_id: CONT_AWD_{piid}_{agency}_{parent}_{parent_agency}
df["gen_id"] = df["generated_internal_id"].astype(str).str.upper()
df.to_parquet(f"{REPO}/data/derived/m0a_desc_phase3_dod.parquet")
print(f"pulled {len(df)} DoD 'SBIR PHASE III' description records")
print("  award types:", df["Contract Award Type"].value_counts().to_dict() if "Contract Award Type" in df else "n/a")
print("  sample gen_id:", df["gen_id"].iloc[0] if len(df) else "-")
print("  distinct gen_id:", df["gen_id"].nunique())
