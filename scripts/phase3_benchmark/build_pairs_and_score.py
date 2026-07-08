"""Construct P1/N1/N3 benchmark pairs and run the P1-vs-N1 separability test (lexical baseline).

Gating question: can text separate true derivative pairs (P1: same-firm Phase II abstract x its
coded-Phase-III FPDS description) from hard negatives (N1: a Phase III description x a *different*
same-agency/adjacent-NAICS firm's Phase II abstract)? Reports ROC-AUC (Mann-Whitney) + bootstrap CI.

Embedding scorer is added in a follow-up step; this establishes the lexical baseline the embedder
must beat. Read-only inputs; writes benchmark pairs + scores under data/derived/.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
RNG = np.random.default_rng(20260708)  # deterministic; no argless Date/random

# ---- coarse agency normalizer (SBIR.gov "Agency" vs FPDS agencyID_name) ----
def norm_agency(s: str | None) -> str:
    s = (s or "").upper()
    if "DEFENSE" in s or "ARMY" in s or "NAVY" in s or "AIR FORCE" in s or "DOD" in s:
        return "DOD"
    if "HEALTH" in s or "NIH" in s or "HHS" in s:
        return "HHS"
    if "NASA" in s or "AERONAUTICS" in s:
        return "NASA"
    if "NATIONAL SCIENCE" in s or s.strip() == "NSF":
        return "NSF"
    if "ENERGY" in s:
        return "DOE"
    if "HOMELAND" in s or "DHS" in s:
        return "DHS"
    if "AGRICULT" in s or "USDA" in s:
        return "USDA"
    return s.strip()[:12] or "OTHER"


STOP = set("the a an of and or for to in on with by from is are this that these those be as at "
           "using use used based system systems method methods device technology development "
           "program phase sbir sttr research small business innovation new novel approach".split())


def toks(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2 and w not in STOP}


def jaccard(a: str, b: str) -> float:
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def auc_mw(pos: np.ndarray, neg: np.ndarray) -> float:
    """ROC-AUC via Mann-Whitney U (rank-based, ties averaged)."""
    allv = np.concatenate([pos, neg])
    order = allv.argsort()
    ranks = np.empty(len(allv), float)
    ranks[order] = np.arange(1, len(allv) + 1)
    # average tied ranks
    _, inv, counts = np.unique(allv, return_inverse=True, return_counts=True)
    sums = np.zeros(len(counts)); np.add.at(sums, inv, ranks)
    ranks = (sums / counts)[inv]
    r_pos = ranks[: len(pos)].sum()
    return (r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def bootstrap_auc(pos: np.ndarray, neg: np.ndarray, n: int = 2000) -> tuple[float, float, float]:
    base = auc_mw(pos, neg)
    boots = []
    for _ in range(n):
        p = RNG.choice(pos, len(pos), replace=True)
        q = RNG.choice(neg, len(neg), replace=True)
        boots.append(auc_mw(p, q))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return base, lo, hi


def main() -> None:
    # ---- load Phase II abstracts ----
    a = pd.read_csv(REPO / "data/raw/sbir/award_data.csv", dtype=str,
                    keep_default_na=False, na_values=[""])
    a = a[a["Phase"] == "Phase II"].copy()
    a["year"] = pd.to_numeric(a["Award Year"], errors="coerce")
    a["ag"] = a["Agency"].map(norm_agency)
    a["naics3"] = a.get("Solicitation Number", "").astype(str).str[:0]  # placeholder; SBIR has no NAICS
    a = a[a["Abstract"].fillna("").str.len() > 0]

    # ---- load FPDS SR3 (Phase III coded) ----
    fp = pd.read_parquet(REPO / "data/derived/fpds_10q_sr3.parquet")
    fp = fp[fp["UEI"].notna() & (fp["descriptionOfContractRequirement"].fillna("").str.len() > 0)].copy()
    fp["sign_year"] = pd.to_numeric(fp["signedDate"].str[:4], errors="coerce")
    fp["ag"] = fp.get("agencyID_name", pd.Series(index=fp.index)).map(norm_agency)
    fp["naics3"] = fp["principalNAICSCode"].fillna("").str[:3]

    # index Phase II abstracts by UEI (prefer most recent prior)
    a_by_uei = {u: g for u, g in a.groupby("UEI")}

    # ---- P1: same-firm derivative pairs ----
    p1 = []
    for _, r in fp.iterrows():
        g = a_by_uei.get(r["UEI"])
        if g is None:
            continue
        prior = g[(g["year"] <= (r["sign_year"] if pd.notna(r["sign_year"]) else 9999))]
        prior = prior if len(prior) else g
        pick = prior.sort_values("year").iloc[-1]  # most recent prior Phase II
        p1.append({
            "stratum": "P1", "label": 1,
            "uei_fpds": r["UEI"], "uei_sbir": pick["UEI"],
            "firm_fpds": r["vendorName"], "firm_sbir": pick["Company"],
            "abstract": pick["Abstract"], "description": r["descriptionOfContractRequirement"],
            "ag": r["ag"], "naics3": r["naics3"], "sign_year": r["sign_year"],
            "desc_len": len(r["descriptionOfContractRequirement"]),
            "piid": r.get("PIID"), "pair_rule": "same-UEI, most-recent-prior Phase II (Tier-2-grade)",
        })
    p1 = pd.DataFrame(p1)
    print(f"P1 (same-firm) pairs: {len(p1)}  from {p1['uei_fpds'].nunique()} firms")

    # ---- N1: hard negatives (different firm, same agency, adjacent NAICS, prior in time) ----
    # pool of Phase II abstracts tagged by agency; NAICS not in SBIR data -> use agency + time only,
    # which is a SOFTER hard-negative than 'same funding office'. Flagged in the report.
    n1 = []
    for _, r in p1.iterrows():
        cand = a[(a["ag"] == r["ag"]) & (a["UEI"] != r["uei_fpds"]) &
                 (a["year"] <= (r["sign_year"] if pd.notna(r["sign_year"]) else 9999))]
        if not len(cand):
            continue
        pick = cand.iloc[RNG.integers(len(cand))]
        # confirm different lineage (cheap proxy: different UEI + different normalized name)
        if pick["Company"].strip().lower() == r["firm_sbir"].strip().lower():
            continue
        n1.append({
            "stratum": "N1", "label": 0,
            "uei_fpds": r["uei_fpds"], "uei_sbir": pick["UEI"],
            "firm_fpds": r["firm_fpds"], "firm_sbir": pick["Company"],
            "abstract": pick["Abstract"], "description": r["description"],
            "ag": r["ag"], "naics3": r["naics3"], "sign_year": r["sign_year"],
            "desc_len": r["desc_len"], "piid": r["piid"],
            "pair_rule": "diff-firm same-agency prior Phase II (soft hard-negative: agency+time)",
        })
    n1 = pd.DataFrame(n1)
    print(f"N1 (hard negative) pairs: {len(n1)}")

    pairs = pd.concat([p1, n1], ignore_index=True)
    out = REPO / "data/derived/phase3_match_benchmark_pairs.parquet"
    pairs.to_parquet(out)
    print(f"wrote {len(pairs)} pairs -> {out}")

    # ---- lexical baseline separability ----
    p1["jac"] = [jaccard(x.abstract, x.description) for x in p1.itertuples()]
    n1["jac"] = [jaccard(x.abstract, x.description) for x in n1.itertuples()]
    base, lo, hi = bootstrap_auc(p1["jac"].to_numpy(), n1["jac"].to_numpy())
    print("\n=== LEXICAL BASELINE (Jaccard) P1-vs-N1 separability ===")
    print(f"  P1 median Jaccard: {p1['jac'].median():.3f}   N1 median: {n1['jac'].median():.3f}")
    print(f"  ROC-AUC = {base:.3f}  (95% bootstrap CI {lo:.3f}-{hi:.3f})")
    # per description-length quartile (the 'well-described stratum' question)
    p1["dq"] = pd.qcut(p1["desc_len"], 4, labels=["Q1","Q2","Q3","Q4"], duplicates="drop")
    print("\n  by FPDS description-length quartile (P1 side):")
    for q in ["Q1","Q2","Q3","Q4"]:
        sub_p = p1[p1["dq"] == q]
        if len(sub_p) < 10:
            continue
        sub_n = n1[n1["piid"].isin(sub_p["piid"])]
        if len(sub_n) < 10:
            continue
        au = auc_mw(sub_p["jac"].to_numpy(), sub_n["jac"].to_numpy())
        print(f"    {q}: desc_len {sub_p['desc_len'].min()}-{sub_p['desc_len'].max()}  "
              f"n={len(sub_p)}  AUC={au:.3f}")
    scores = pd.concat([p1, n1], ignore_index=True)[
        ["stratum","label","firm_fpds","firm_sbir","ag","desc_len","jac","piid"]]
    scores.to_parquet(REPO / "data/derived/phase3_benchmark_scores_lexical.parquet")


if __name__ == "__main__":
    main()
