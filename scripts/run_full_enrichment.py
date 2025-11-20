#!/usr/bin/env python3
"""
sbir-analytics/scripts/run_full_enrichment.py

Run a full enrichment pass: join awards_data.csv against companies_merged.csv
to enrich award records with company-level attributes.

Behavior:
- Deterministic joins first:
  - UEI exact match (cleaned)
  - DUNS exact match (digits-only)
- Fuzzy-name fallback using token-based scorer (rapidfuzz)
  - Blocking by normalized prefix to limit candidate set
  - Configurable thresholds for auto-accept and candidate-review
- Chunked processing for large awards CSV (pandas.read_csv chunks)
- Outputs:
  - enriched awards CSV: data/processed/enriched_awards.csv
  - candidate review CSV (medium-confidence fuzzy matches): reports/enrichment_candidate_review.csv
  - summary JSON: reports/enrichment_summary.json

Usage:
    python sbir-analytics/scripts/run_full_enrichment.py \
        --companies data/raw/sbir/companies_merged.csv \
        --awards data/raw/sbir/awards_data.csv \
        --out-enriched data/processed/enriched_awards.csv \
        --out-candidates reports/enrichment_candidate_review.csv \
        --out-summary reports/enrichment_summary.json

Note: requires pandas and rapidfuzz installed in the environment.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import pandas as pd


# rapidfuzz is used for token-based fuzzy matching
try:
    from rapidfuzz import fuzz, process
except Exception as e:
    raise ImportError("Please install rapidfuzz (pip install rapidfuzz)") from e


# ----------------------
# Helpers
# ----------------------
def clean_uei(v: str | None) -> str:
    if not v:
        return ""
    return "".join(ch for ch in str(v) if ch.isalnum()).upper()


def clean_duns(v: str | None) -> str:
    if not v:
        return ""
    return "".join(ch for ch in str(v) if ch.isdigit())


def normalize_name(s: str | None) -> str:
    """Normalize name using centralized utility.
    
    Uses centralized text normalization utility with suffix normalization.
    """
    from src.utils.text_normalization import normalize_name as normalize_name_util
    
    return normalize_name_util(s, remove_suffixes=False)


def build_block_key(name_norm: str, prefix_len: int = 2) -> str:
    return name_norm[:prefix_len] if name_norm else ""


# ----------------------
# Index building
# ----------------------
def build_company_indexes(
    companies: pd.DataFrame,
    company_col: str = "company",
    uei_col: str = "UEI",
    duns_col_names: Iterable[str] = ("DUNs", "Duns"),
    prefix_len: int = 2,
) -> dict[str, object]:
    """
    Create helper indexes:
    - comp_df: canonical companies DataFrame (indexed by original index)
    - comp_norm: Series index->normalized name
    - comp_block: Series index->block key
    - comp_by_uei: dict UEI -> index
    - comp_by_duns: dict DUNS -> index
    - blocks: dict block_key -> list[index]
    """
    df = companies.copy().reset_index(drop=False)  # keep original index as 'index' column
    # Ensure column exists
    if company_col not in df.columns:
        df[company_col] = df.iloc[:, 0].astype(str)

    df["_norm_name"] = df[company_col].astype(str).map(normalize_name)
    df["_block"] = df["_norm_name"].map(lambda n: build_block_key(n, prefix_len))

    comp_by_uei: dict[str, int] = {}
    if uei_col in df.columns:
        for _, row in df.iterrows():
            k = clean_uei(row.get(uei_col, ""))
            if k:
                comp_by_uei[k] = int(row["index"])

    # detect duns column
    duns_col = None
    for cand in duns_col_names:
        if cand in df.columns:
            duns_col = cand
            break

    comp_by_duns: dict[str, int] = {}
    if duns_col:
        for _, row in df.iterrows():
            k = clean_duns(row.get(duns_col, ""))
            if k:
                comp_by_duns[k] = int(row["index"])

    blocks: dict[str, list[int]] = defaultdict(list)
    for _, row in df.iterrows():
        blk = row["_block"]
        if blk is None:
            blk = ""
        blocks[blk].append(int(row["index"]))

    # map index to normalized name for rapidfuzz choices
    norm_map = {int(row["index"]): row["_norm_name"] for _, row in df.iterrows()}

    return {
        "comp_df": df.set_index("index"),
        "norm_map": norm_map,
        "blocks": blocks,
        "comp_by_uei": comp_by_uei,
        "comp_by_duns": comp_by_duns,
    }


# ----------------------
# Enrichment for chunk
# ----------------------
def enrich_awards_chunk(
    awards_chunk: pd.DataFrame,
    idxs: dict[str, object],
    *,
    award_company_col: str = "Company",
    uei_col_awards: str = "UEI",
    duns_col_awards_candidates: Iterable[str] = ("Duns", "DUNs"),
    high_threshold: int = 90,
    med_threshold: int = 75,
    top_k: int = 3,
    prefix_len: int = 2,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Enrich a chunk of awards_df using the provided company indexes.
    Returns enriched chunk (with merged company_ columns) and a list of candidate-review rows.
    """
    comp_df = idxs["comp_df"]
    norm_map = idxs["norm_map"]
    blocks = idxs["blocks"]
    comp_by_uei = idxs["comp_by_uei"]
    comp_by_duns = idxs["comp_by_duns"]

    awards = awards_chunk.copy()
    # canonical award company column
    if award_company_col not in awards.columns:
        # fallback
        awards["Company"] = awards.iloc[:, 0].astype(str)
        award_company_col = "Company"

    awards["_norm_name"] = awards[award_company_col].astype(str).map(normalize_name)
    # identify award UEI/DUN columns if present
    awards["UEI_clean"] = (
        awards[uei_col_awards].astype(str).map(clean_uei)
        if uei_col_awards in awards.columns
        else ""
    )
    award_duns_col = None
    for cand in duns_col_awards_candidates:
        if cand in awards.columns:
            award_duns_col = cand
            break
    if award_duns_col:
        awards["DUNs_clean"] = awards[award_duns_col].astype(str).map(clean_duns)
    else:
        awards["DUNs_clean"] = ""

    # Prepare result holders
    awards["_matched_company_idx"] = pd.NA
    awards["_match_score"] = pd.NA
    awards["_match_method"] = pd.NA
    awards["_match_candidates"] = pd.NA

    candidate_review_rows: list[dict] = []

    # Precompute global choices mapping for fallback
    global_choices = norm_map

    for ai, arow in awards.iterrows():
        # exact UEI
        award_uei = arow.get("UEI_clean") or ""
        if award_uei and award_uei in comp_by_uei:
            matched_idx = comp_by_uei[award_uei]
            awards.at[ai, "_matched_company_idx"] = matched_idx
            awards.at[ai, "_match_score"] = 100
            awards.at[ai, "_match_method"] = "uei-exact"
            continue

        # exact DUNS
        award_duns = arow.get("DUNs_clean") or ""
        if award_duns and award_duns in comp_by_duns:
            matched_idx = comp_by_duns[award_duns]
            awards.at[ai, "_matched_company_idx"] = matched_idx
            awards.at[ai, "_match_score"] = 100
            awards.at[ai, "_match_method"] = "duns-exact"
            continue

        # candidate generation via block
        blk = build_block_key(arow.get("_norm_name") or "", prefix_len)
        candidate_idxs = blocks.get(blk, [])
        if not candidate_idxs:
            # fallback: small subset of companies—top 100 by occurrence in merged file (cheap)
            candidate_idxs = list(global_choices.keys())[:500]

        # Build choices mapping (index -> normalized name)
        choices = {idx: global_choices[idx] for idx in candidate_idxs if idx in global_choices}

        target = arow.get("_norm_name") or ""
        if not target or not choices:
            awards.at[ai, "_match_method"] = "no-candidates"
            continue

        # Use rapidfuzz to get top_k candidates
        results = process.extract(
            target, choices, scorer=fuzz.token_set_ratio, processor=None, limit=top_k
        )
        # results are tuples; normalize to (idx, score)
        simple_results: list[tuple[int, int]] = []
        for r in results:
            # r often (choice_value, score, key) where key is original choice key (our index)
            if len(r) >= 3:
                key = r[2]
                score = int(r[1])
                try:
                    idx_candidate = int(key)
                except Exception:
                    # fallback lookup by value
                    idx_candidate = None
                    for k, v in choices.items():
                        if v == r[0]:
                            idx_candidate = k
                            break
                    if idx_candidate is None:
                        continue
                simple_results.append((idx_candidate, score))
            elif len(r) == 2:
                # (choice_value, score)
                score = int(r[1])
                # find index by value
                idx_candidate = None
                for k, v in choices.items():
                    if v == r[0]:
                        idx_candidate = k
                        break
                if idx_candidate is None:
                    continue
                simple_results.append((idx_candidate, score))

        if not simple_results:
            awards.at[ai, "_match_method"] = "no-candidates"
            continue

        # attach candidates json if asked
        awards.at[ai, "_match_candidates"] = json.dumps(
            [{"idx": r[0], "score": r[1], "name": choices.get(r[0], "")} for r in simple_results],
            ensure_ascii=False,
        )

        best_idx, best_score = simple_results[0]
        if best_score >= high_threshold:
            awards.at[ai, "_matched_company_idx"] = best_idx
            awards.at[ai, "_match_score"] = best_score
            awards.at[ai, "_match_method"] = "fuzzy-auto"
        elif best_score >= med_threshold:
            awards.at[ai, "_match_score"] = best_score
            awards.at[ai, "_match_method"] = "fuzzy-candidate"
            # Add candidate review row
            candidate_review_rows.append(
                {
                    "award_index": int(ai),
                    "award_company": arow.get(award_company_col),
                    "best_match_idx": int(best_idx),
                    "best_match_score": int(best_score),
                    "candidates": awards.at[ai, "_match_candidates"],
                }
            )
        else:
            awards.at[ai, "_match_score"] = best_score
            awards.at[ai, "_match_method"] = "fuzzy-low"

    # Merge matched company fields into the awards chunk
    # comp_df is indexed by original company index
    comp_prefixed = comp_df.add_prefix("company_")
    # Ensure matched idx column exists
    if "_matched_company_idx" not in awards.columns:
        awards["_matched_company_idx"] = pd.NA

    enriched = (
        awards.reset_index()
        .set_index("_matched_company_idx")
        .join(comp_prefixed, how="left")
        .reset_index()
    )
    # Remove helper columns we added
    for helper in ("_norm_name",):
        if helper in enriched.columns:
            enriched = enriched.drop(columns=[helper])

    return enriched, candidate_review_rows


