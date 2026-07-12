"""M0a spike: one FY shard (FY2022 DoD SR3+ST3) coded pull + USAspending join validation.

Validates (1) the coded ATOM pull mechanics/parse at shard scale, and (2) that coded FPDS records
are findable in the USAspending recipient universe (so the uncoded = set-difference is computable).
Self-contained; caches pages under data/raw/fpds/m0a_spike_fy2022/. Read-only public feeds."""
import re, os, time, json, urllib.request, urllib.parse
from math import ceil

REPO = "/Users/hollomancer/projects/sbir-analytics"
CACHE = f"{REPO}/data/raw/fpds/m0a_spike_fy2022"
os.makedirs(CACHE, exist_ok=True)
UA = "sbir-analytics-research/1.0"
FEED = "https://www.fpds.gov/ezsearch/FEEDS/ATOM?FEEDNAME=PUBLIC"
WINDOW = "SIGNED_DATE:[2021/10/01,2022/09/30]"  # FY2022

def fetch(q, start, tag):
    f = f"{CACHE}/{tag}_{start:05d}.xml"
    if os.path.exists(f):
        return open(f, encoding="utf-8", errors="replace").read()
    url = f"{FEED}&q={urllib.parse.quote(q)}&start={start}"
    for a in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode("utf-8", "replace")
            open(f, "w", encoding="utf-8").write(body); return body
        except Exception as e:
            if a == 4: print("  fetch fail", start, e); return ""
            time.sleep(3 * (a + 1))
    return ""

def leaf(block, tag):
    m = re.search(rf"<ns\d+:{tag}\b[^>]*>([^<]*)</ns\d+:{tag}>", block); return m.group(1).strip() if m else ""

def parse(entry):
    ac = re.search(r"<ns\d+:awardContractID\b.*?</ns\d+:awardContractID>", entry, re.S)
    iv = re.search(r"<ns\d+:referencedIDVID\b.*?</ns\d+:referencedIDVID>", entry, re.S)
    acb, ivb = (ac.group(0) if ac else ""), (iv.group(0) if iv else "")
    return {
        "order_piid": leaf(acb, "PIID"), "order_agency": leaf(acb, "agencyID"),
        "idv_piid": leaf(ivb, "PIID"), "idv_agency": leaf(ivb, "agencyID"),
        "research": leaf(entry, "research"), "uei": leaf(entry, "UEI"),
        "vendor": leaf(entry, "vendorName"), "signed": leaf(entry, "signedDate"),
        "desc": leaf(entry, "descriptionOfContractRequirement"),
    }

records, requests = [], 0
t0 = time.time()
for code in ("SR3", "ST3"):
    q = f"RESEARCH:{code} DEPARTMENT_ID:9700 {WINDOW}"
    start = 0
    while True:
        xml = fetch(q, start, code); requests += 1
        if not xml: break
        ents = re.findall(r"<entry>.*?</entry>", xml, re.S)
        if not ents: break
        for e in ents:
            r = parse(e); r["code"] = code; records.append(r)
        # stop at last page
        last = re.search(r'rel="last"[^>]*start=(\d+)|start=(\d+)[^>]*rel="last"', xml)
        lastn = int(next(g for g in last.groups() if g)) if last else None
        if lastn is None or start >= lastn: break
        start += 10
        if start % 500 == 0: print(f"  [{code}] {start} rows, {time.time()-t0:.0f}s")
        time.sleep(0.25)

print(f"\n[{time.time()-t0:.0f}s] coded pull: {len(records)} records in {requests} requests")
def key(r): return "|".join([r["order_piid"], r["order_agency"], r["idv_piid"], r["idv_agency"]])
compound = {key(r) for r in records}
ueis = {r["uei"] for r in records if r["uei"]}
print(f"  distinct compound keys: {len(compound)}  distinct UEIs: {len(ueis)}  "
      f"research dist: SR3={sum(r['code']=='SR3' for r in records)} ST3={sum(r['code']=='ST3' for r in records)}")
print(f"  est full pull (10 FY x this): ~{requests*10} requests")
json.dump(records, open(f"{CACHE}/parsed.json", "w"))

# ---- USAspending join validation: sample coded records, find them in USAspending by UEI+FY ----
print("\n=== USAspending join validation (sample 25 coded records) ===")
sample = [r for r in records if r["uei"] and r["order_piid"]][:25]
def usa_awards(uei):
    body = {"filters": {"award_type_codes": ["A","B","C","D"],
        "time_period": [{"start_date": "2021-10-01", "end_date": "2022-09-30"}],
        "recipient_search_text": [uei]}, "fields": ["Award ID", "Description"], "limit": 100}
    req = urllib.request.Request("https://api.usaspending.gov/api/v2/search/spending_by_award/",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as rr:
            return [x.get("Award ID") for x in json.loads(rr.read()).get("results", [])]
    except Exception:
        return None
matched = usa_seen = 0
for r in sample:
    ids = usa_awards(r["uei"])
    if ids is None: continue
    usa_seen += 1
    if r["order_piid"] in ids or any(r["order_piid"] in str(i) for i in ids):
        matched += 1
    time.sleep(0.3)
print(f"  sampled {len(sample)} coded records; USAspending returned awards for {usa_seen}; "
      f"order-PIID matched in {matched}/{usa_seen}")
print("  -> join key: FPDS order_piid == USAspending 'Award ID' (contract PIID); parent via 'Parent Award ID'")
