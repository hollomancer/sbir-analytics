"""Provisional retrieval score by target-description length.

This selected-cohort diagnostic cannot identify a causal length threshold: the
input already excludes descriptions below 150 characters and length can proxy
field content. It is retained only to regenerate a descriptive curve.

Inputs: award_data.csv + cached TechPort JSON; optional DoD coded parquet for the production length distribution.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from retrieval_metrics import tie_corrected_auc
from text_richness_2x2 import (_firm_orgs, _is_sbir, normalize_name, random_negatives)


def per_firm_auc(query_texts: list[str], target_texts: list[str],
                 neg_indices: dict[int, np.ndarray]) -> np.ndarray:
    """Per-firm retrieval AUC under a fixed negative set (TF-IDF). Pure."""
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2)
    matrix = vec.fit_transform(list(query_texts) + list(target_texts))
    n = len(query_texts)
    sims = cosine_similarity(matrix[:n], matrix[n:])
    return np.array([
        tie_corrected_auc(float(sims[i, i]), sims[i, neg_indices[i]]) for i in range(n)
    ])


def auc_by_length_decile(aucs: np.ndarray, lengths: np.ndarray,
                         n_bins: int = 10) -> list[dict[str, float]]:
    """Mean AUC within each target-length decile. Pure — the operating curve."""
    bins = pd.qcut(lengths, n_bins, labels=False, duplicates="drop")
    rows = []
    for b in sorted(set(bins)):
        mask = bins == b
        rows.append({"decile": int(b), "len_lo": int(lengths[mask].min()),
                     "len_hi": int(lengths[mask].max()), "mean_auc": float(aucs[mask].mean()),
                     "n": int(mask.sum())})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--techport", type=Path, required=True)
    parser.add_argument("--coded", type=Path, default=Path("data/derived/m0a_coded_dod.parquet"))
    args = parser.parse_args(argv)

    awards = pd.read_csv(args.awards, dtype=str, keep_default_na=False)
    awards = awards[awards["UEI"].str.len() > 5]
    name_to_ueis: dict[str, set[str]] = {}
    for company, uei in zip(awards["Company"], awards["UEI"], strict=True):
        key = normalize_name(company)
        if len(key) > 4:
            name_to_ueis.setdefault(key, set()).add(str(uei))
    name_to_uei = {key: next(iter(ueis)) for key, ueis in name_to_ueis.items()
                   if len(ueis) == 1}
    q_abstract = awards.groupby("UEI")["Abstract"].apply(lambda s: " ".join(x for x in s if x)[:9000]).to_dict()

    listing = json.loads(args.techport.read_text())
    projects = listing.get("results") or listing.get("projects") or listing
    t_desc: dict[str, str] = {}
    for project in sorted(projects, key=lambda value: str(value.get("projectId") or value.get("id") or "")):
        if _is_sbir(project):
            continue
        description = str(project.get("description") or "")
        if len(description) < 150:
            continue
        for org in _firm_orgs(project):
            uei = name_to_uei.get(normalize_name(org))
            if uei and uei in q_abstract and uei not in t_desc:
                t_desc[uei] = description
    firms = [u for u in t_desc if len(q_abstract[u]) > 80]

    lengths = np.array([len(t_desc[u]) for u in firms])
    aucs = per_firm_auc([q_abstract[u] for u in firms], [t_desc[u] for u in firms],
                        random_negatives(len(firms), 25))
    print(f"AUC by TARGET-description-length decile (rich/rich, TF-IDF, random neg, n={len(firms)}):\n")
    print(f"  {'decile':6s} {'len range (chars)':20s} {'mean AUC':9s} n")
    for row in auc_by_length_decile(aucs, lengths):
        length_range = f"{row['len_lo']}-{row['len_hi']}"
        print(f"  {row['decile']:^6d} {length_range:20s} {row['mean_auc']:.3f}    {row['n']}")
    print(f"\n  Pearson r(length, AUC) = {np.corrcoef(lengths, aucs)[0, 1]:.2f}  (selected desc>=150 cohort)")

    if args.coded.exists():
        desc_len = pd.read_parquet(args.coded)["desc"].astype(str).str.len()
        print(f"\n  DoD production: USAspending 'desc' median {desc_len.median():.0f} chars, "
              f"{100 * (desc_len < 150).mean():.0f}% under 150; no causal AUC extrapolation is made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
