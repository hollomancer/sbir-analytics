"""Embedding separability + realistic-pool precision@k for the Phase III match benchmark.

(1) P1-vs-N1 ROC-AUC with ModernBERT-Embed cosine, N1 = TRUE same-contracting-office negatives.
(2) Retrieval precision@k: for each Phase II query, rank the SR3 descriptions in the SAME
    contracting office and measure whether the query firm's own Phase III ranks at the top.

POOL LIMITATION (documented, not hidden): the candidate pool is only SR3-*coded* records in the
office, not the full contract population (M0a not yet ingested). The real pool includes uncoded
and non-SBIR contracts in the office — far larger and harder — so precision@k here is an
OPTIMISTIC upper bound on realistic retrieval.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

REPO = Path(__file__).resolve().parents[2]
RNG = np.random.default_rng(20260708)
MODEL = "nomic-ai/modernbert-embed-base"
DOC = "search_document: "


def auc_mw(pos: np.ndarray, neg: np.ndarray) -> float:
    allv = np.concatenate([pos, neg])
    order = allv.argsort()
    ranks = np.empty(len(allv), float)
    ranks[order] = np.arange(1, len(allv) + 1)
    _, inv, counts = np.unique(allv, return_inverse=True, return_counts=True)
    sums = np.zeros(len(counts)); np.add.at(sums, inv, ranks)
    ranks = (sums / counts)[inv]
    return (ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def boot(pos, neg, n=2000):
    b = auc_mw(pos, neg)
    xs = [auc_mw(RNG.choice(pos, len(pos), True), RNG.choice(neg, len(neg), True)) for _ in range(n)]
    return (b, *np.percentile(xs, [2.5, 97.5]))


def main() -> None:
    pairs = pd.read_parquet(REPO / "data/derived/phase3_match_benchmark_pairs.parquet")
    model = SentenceTransformer(MODEL)

    def embed(texts):
        return model.encode([DOC + (t or "") for t in texts], batch_size=32,
                            normalize_embeddings=True, show_progress_bar=False)

    # ---------- (1) separability on true same-office negatives ----------
    ea = embed(pairs["abstract"].tolist()); ed = embed(pairs["description"].tolist())
    pairs["cos"] = (ea * ed).sum(axis=1)
    p1 = pairs[pairs["label"] == 1]; n1 = pairs[pairs["label"] == 0]
    p1e = p1[p1["pair_id"].isin(n1["pair_id"])]
    base, lo, hi = boot(p1e["cos"].to_numpy(), n1["cos"].to_numpy())
    print("=== ModernBERT cosine  P1-vs-N1 (TRUE same-office negatives) ===")
    print(f"  ROC-AUC = {base:.3f} (95% CI {lo:.3f}-{hi:.3f})  n={len(p1e)} vs {len(n1)}")
    dq = pd.qcut(p1e["desc_len"], 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")
    p1e = p1e.assign(dq=dq)
    for q in ["Q1", "Q2", "Q3", "Q4"]:
        sp = p1e[p1e["dq"] == q]; sn = n1[n1["pair_id"].isin(sp["pair_id"])]
        if len(sp) >= 10 and len(sn) >= 10:
            print(f"    {q}: len {int(sp['desc_len'].min())}-{int(sp['desc_len'].max())} "
                  f"n={len(sp)} AUC={auc_mw(sp['cos'].to_numpy(), sn['cos'].to_numpy()):.3f}")

    # ---------- (2) realistic-pool precision@k within same office ----------
    fp = pd.read_parquet(REPO / "data/derived/fpds_10q_sr3.parquet")
    fp = fp[fp["UEI"].notna() & (fp["descriptionOfContractRequirement"].fillna("").str.len() > 0)].copy()
    fp["office"] = fp["contractingOfficeID"].fillna("")
    fp = fp[fp["UEI"].isin(pairs["uei_fpds"])]  # firms that have a Phase II abstract
    fp["demb"] = list(embed(fp["descriptionOfContractRequirement"].tolist()))

    # query = each distinct (firm, office) with its most-recent-prior Phase II abstract (from P1)
    q = p1.drop_duplicates(["uei_fpds", "office"])[["uei_fpds", "office", "abstract", "desc_len"]]
    qemb = {i: e for i, e in zip(q.index, embed(q["abstract"].tolist()))}

    rows = []
    for i, r in q.iterrows():
        pool = fp[fp["office"] == r["office"]]
        if pool["UEI"].nunique() < 2 or len(pool) < 3:
            continue  # need a real ranking task
        sims = np.array([float(qemb[i] @ d) for d in pool["demb"]])
        order = sims.argsort()[::-1]
        ranked_uei = pool["UEI"].to_numpy()[order]
        gold = ranked_uei == r["uei_fpds"]
        first = int(np.argmax(gold)) + 1 if gold.any() else None
        rows.append({
            "office": r["office"], "pool_n": len(pool), "pool_firms": pool["UEI"].nunique(),
            "desc_len": r["desc_len"],
            "p_at_1": int(gold[0]), "hit_at_5": int(gold[:5].any()),
            "mrr": (1.0 / first) if first else 0.0,
        })
    ret = pd.DataFrame(rows)
    print(f"\n=== Retrieval precision@k over SAME-OFFICE pools ({len(ret)} queries) ===")
    print(f"  pool size: median {int(ret['pool_n'].median())}  max {int(ret['pool_n'].max())}  "
          f"firms/pool median {int(ret['pool_firms'].median())}")
    print(f"  P@1={ret['p_at_1'].mean():.3f}  hit@5={ret['hit_at_5'].mean():.3f}  MRR={ret['mrr'].mean():.3f}")
    well = ret[ret["desc_len"] >= 100]
    if len(well) >= 10:
        print(f"  well-described queries (gold desc >=100 chars, n={len(well)}): "
              f"P@1={well['p_at_1'].mean():.3f}  hit@5={well['hit_at_5'].mean():.3f}  MRR={well['mrr'].mean():.3f}")
    print("  NOTE: pool = SR3-coded records only; real pool (all contracts, M0a) is larger/harder "
          "-> these are OPTIMISTIC upper bounds.")
    pairs[["stratum", "label", "office", "desc_len", "cos", "piid"]].to_parquet(
        REPO / "data/derived/phase3_benchmark_scores_embedding.parquet")
    ret.to_parquet(REPO / "data/derived/phase3_benchmark_retrieval.parquet")


if __name__ == "__main__":
    main()
