"""Dark-layer pull: DoD contracts to the 8,090 SBIR recipient firms, FY2016-2025, from USAspending.

Per-firm spending_by_award by recipient UEI; one cache file per UEI (resumable). The recipient
universe from which dark (uncoded, non-self-describing) Phase III candidates are identified."""
import json, os, time, urllib.request

SCR = "/private/tmp/claude-501/-Users-hollomancer-projects-sbir-analytics/e3bbeac4-dccf-4d5b-bb43-a9565ac6d983/scratchpad"
CACHE = "/Users/hollomancer/projects/sbir-analytics/data/raw/usaspending/recipient_universe"
os.makedirs(CACHE, exist_ok=True)
URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
UA = "sbir-analytics-research/1.0"
FIELDS = ["Award ID", "Description", "Recipient Name", "Award Amount",
          "Awarding Sub Agency", "Action Date", "Contract Award Type"]

firms = json.load(open(f"{SCR}/m0a_recipient_firms.json"))
ueis = sorted({u for f in firms["firms"] for u in f["ueis"]})
print(f"recipient UEIs to pull: {len(ueis)}", flush=True)

def firm_pull(uei):
    rows, p = [], 1
    while True:
        body = {"filters": {"award_type_codes": ["A", "B", "C", "D"],
            "time_period": [{"start_date": "2015-10-01", "end_date": "2025-09-30"}],
            "recipient_search_text": [uei],
            "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of Defense"}]},
            "fields": FIELDS, "limit": 100, "page": p}
        data = json.dumps(body).encode()
        for a in range(6):
            try:
                req = urllib.request.Request(URL, data=data,
                    headers={"Content-Type": "application/json", "User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    d = json.loads(r.read())
                break
            except Exception:
                if a == 5:
                    return None  # signal failure; leave uncached to retry next run
                time.sleep(3 * (a + 1))
        rows.extend(d.get("results", []))
        if not d.get("page_metadata", {}).get("hasNext"):
            break
        p += 1
        time.sleep(0.15)
    return rows

t0 = time.time(); done = 0; total_rows = 0; req_firms = 0
for i, uei in enumerate(ueis):
    f = f"{CACHE}/{uei}.json"
    if os.path.exists(f):
        done += 1
        continue
    rows = firm_pull(uei)
    if rows is None:
        continue  # transient failure; retry on a later run
    json.dump(rows, open(f, "w"))
    done += 1; req_firms += 1; total_rows += len(rows)
    time.sleep(0.2)
    if req_firms % 100 == 0:
        el = time.time() - t0
        rate = req_firms / el if el else 0
        eta = (len(ueis) - done) / rate / 60 if rate else 0
        print(f"[{el/60:.0f}m] {done}/{len(ueis)} firms ({req_firms} pulled this run), "
              f"{total_rows} rows, ~{eta:.0f}m ETA", flush=True)

print(f"\nDONE: {done}/{len(ueis)} firms cached, {total_rows} rows pulled this run, "
      f"{time.time()-t0:.0f}s", flush=True)
