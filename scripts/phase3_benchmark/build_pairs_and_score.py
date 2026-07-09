"""Construct P1/N1 benchmark pairs and run the P1-vs-N1 separability test (lexical baseline).

N1 is a TRUE same-funding-office hard negative: firm B's coded-Phase-III description paired with a
DIFFERENT firm A's prior Phase II abstract, where A is another SR3 awardee in the SAME FPDS
contracting office (a real competitor in that office) — not merely the same agency. Reports
ROC-AUC (Mann-Whitney) + bootstrap CI, overall and by FPDS description-length quartile.

Embedding scorer + precision@k retrieval live in embed_and_score.py. Read-only inputs.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
RNG = np.random.default_rng(20260708)

STOP = set("the a an of and or for to in on with by from is are this that these those be as at "
           "using use used based system systems method methods device technology development "
           "program phase sbir sttr research small business innovation new novel approach".split())


def toks(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2 and w not in STOP}


def jaccard(a: str, b: str) -> float:
    ta, tb = toks(a), toks(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def auc_mw(pos: np.ndarray, neg: np.ndarray) -> float:
    allv = np.concatenate([pos, neg])
    order = allv.argsort()
    ranks = np.empty(len(allv), float)
    ranks[order] = np.arange(1, len(allv) + 1)
    _, inv, counts = np.unique(allv, return_inverse=True, return_counts=True)
    sums = np.zeros(len(counts)); np.add.at(sums, inv, ranks)
    ranks = (sums / counts)[inv]
    return (ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def bootstrap_auc(pos, neg, n=2000):
    base = auc_mw(pos, neg)
    xs = [auc_mw(RNG.choice(pos, len(pos), True), RNG.choice(neg, len(neg), True)) for _ in range(n)]
    lo, hi = np.percentile(xs, [2.5, 97.5])
    return base, lo, hi


def main() -> None:
    a = pd.read_csv(REPO / "data/raw/sbir/award_data.csv", dtype=str,
                    keep_default_na=False, na_values=[""])
    a = a[(a["Phase"] == "Phase II") & (a["Abstract"].fillna("").str.len() > 0)].copy()
    a["year"] = pd.to_numeric(a["Award Year"], errors="coerce")

    fp = pd.read_parquet(REPO / "data/derived/fpds_10q_sr3.parquet")
    fp = fp[fp["UEI"].notna() & (fp["descriptionOfContractRequirement"].fillna("").str.len() > 0)].copy()
    fp["sign_year"] = pd.to_numeric(fp["signedDate"].str[:4], errors="coerce")
    fp["office"] = fp["contractingOfficeID"].fillna("")

    a_by_uei = {u: g for u, g in a.groupby("UEI")}

    def prior_abstract(uei: str, before: float):
        g = a_by_uei.get(uei)
        if g is None:
            return None
        prior = g[g["year"] <= (before if pd.notna(before) else 9999)]
        prior = prior if len(prior) else g
        return prior.sort_values("year").iloc[-1]

    # only SR3 records whose firm has a Phase II abstract
    fp = fp[fp["UEI"].isin(a_by_uei)].copy()

    # ---- P1: same-firm derivative pairs ----
    p1 = []
    for _, r in fp.iterrows():
        pick = prior_abstract(r["UEI"], r["sign_year"])
        if pick is None:
            continue
        p1.append({
            "stratum": "P1", "label": 1, "office": r["office"],
            "uei_fpds": r["UEI"], "uei_sbir": pick["UEI"],
            "firm_fpds": r["vendorName"], "firm_sbir": pick["Company"],
            "abstract": pick["Abstract"], "description": r["descriptionOfContractRequirement"],
            "sign_year": r["sign_year"], "desc_len": len(r["descriptionOfContractRequirement"]),
            "piid": r.get("PIID"), "pair_rule": "same-UEI most-recent-prior Phase II (Tier-2-grade)",
        })
    p1 = pd.DataFrame(p1).reset_index(drop=True)
    p1["pair_id"] = p1.index  # unique key (FPDS PIID is a non-unique order/mod number)

    # firms (with Phase II abstracts) per office, for same-office negatives
    firms_by_office: dict[str, list[str]] = {
        off: sorted(g["UEI"].unique()) for off, g in fp.groupby("office")
    }

    # ---- N1: TRUE same-office hard negatives (different firm, same contracting office) ----
    n1 = []
    for _, r in p1.iterrows():
        others = [u for u in firms_by_office.get(r["office"], []) if u != r["uei_fpds"]]
        if not others:
            continue  # single-firm office -> no same-office negative
        a_uei = others[RNG.integers(len(others))]
        pick = prior_abstract(a_uei, r["sign_year"])
        if pick is None or pick["Company"].strip().lower() == r["firm_sbir"].strip().lower():
            continue
        n1.append({
            "stratum": "N1", "label": 0, "office": r["office"], "pair_id": r["pair_id"],
            "uei_fpds": r["uei_fpds"], "uei_sbir": pick["UEI"],
            "firm_fpds": r["firm_fpds"], "firm_sbir": pick["Company"],
            "abstract": pick["Abstract"], "description": r["description"],
            "sign_year": r["sign_year"], "desc_len": r["desc_len"], "piid": r["piid"],
            "pair_rule": "diff-firm SAME contracting office (true hard negative)",
        })
    n1 = pd.DataFrame(n1)
    print(f"P1 (same-firm) pairs: {len(p1)} from {p1['uei_fpds'].nunique()} firms")
    print(f"N1 (same-office diff-firm) pairs: {len(n1)}  "
          f"(P1 in single-firm offices with no same-office negative: {len(p1)-len(n1)})")

    pairs = pd.concat([p1, n1], ignore_index=True)
    pairs.to_parquet(REPO / "data/derived/phase3_match_benchmark_pairs.parquet")
    print(f"wrote {len(pairs)} pairs -> data/derived/phase3_match_benchmark_pairs.parquet")

    # ---- lexical baseline separability (only P1 that have an N1 counterpart, for a fair contrast) ----
    p1e = p1[p1["pair_id"].isin(n1["pair_id"])].copy()
    p1e["jac"] = [jaccard(x.abstract, x.description) for x in p1e.itertuples()]
    n1["jac"] = [jaccard(x.abstract, x.description) for x in n1.itertuples()]
    base, lo, hi = bootstrap_auc(p1e["jac"].to_numpy(), n1["jac"].to_numpy())
    print("\n=== LEXICAL (Jaccard) P1-vs-N1 (TRUE same-office negatives) ===")
    print(f"  P1 median Jaccard {p1e['jac'].median():.3f}  N1 median {n1['jac'].median():.3f}")
    print(f"  ROC-AUC = {base:.3f}  (95% CI {lo:.3f}-{hi:.3f})   n={len(p1e)} vs {len(n1)}")
    p1e["dq"] = pd.qcut(p1e["desc_len"], 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")
    print("  by FPDS description-length quartile:")
    for q in ["Q1", "Q2", "Q3", "Q4"]:
        sp = p1e[p1e["dq"] == q]; sn = n1[n1["pair_id"].isin(sp["pair_id"])]
        if len(sp) >= 10 and len(sn) >= 10:
            print(f"    {q}: len {int(sp['desc_len'].min())}-{int(sp['desc_len'].max())} "
                  f"n={len(sp)} AUC={auc_mw(sp['jac'].to_numpy(), sn['jac'].to_numpy()):.3f}")


if __name__ == "__main__":
    main()
