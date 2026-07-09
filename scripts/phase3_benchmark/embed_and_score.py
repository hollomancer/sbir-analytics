"""Embedding separability: ModernBERT-Embed cosine on the P1/N1 pairs vs the lexical baseline.

Uses nomic-ai/modernbert-embed-base (the repo-standard model behind ModernBertClient's local mode).
Reports P1-vs-N1 ROC-AUC (Mann-Whitney) + bootstrap CI, overall and by FPDS description-length
quartile, to compare against the Jaccard baseline (0.598 overall / 0.755 in the well-described Q4).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

REPO = Path(__file__).resolve().parents[2]
RNG = np.random.default_rng(20260708)
MODEL = "nomic-ai/modernbert-embed-base"
# nomic prefixes (repo ModernBertClient uses the same convention)
DOC = "search_document: "


def auc_mw(pos: np.ndarray, neg: np.ndarray) -> float:
    allv = np.concatenate([pos, neg])
    order = allv.argsort()
    ranks = np.empty(len(allv), float)
    ranks[order] = np.arange(1, len(allv) + 1)
    _, inv, counts = np.unique(allv, return_inverse=True, return_counts=True)
    sums = np.zeros(len(counts)); np.add.at(sums, inv, ranks)
    ranks = (sums / counts)[inv]
    r_pos = ranks[: len(pos)].sum()
    return (r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def boot(pos, neg, n=2000):
    b = auc_mw(pos, neg)
    xs = [auc_mw(RNG.choice(pos, len(pos), True), RNG.choice(neg, len(neg), True)) for _ in range(n)]
    lo, hi = np.percentile(xs, [2.5, 97.5])
    return b, lo, hi


def main() -> None:
    pairs = pd.read_parquet(REPO / "data/derived/phase3_match_benchmark_pairs.parquet")
    model = SentenceTransformer(MODEL)

    # unique texts -> embed once
    abstracts = pairs["abstract"].fillna("").tolist()
    descs = pairs["description"].fillna("").tolist()
    ea = model.encode([DOC + t for t in abstracts], batch_size=32, normalize_embeddings=True,
                      show_progress_bar=False)
    ed = model.encode([DOC + t for t in descs], batch_size=32, normalize_embeddings=True,
                      show_progress_bar=False)
    pairs["cos"] = (ea * ed).sum(axis=1)

    p1 = pairs[pairs["label"] == 1]; n1 = pairs[pairs["label"] == 0]
    base, lo, hi = boot(p1["cos"].to_numpy(), n1["cos"].to_numpy())
    print("=== ModernBERT-Embed cosine  P1-vs-N1 separability ===")
    print(f"  P1 median cos: {p1['cos'].median():.3f}   N1 median: {n1['cos'].median():.3f}")
    print(f"  ROC-AUC = {base:.3f}  (95% bootstrap CI {lo:.3f}-{hi:.3f})   [lexical was 0.598]")

    q = pd.qcut(p1["desc_len"], 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")
    p1 = p1.assign(dq=q)
    print("\n  by FPDS description-length quartile (embedding):")
    for ql in ["Q1", "Q2", "Q3", "Q4"]:
        sp = p1[p1["dq"] == ql]
        sn = n1[n1["piid"].isin(sp["piid"])]
        if len(sp) < 10 or len(sn) < 10:
            continue
        au = auc_mw(sp["cos"].to_numpy(), sn["cos"].to_numpy())
        print(f"    {ql}: desc_len {int(sp['desc_len'].min())}-{int(sp['desc_len'].max())}  "
              f"n={len(sp)}  AUC={au:.3f}")

    pairs[["stratum", "label", "firm_fpds", "firm_sbir", "ag", "desc_len", "cos", "piid"]].to_parquet(
        REPO / "data/derived/phase3_benchmark_scores_embedding.parquet")
    print("\nwrote scores -> data/derived/phase3_benchmark_scores_embedding.parquet")


if __name__ == "__main__":
    main()
