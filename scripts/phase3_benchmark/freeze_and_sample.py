"""Freeze the confirmed Phase III undercount flags (168) and draw a stratified 50-case validation
sample. Re-pulls the DoD/NASA description sets fresh (full fields) for consistent firm+$ data,
recomputes uncoded flags against the coded sets, adds the DoD full-universe text-scan flags."""
import hashlib, json, time, urllib.request
import numpy as np
import pandas as pd

REPO = "/Users/hollomancer/projects/sbir-analytics"
RNG = np.random.default_rng(20260715)
URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"; UA = "sbir-analytics-research/1.0"
FIELDS = ["Award ID", "Description", "Recipient Name", "Award Amount", "Awarding Sub Agency", "Action Date"]

def pull_desc(agency):
    rows = []
    for types in (["A", "B", "C", "D"], ["IDV_A", "IDV_B", "IDV_C", "IDV_D", "IDV_E"]):
        p = 1
        while True:
            body = {"filters": {"award_type_codes": types,
                "time_period": [{"start_date": "2015-10-01", "end_date": "2025-09-30"}],
                "description": "SBIR PHASE III",
                "agencies": [{"type": "awarding", "tier": "toptier", "name": agency}]},
                "fields": FIELDS, "limit": 100, "page": p}
            req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "User-Agent": UA})
            d = json.loads(urllib.request.urlopen(req, timeout=50).read()); rows.extend(d.get("results", []))
            if not d.get("page_metadata", {}).get("hasNext"): break
            p += 1; time.sleep(0.25)
    df = pd.DataFrame(rows); df["gen_id"] = df["generated_internal_id"].astype(str).str.upper()
    return df

def norm(x): return str(x).strip().upper() if x is not None else ""
def coded_keys(path):
    c = pd.read_parquet(f"{REPO}/data/derived/{path}")
    return set(c.apply(lambda r: f"CONT_AWD_{norm(r['order_piid'])}_{norm(r['order_agency']) or '-NONE-'}_"
                                 f"{norm(r['idv_piid']) or '-NONE-'}_{norm(r['idv_agency']) or '-NONE-'}", axis=1))

def flags_for(agency, coded_path, layer):
    d = pull_desc(agency); ck = coded_keys(coded_path)
    f = d[~d["gen_id"].isin(ck)].copy()
    return pd.DataFrame({"gen_id": f["gen_id"], "award_id": f["Award ID"], "firm": f["Recipient Name"],
                         "amount_usd": pd.to_numeric(f["Award Amount"], errors="coerce"),
                         "sub_agency": f["Awarding Sub Agency"], "description": f["Description"],
                         "action_date": f["Action Date"], "agency": agency, "layer": layer})

dod = flags_for("Department of Defense", "m0a_coded_dod.parquet", "dod_exact_phrase")
nasa = flags_for("National Aeronautics and Space Administration", "m0a_coded_nasa.parquet", "nasa_exact_phrase")
# DoD full-universe text-scan flags (11) — already has gen_id + fields
ts = pd.read_parquet(f"{REPO}/data/derived/m0a_dark_discoverable_flags.parquet")
ts = pd.DataFrame({"gen_id": ts["gen_id"].astype(str).str.upper(), "award_id": ts["Award ID"],
                   "firm": ts["Recipient Name"], "amount_usd": pd.to_numeric(ts["Award Amount"], errors="coerce"),
                   "sub_agency": ts["Awarding Sub Agency"], "description": ts["Description"],
                   "action_date": ts["Action Date"], "agency": "DoD", "layer": "dod_text_scan"})

gr = pd.read_parquet(f"{REPO}/data/derived/m0a_grey_flags.parquet")
gr = pd.DataFrame({"gen_id": gr["gen_id"].astype(str).str.upper(), "award_id": gr["award_id"],
                   "firm": gr["firm"], "amount_usd": pd.to_numeric(gr["amount_usd"], errors="coerce"),
                   "sub_agency": gr["sub_agency"], "description": gr["description"],
                   "action_date": gr["action_date"], "agency": "DoD", "layer": "dod_grey_variant"})
flags = pd.concat([dod, nasa, ts, gr], ignore_index=True).drop_duplicates("gen_id").reset_index(drop=True)
flags["agency"] = flags["agency"].replace({"Department of Defense": "DoD", "National Aeronautics and Space Administration": "NASA"})
flags["flag_id"] = flags["gen_id"].map(lambda g: "P3F-" + hashlib.sha1(g.encode()).hexdigest()[:10])
flags["usaspending_url"] = "https://www.usaspending.gov/award/" + flags["gen_id"]
flags["disposition"] = pd.NA; flags["reviewer"] = pd.NA; flags["notes"] = pd.NA

frame_cols = ["flag_id", "agency", "sub_agency", "firm", "award_id", "gen_id", "amount_usd",
              "layer", "action_date", "description", "usaspending_url", "disposition"]
frozen = flags[frame_cols].sort_values(["agency", "amount_usd"], ascending=[True, False])
frozen.to_csv(f"{REPO}/data/derived/phase3_undercount_flags_frozen.csv", index=False)
fh = hashlib.sha1("".join(sorted(frozen["gen_id"])).encode()).hexdigest()[:12]
print(f"FROZEN FRAME: {len(frozen)} flags  frame_hash={fh}  ${frozen['amount_usd'].sum()/1e6:.1f}M")
print(frozen.groupby(["agency", "layer"]).size().to_string())

# --- stratified 50-case sample ---
def band(a): return "unknown" if pd.isna(a) else ("A_>=5M" if a >= 5e6 else ("B_1-5M" if a >= 1e6 else "C_<1M"))
flags["band"] = flags["amount_usd"].map(band)
alloc = {"NASA": min(8, (flags["agency"] == "NASA").sum())}
alloc["DoD"] = 50 - alloc["NASA"]
picks = []
for ag, n_ag in alloc.items():
    sub = flags[flags["agency"] == ag]
    for b, cnt in sub["band"].value_counts().items():
        k = max(1, round(n_ag * cnt / len(sub))); cand = sub[sub["band"] == b]
        take = cand.sample(min(k, len(cand)), random_state=int(RNG.integers(1e9)))
        picks.append(take.assign(_stratum=f"{ag}|{b}", _design_weight=round(len(cand) / min(k, len(cand)), 2)))
sample = pd.concat(picks).drop_duplicates("flag_id")
if len(sample) > 50: sample = sample.sort_values("amount_usd", ascending=False).head(50)
elif len(sample) < 50:
    extra = flags[~flags["flag_id"].isin(sample["flag_id"])].sample(50 - len(sample), random_state=7)
    sample = pd.concat([sample, extra.assign(_stratum="fill", _design_weight=1.0)])
sheet = sample[["flag_id", "agency", "sub_agency", "_stratum", "firm", "award_id", "amount_usd",
                "description", "usaspending_url", "_design_weight", "disposition", "reviewer", "notes"]]
sheet = sheet.sort_values(["agency", "amount_usd"], ascending=[True, False])
sheet.to_csv(f"{REPO}/data/derived/phase3_undercount_validation_sample_50.csv", index=False)
print(f"\nSAMPLE: {len(sheet)} cases; ${sample['amount_usd'].sum()/1e6:.1f}M covered")
print(sheet.groupby(["agency", "_stratum"]).size().to_string())
