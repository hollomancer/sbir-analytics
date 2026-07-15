"""Dark-layer analysis: partition the recipient universe (coded / described / neither), then scan
the 'neither' pool's descriptions for broader Phase III indicators the exact-phrase API filter
missed. Converts part of the modeled-dark into discoverable flags; the residual (no text signal)
stays a modeled estimate."""
import json, os, glob, re
import pandas as pd

REPO = "/Users/hollomancer/projects/sbir-analytics"
CACHE = f"{REPO}/data/raw/usaspending/recipient_universe"

# --- load the pulled recipient universe ---
rows = []
for f in glob.glob(f"{CACHE}/*.json"):
    try:
        rows.extend(json.load(open(f)))
    except Exception:
        pass
uni = pd.DataFrame(rows)
uni["gen_id"] = uni["generated_internal_id"].astype(str).str.upper()
uni = uni.drop_duplicates("gen_id")
print(f"recipient universe: {len(uni)} distinct DoD contracts to SBIR firms (FY2016-2025)")

# --- coded + exact-described sets ---
coded = pd.read_parquet(f"{REPO}/data/derived/m0a_coded_dod.parquet")
def norm(x): return str(x).strip().upper() if x is not None else ""
def gk(r): return f"CONT_AWD_{norm(r['order_piid'])}_{norm(r['order_agency']) or '-NONE-'}_{norm(r['idv_piid']) or '-NONE-'}_{norm(r['idv_agency']) or '-NONE-'}"
coded_keys = set(coded.apply(gk, axis=1))
desc = pd.read_parquet(f"{REPO}/data/derived/m0a_desc_phase3_dod.parquet")
desc_keys = set(desc["generated_internal_id"].astype(str).str.upper())

uni["coded"] = uni["gen_id"].isin(coded_keys)
uni["described"] = uni["gen_id"].isin(desc_keys)
neither = uni[~uni["coded"] & ~uni["described"]].copy()
print(f"  coded: {uni['coded'].sum()}  exact-described: {uni['described'].sum()}  "
      f"NEITHER (candidate pool): {len(neither)}")

# --- broad Phase III indicators in the 'neither' descriptions (what the exact filter missed) ---
D = neither["Description"].fillna("").str.upper()
pat_strong = re.compile(r"\bSBIR\b.{0,40}\bPHASE\s*(?:III|3)\b|\bPHASE\s*(?:III|3)\b.{0,40}\bSBIR\b|\bSTTR\b.{0,40}\bPHASE\s*(?:III|3)\b")
pat_medium = re.compile(r"\bSBIR\b|\bSTTR\b|SMALL BUSINESS INNOVATION|SMALL BUSINESS TECHNOLOGY")
neither["ph3_strong"] = D.str.contains(pat_strong)
neither["sbir_any"]  = D.str.contains(pat_medium)
newflags = neither[neither["ph3_strong"]]
amt = pd.to_numeric(newflags["Award Amount"], errors="coerce")
print(f"\n=== discoverable-beyond-exact-phrase ('neither' with SBIR+PhaseIII text) ===")
print(f"  new dark->discoverable flags: {len(newflags)}  (${amt.sum()/1e6:.1f}M)")
print(f"  'neither' mentioning SBIR/STTR at all: {neither['sbir_any'].sum()}")
print(f"  residual TRULY dark (no SBIR/PhaseIII text): {len(neither) - int(neither['sbir_any'].sum())} "
      f"(model-only; not enumerable)")

# --- combined visible+discoverable undercount ---
print(f"\n=== undercount rollup ===")
print(f"  visible (exact 'SBIR PHASE III', uncoded): 141")
print(f"  + discoverable (broad text in universe, uncoded): {len(newflags)}")
print(f"  = confirmed uncoded Phase III (text-evidenced): {141 + len(newflags)}")
print(f"  modeled truly-dark (no text): ~1,000 (floor, from stratified extrapolation)")

out = neither[["Award ID","gen_id","Recipient Name","Award Amount","Awarding Sub Agency",
               "Action Date","Description","ph3_strong","sbir_any"]]
out.to_parquet(f"{REPO}/data/derived/m0a_dark_candidate_pool.parquet")
newflags.assign(disposition=None).to_parquet(f"{REPO}/data/derived/m0a_dark_discoverable_flags.parquet")
print(f"\nwrote candidate pool ({len(out)}) + discoverable flags ({len(newflags)}) to data/derived/")