# ----------------------
# Orchestration
# ----------------------
def run_full_enrichment(
    companies_path: Path,
    awards_path: Path,
    out_enriched: Path,
    out_candidates: Path,
    out_summary: Path,
    *,
    chunk_size: int = 10000,
    high_threshold: int = 90,
    med_threshold: int = 75,
    prefix_len: int = 2,
    top_k: int = 3,
):
    # Load companies canonical file
    print(f"Loading companies from: {companies_path}")
    companies = pd.read_csv(companies_path, dtype=str, keep_default_na=False)
    # create canonical columns if missing
    if "company" not in companies.columns:
        # find a name column to canonicalize
        candidates = [c for c in companies.columns if c.lower().startswith("company")]
        if candidates:
            companies["company"] = companies[candidates[0]]
        else:
            companies["company"] = companies.iloc[:, 0].astype(str)

    if "company_url" not in companies.columns:
        candidates = [c for c in companies.columns if "url" in c.lower()]
        companies["company_url"] = companies[candidates[0]] if candidates else pd.NA

    # Build indexes
    idxs = build_company_indexes(
        companies,
        company_col="company",
        uei_col="UEI",
        duns_col_names=("DUNs", "Duns"),
        prefix_len=prefix_len,
    )

    # Prepare outputs
    out_enriched.parent.mkdir(parents=True, exist_ok=True)
    out_candidates.parent.mkdir(parents=True, exist_ok=True)
    out_summary.parent.mkdir(parents=True, exist_ok=True)

    # Stats counters
    stats = Counter()
    candidate_rows_accum: list[dict] = []

    # Process awards CSV in chunks
    print(f"Processing awards from: {awards_path} in chunks of {chunk_size}")
    first_chunk = True
    total_rows_processed = 0
    for chunk in pd.read_csv(awards_path, dtype=str, keep_default_na=False, chunksize=chunk_size):
        total_rows_processed += len(chunk)
        enriched_chunk, candidate_rows = enrich_awards_chunk(
            chunk,
            idxs,
            award_company_col="Company",
            uei_col_awards="UEI",
            duns_col_awards_candidates=("Duns", "DUNs"),
            high_threshold=high_threshold,
            med_threshold=med_threshold,
            top_k=top_k,
            prefix_len=prefix_len,
        )

        # Update stats
        stats["chunks"] += 1
        stats["rows_processed"] = total_rows_processed
        # count kinds of match methods
        mcounts = enriched_chunk["_match_method"].fillna("none").value_counts().to_dict()
        for k, v in mcounts.items():
            stats[f"method_{k}"] += int(v)

        # Append candidate rows for review
        if candidate_rows:
            candidate_rows_accum.extend(candidate_rows)

        # Write enriched chunk to output (append)
        if first_chunk:
            enriched_chunk.to_csv(out_enriched, index=False, mode="w")
            first_chunk = False
        else:
            enriched_chunk.to_csv(out_enriched, index=False, mode="a", header=False)

    # Write candidate-review CSV
    if candidate_rows_accum:
        cand_df = pd.DataFrame(candidate_rows_accum)
        cand_df.to_csv(out_candidates, index=False)
    else:
        # write an empty CSV with columns
        pd.DataFrame(
            columns=[
                "award_index",
                "award_company",
                "best_match_idx",
                "best_match_score",
                "candidates",
            ]
        ).to_csv(out_candidates, index=False)

    # Summary
    summary = {
        "timestamp": datetime.utcnow().isoformat(),
        "companies_merged": str(companies_path),
        "awards_source": str(awards_path),
        "output_enriched": str(out_enriched),
        "output_candidates": str(out_candidates),
        "rows_processed": int(total_rows_processed),
        "stats": {k: int(v) if isinstance(v, int | float) else v for k, v in stats.items()},
    }

    with out_summary.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    print("Enrichment complete. Summary:")
    print(json.dumps(summary, indent=2))


