"""NASA Phase III undercount (v1.1) — mirror of the DoD analysis, agency = NASA (dept 8000).
Coded set from m0a_coded_pull_nasa.py; pulls the NASA 'SBIR PHASE III' description set and joins."""
import json, time, urllib.request, re
import pandas as pd
REPO="/Users/hollomancer/projects/sbir-analytics"; UA="sbir-analytics-research/1.0"
URL="https://api.usaspending.gov/api/v2/search/spending_by_award/"
def pull():
    rows=[]
    for types in (["A","B","C","D"],["IDV_A","IDV_B","IDV_C","IDV_D","IDV_E"]):
        p=1
        while True:
            body={"filters":{"award_type_codes":types,"time_period":[{"start_date":"2015-10-01","end_date":"2025-09-30"}],
                "description":"SBIR PHASE III","agencies":[{"type":"awarding","tier":"toptier","name":"National Aeronautics and Space Administration"}]},
                "fields":["Award ID","Description","Recipient Name","Award Amount","Awarding Sub Agency","Action Date"],"limit":100,"page":p}
            req=urllib.request.Request(URL,data=json.dumps(body).encode(),headers={"Content-Type":"application/json","User-Agent":UA})
            d=json.loads(urllib.request.urlopen(req,timeout=50).read()); rows.extend(d.get("results",[]))
            if not d.get("page_metadata",{}).get("hasNext"): break
            p+=1; time.sleep(0.25)
    return pd.DataFrame(rows)
desc=pull(); desc["gen_id"]=desc["generated_internal_id"].astype(str).str.upper()
desc.to_parquet(f"{REPO}/data/derived/m0a_desc_phase3_nasa.parquet")
coded=pd.read_parquet(f"{REPO}/data/derived/m0a_coded_nasa.parquet")
def norm(x): return str(x).strip().upper() if x is not None else ""
def gk(r): return f"CONT_AWD_{norm(r['order_piid'])}_{norm(r['order_agency']) or '-NONE-'}_{norm(r['idv_piid']) or '-NONE-'}_{norm(r['idv_agency']) or '-NONE-'}"
ck=set(coded.apply(gk,axis=1)); desc["coded"]=desc["gen_id"].isin(ck)
n=len(desc); u=int((~desc["coded"]).sum()); amt=pd.to_numeric(desc.loc[~desc["coded"],"Award Amount"],errors="coerce").sum()
flags=desc.loc[~desc["coded"]].copy(); flags["disposition"]=None
flags.to_parquet(f"{REPO}/data/derived/m0a_status_denial_flags_nasa.parquet")
print(f"NASA: coded universe {len(coded)} awards / {coded['uei'].nunique()} firms; described {n}; "
      f"uncoded {u} ({100*u/n:.1f}%, ${amt/1e6:.1f}M)")
