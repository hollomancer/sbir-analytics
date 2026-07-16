"""Measurement 2 — same-firm contrastive: the OPERATIONAL test. Among a single firm's DoD
contracts, does cosine(firm abstract, contract description) rank the firm's TRUE Phase III
transitions (coded SR3/ST3) above its routine contracts? This is the hard task (all of a firm's
contracts are in its field). Ground truth = coded keys; targets are the terse FPDS/USAspending
descriptions (the only text reliably available retrospectively). Per-firm AUC, averaged."""
import glob, json
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

REPO = "/Users/hollomancer/projects/sbir-analytics"
UNI = f"{REPO}/data/raw/usaspending/recipient_universe"

# firm abstracts
a = pd.read_csv(f"{REPO}/data/raw/sbir/award_data.csv", dtype=str, keep_default_na=False)
a = a[a["UEI"].str.len() > 5]
firm_abs = a.groupby("UEI")["Abstract"].apply(lambda s: " ".join(s)[:8000]).to_dict()

# coded Phase III compound keys (ground-truth positives)
def norm(x): return str(x).strip().upper() if x is not None else ""
c = pd.read_parquet(f"{REPO}/data/derived/m0a_coded_dod.parquet")
coded_keys = set(c.apply(lambda r: f"CONT_AWD_{norm(r['order_piid'])}_{norm(r['order_agency']) or '-NONE-'}_"
                                   f"{norm(r['idv_piid']) or '-NONE-'}_{norm(r['idv_agency']) or '-NONE-'}", axis=1))

# per-firm contrastive AUC
aucs, npos_tot, firms_used = [], 0, 0
for f in glob.glob(f"{UNI}/*.json"):
    uei = f.split("/")[-1][:-5]
    if uei not in firm_abs or len(firm_abs[uei]) < 200:
        continue
    try:
        recs = json.load(open(f))
    except Exception:
        continue
    df = pd.DataFrame(recs)
    if df.empty or "generated_internal_id" not in df:
        continue
    df["gid"] = df["generated_internal_id"].astype(str).str.upper()
    df["desc"] = df.get("Description", "").fillna("").astype(str)
    df = df[df["desc"].str.len() > 10].drop_duplicates("gid")
    df["pos"] = df["gid"].isin(coded_keys)
    npos, nneg = int(df["pos"].sum()), int((~df["pos"]).sum())
    if npos < 1 or nneg < 3:
        continue
    docs = [firm_abs[uei]] + df["desc"].tolist()
    try:
        X = TfidfVectorizer(stop_words="english", min_df=1).fit_transform(docs)
    except ValueError:
        continue
    sims = cosine_similarity(X[0], X[1:]).ravel()
    pos_s, neg_s = sims[df["pos"].values], sims[~df["pos"].values]
    # within-firm AUC = P(a random true Phase III scores above a random routine contract)
    wins = sum((ps > neg_s).sum() for ps in pos_s)
    aucs.append(wins / (len(pos_s) * len(neg_s)))
    npos_tot += npos; firms_used += 1

aucs = np.array(aucs)
print(f"firms with >=1 coded Phase III and >=3 routine contracts: {firms_used}  (total {npos_tot} positives)")
print(f"same-firm contrastive AUC (abstract vs terse desc): mean {aucs.mean():.3f}  median {np.median(aucs):.3f}")
print(f"  firms where true Phase III ranks strictly better than chance (>0.5): {100*(aucs>0.5).mean():.0f}%")
print(f"  firms with AUC>=0.7: {100*(aucs>=0.7).mean():.0f}%   AUC<=0.3: {100*(aucs<=0.3).mean():.0f}%")
print(f"  (0.50 = the abstract can't tell the firm's Phase III from its routine work)")
