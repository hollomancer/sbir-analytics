"""Positive control: does RICH abstract <-> RICH solicitation text discriminate true SBIR
transitions? For known coded Phase III (true firm known), pull the solicitation text and test
whether the true awardee's Phase I/II abstract outranks random firms' abstracts against that
solicitation. Baseline = same test using the terse FPDS contract description instead of the
solicitation. TF-IDF cosine (lexical floor; embeddings only do better)."""
import glob, json, re, time, urllib.request, urllib.parse
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

REPO = "/Users/hollomancer/projects/sbir-analytics"
RNG = np.random.default_rng(20260715)

# firm (UEI) -> concatenated Phase I/II abstracts
a = pd.read_csv(f"{REPO}/data/raw/sbir/award_data.csv", dtype=str, keep_default_na=False)
a = a[a["UEI"].str.len() > 5]
firm_abs = a.groupby("UEI")["Abstract"].apply(lambda s: " ".join(s)[:8000]).to_dict()

# coded Phase III (SR3) with solicitationID + UEI, from the local FPDS pull
def _leaf(b, t):
    m = re.search(rf"<ns\d+:{t}\b[^>]*>([^<]*)</ns\d+:{t}>", b); return m.group(1).strip() if m else ""
coded = []
for f in glob.glob(f"{REPO}/data/raw/fpds/m0a_coded/SR3_*.xml"):
    x = open(f, encoding="utf-8", errors="replace").read()
    for e in re.findall(r"<entry>.*?</entry>", x, re.S):
        sol, uei = _leaf(e, "solicitationID"), _leaf(e, "UEI")
        if sol and uei:
            coded.append({"sol": sol, "uei": uei, "desc": _leaf(e, "descriptionOfContractRequirement")})
# keep coded Phase III whose firm we have an abstract for; one record per solicitation
seen, recs = set(), []
for r in coded:
    if r["uei"] in firm_abs and r["sol"] not in seen and len(firm_abs[r["uei"]]) > 200:
        seen.add(r["sol"]); recs.append(r)
print(f"eligible solicitations (firm abstract available): {len(recs)}")

SAMPLE = 70
sample = [recs[i] for i in RNG.choice(len(recs), size=min(SAMPLE, len(recs)), replace=False)]

def sam_text(solnum):
    url = f"https://sam.gov/api/prod/sgs/v1/search?index=opp&q={urllib.parse.quote(solnum)}&size=3&page=0"
    for k in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0", "Accept": "*/*"})
            d = json.loads(urllib.request.urlopen(req, timeout=30).read())
            res = d.get("_embedded", {}).get("results", []) or []
            best = None
            for rec in res:
                cs = re.sub(r"[^A-Z0-9]", "", (rec.get("solicitationNumber") or "").upper())
                if cs == re.sub(r"[^A-Z0-9]", "", solnum.upper()): best = rec; break
            best = best or (res[0] if res else None)
            if not best: return ""
            txt = " ".join(x.get("content", "") or "" for x in best.get("descriptions", []))
            return re.sub(r"<[^>]+>|&nbsp;", " ", (best.get("title", "") or "") + " " + txt)
        except Exception:
            time.sleep(2 * (k + 1))
    return "__ERR__"

# pull solicitation text
for i, r in enumerate(sample):
    r["soltext"] = sam_text(r["sol"]); time.sleep(0.3)
    if (i + 1) % 20 == 0: print(f"  pulled {i+1}/{len(sample)}", flush=True)
got = [r for r in sample if r["soltext"] not in ("", "__ERR__") and len(r["soltext"]) > 80]
print(f"solicitations with retrievable rich text (>80ch): {len(got)}/{len(sample)} "
      f"({100*len(got)/len(sample):.0f}%)  median {int(np.median([len(r['soltext']) for r in got]))} chars")

# --- discrimination test: true firm abstract vs N random firms, per target text ---
all_ueis = list(firm_abs.keys())
def auc_for(target_key):
    wins = comps = 0
    for r in got:
        tgt = r[target_key]
        if not tgt or len(tgt) < 40: continue
        negs = [u for u in RNG.choice(all_ueis, size=25, replace=False) if u != r["uei"]][:20]
        docs = [firm_abs[r["uei"]]] + [firm_abs[u] for u in negs] + [tgt]
        try:
            X = TfidfVectorizer(stop_words="english", min_df=1, ngram_range=(1, 2)).fit_transform(docs)
        except ValueError:
            continue
        sims = cosine_similarity(X[-1], X[:-1]).ravel()  # target vs [true, negs...]
        true_s, neg_s = sims[0], sims[1:]
        wins += int((true_s > neg_s).sum()); comps += len(neg_s)
    return wins / comps if comps else float("nan"), comps

auc_sol, n_sol = auc_for("soltext")
auc_desc, n_desc = auc_for("desc")
print("\n=== DISCRIMINATION (true awardee abstract vs 20 random firms, per target) ===")
print(f"  RICH  target = solicitation text:  AUC {auc_sol:.3f}  ({n_sol} comparisons)")
print(f"  TERSE target = FPDS description:    AUC {auc_desc:.3f}  ({n_desc} comparisons)")
print(f"  (0.50 = chance; higher = true firm's abstract ranks above random firms)")