# ----------------------
# CLI
# ----------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run full enrichment: join awards with merged companies"
    )
    p.add_argument(
        "--companies", default="data/raw/sbir/companies_merged.csv", help="Canonical companies CSV"
    )
    p.add_argument("--awards", default="data/raw/sbir/awards_data.csv", help="Full awards CSV")
    p.add_argument(
        "--out-enriched", default="data/processed/enriched_awards.csv", help="Output enriched CSV"
    )
    p.add_argument(
        "--out-candidates",
        default="reports/enrichment_candidate_review.csv",
        help="Candidate review CSV",
    )
    p.add_argument(
        "--out-summary", default="reports/enrichment_summary.json", help="Enrichment summary JSON"
    )
    p.add_argument(
        "--chunksize", type=int, default=10000, help="Chunk size for processing awards CSV"
    )
    p.add_argument(
        "--high", type=int, default=90, help="High threshold for auto-accept fuzzy matches"
    )
    p.add_argument("--med", type=int, default=75, help="Medium threshold for candidate-review")
    p.add_argument(
        "--prefix", type=int, default=2, help="Normalized name prefix length for blocking"
    )
    p.add_argument("--topk", type=int, default=3, help="Top-k fuzzy candidates to store")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_full_enrichment(
        Path(args.companies),
        Path(args.awards),
        Path(args.out_enriched),
        Path(args.out_candidates),
        Path(args.out_summary),
        chunk_size=args.chunksize,
        high_threshold=args.high,
        med_threshold=args.med,
        prefix_len=args.prefix,
        top_k=args.topk,
    )
