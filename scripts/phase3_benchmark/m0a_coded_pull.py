"""M0a full coded pull: DoD SR3+ST3 Phase III records, FY2016-2025, from FPDS ATOM.

Sharded by fiscal year (SIGNED_DATE), cached under data/raw/fpds/m0a_coded/. Dedups to award grain
via the compound key. Output: data/derived/m0a_coded_dod.parquet (the coded Phase III universe)."""
import re, os, time, json, urllib.request, urllib.parse
import pandas as pd

REPO = "/Users/hollomancer/projects/sbir-analytics"
CACHE = f"{REPO}/data/raw/fpds/m0a_coded"; os.makedirs(CACHE, exist_ok=True)
UA = "sbir-analytics-research/1.0"
FEED = "https://www.fpds.gov/ezsearch/FEEDS/ATOM?FEEDNAME=PUBLIC"
FYS = list(range(2016, 2026))  # FY2016..FY2025

def fetch(q, start, tag):
    f = f"{CACHE}/{tag}_{start:06d}.xml"
    if os.path.exists(f):
        return open(f, encoding="utf-8", errors="replace").read()
    url = f"{FEED}&q={urllib.parse.quote(q)}&start={start}"
    for a in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode("utf-8", "replace")
            open(f, "w", encoding="utf-8").write(body); return body
        except Exception as e:
            if a == 5: print("  fail", tag, start, e); return ""
            time.sleep(3 * (a + 1))
    return ""

def leaf(b, t):
    m = re.search(rf"<ns\d+:{t}\b[^>]*>([^<]*)</ns\d+:{t}>", b); return m.group(1).strip() if m else ""
def attr(b, t, a):
    m = re.search(rf'<ns\d+:{t}\b[^>]*\b{a}="([^"]*)"', b); return m.group(1).strip() if m else ""

def parse(e):
    ac = re.search(r"<ns\d+:awardContractID\b.*?</ns\d+:awardContractID>", e, re.S)
    iv = re.search(r"<ns\d+:referencedIDVID\b.*?</ns\d+:referencedIDVID>", e, re.S)
    acb, ivb = (ac.group(0) if ac else ""), (iv.group(0) if iv else "")
    return {
        "order_piid": leaf(acb, "PIID"), "order_agency": leaf(acb, "agencyID"),
        "idv_piid": leaf(ivb, "PIID"), "idv_agency": leaf(ivb, "agencyID"),
        "mod": leaf(acb, "modNumber"),
        "research": leaf(e, "research"), "uei": leaf(e, "UEI"), "vendor": leaf(e, "vendorName"),
        "signed": leaf(e, "signedDate"),
        "sub_agency": attr(e, "contractingOfficeAgencyID", "name"),
        "office": leaf(e, "contractingOfficeID"),
        "psc": leaf(e, "productOrServiceCode"), "naics": leaf(e, "principalNAICSCode"),
        "desc": leaf(e, "descriptionOfContractRequirement"),
    }

t0 = time.time(); rows = []; total_req = 0
for code in ("SR3", "ST3"):
    for fy in FYS:
        q = f"RESEARCH:{code} DEPARTMENT_ID:9700 SIGNED_DATE:[{fy-1}/10/01,{fy}/09/30]"
        start = 0
        while True:
            xml = fetch(q, start, f"{code}_{fy}"); total_req += 1
            if not xml: break
            ents = re.findall(r"<entry>.*?</entry>", xml, re.S)
            if not ents: break
            for e in ents:
                r = parse(e); r["code"] = code; r["fy"] = fy; rows.append(r)
            last = re.search(r'rel="last"[^>]*start=(\d+)|start=(\d+)[^>]*rel="last"', xml)
            lastn = int(next(g for g in last.groups() if g)) if last else None
            if lastn is None or start >= lastn: break
            start += 10
            time.sleep(0.25)
        print(f"[{time.time()-t0:.0f}s] {code} FY{fy}: cumulative {len(rows)} rows, {total_req} req")

df = pd.DataFrame(rows)
df["award_key"] = df[["order_piid","order_agency","idv_piid","idv_agency"]].fillna("").agg("|".join, axis=1)
# award grain: one row per compound key (keep the latest signed date)
df["_d"] = pd.to_datetime(df["signed"], errors="coerce")
df_award = df.sort_values("_d").drop_duplicates("award_key", keep="last").drop(columns="_d")
df.drop(columns="_d").to_parquet(f"{REPO}/data/derived/m0a_coded_dod_txn.parquet")
df_award.to_parquet(f"{REPO}/data/derived/m0a_coded_dod.parquet")
print(f"\nDONE in {time.time()-t0:.0f}s, {total_req} requests")
print(f"  coded transactions: {len(df)}  -> distinct coded AWARDS (compound key): {len(df_award)}")
print(f"  distinct firms (UEI): {df_award['uei'].nunique()}")
print("  coded awards by sub-agency:")
print(df_award["sub_agency"].value_counts().head(8).to_string())
print("  by FY:"); print(df_award["fy"].value_counts().sort_index().to_string())
