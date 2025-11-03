#!/usr/bin/env python3
"""
sbir-etl/scripts/summarize_candidates.py

Summarize the enrichment candidate-review CSV produced by the enrichment pass.

This script:
- Loads the candidate-review CSV (default: reports/enrichment_candidate_review.csv)
  which is expected to have columns like:
    - award_index
    - award_company
    - best_match_idx
    - best_match_score
    - candidates (JSON string of top-k candidates)
- Parses candidate JSON and aggregates useful statistics:
    - total candidate rows
    - distribution of best_match_score
    - counts by score-buckets (high/med/low)
    - top matched company indices and names (if companies CSV provided)
    - sample candidate rows for manual inspection
- Writes a Markdown summary and a JSON diagnostics file.

Usage:
    python sbir-etl/scripts/summarize_candidates.py \
        --candidates reports/enrichment_candidate_review.csv \
        --companies data/raw/sbir/companies_merged.csv \
        --out-md reports/candidate_summary.md \
        --out-json reports/candidate_summary.json \
        --sample 25

If the companies CSV is provided and contains a canonical index column, the script
will attempt to map matched company indices to company names for better readability.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

# pandas is required; assume installed in the environment used to run the script.
import pandas as pd


def safe_load_json_candidates(s: Any) -> list[dict[str, Any]]:
    """
    Parse a JSON candidates string/structure into a list of candidate dicts.
    Accepts:
      - JSON string (utf-8)
      - already-parsed Python list/dict
      - pandas NA / empty -> returns []
    Returns a list of dicts with at least keys: idx, score, name (if available)
    """
    if s is None:
        return []
    if isinstance(s, list):
        return s
    if isinstance(s, float | int) and (pd.isna(s) or s == ""):
        return []
    try:
        if isinstance(s, str):
            s_str = s.strip()
            if not s_str:
                return []
            # sometimes pandas will store a repr like "[]", or a JSON-like string
            try:
                parsed = json.loads(s_str)
                if isinstance(parsed, list):
                    return parsed
                # if it's a dict or other, wrap it
                return [parsed]
            except Exception:
                # fallback: attempt to eval-like parsing of python lists safely by replacing single quotes
                try:
                    alt = s_str.replace("'", '"')
                    parsed = json.loads(alt)
                    if isinstance(parsed, list):
                        return parsed
                except Exception:
                    # final fallback: return a single entry with raw string
                    return [{"raw": s_str}]
        # unknown type: convert to string
        return [{"raw": str(s)}]
    except Exception:
        return []


def build_company_index_map(companies_path: Path) -> dict[str, str]:
    """
    Build a mapping from company index (stringified) to canonical company name.
    The merged companies file typically has original index in the CSV's implicit index,
    but our merge outputs preserved original columns. We attempt to find a sensible
    mapping: if the file contains an index column named 'index' we use it; otherwise
    we map by row number (0-based) as strings.

    Returns dict: str(idx) -> company_name
    """
    mapping: dict[str, str] = {}
    if not companies_path or not companies_path.exists():
        return mapping
    try:
        df = pd.read_csv(companies_path, dtype=str, keep_default_na=False)
    except Exception:
        return mapping

    # canonical company name column detection
    company_col = None
    for cand in ("company", "Company Name", "Company", "company_name"):
        if cand in df.columns:
            company_col = cand
            break
    if company_col is None:
        # fallback to first column
        company_col = df.columns[0] if len(df.columns) > 0 else None

    # If there's an explicit index column left by previous processing, try to use it
    # Look for columns that are numeric-like names: 'index' or 'orig_index' or '__index'
    index_col = None
    for cand in ("index", "orig_index", "__index", "__source_index"):
        if cand in df.columns:
            index_col = cand
            break

    if index_col is not None:
        for _, row in df.iterrows():
            idx_val = str(row.get(index_col, "")).strip()
            name = str(row.get(company_col, "")).strip()
            if idx_val == "":
                continue
            mapping[idx_val] = name
    else:
        # fall back to row-number based mapping; keys are strings of integer row numbers
        for i, name in enumerate(df[company_col].astype(str).tolist()):
            mapping[str(i)] = name

    return mapping


def bucket_score(score: float) -> str:
    """Bucket a score into high/medium/low categories for summarization."""
    try:
        s = float(score)
    except Exception:
        return "unknown"
    if s >= 90:
        return "high"
    if s >= 75:
        return "medium"
    if s >= 0:
        return "low"
    return "unknown"


def summarize_candidates(
    candidates_csv: Path,
    companies_csv: Path | None = None,
    sample_n: int = 25,
) -> dict[str, Any]:
    """
    Produce a summary dictionary for candidate-review CSV.

    The candidate file is expected to include at least:
      - award_index
      - award_company
      - best_match_idx
      - best_match_score
      - candidates (JSON)
    """
    if not candidates_csv.exists():
        raise FileNotFoundError(f"Candidates CSV not found: {candidates_csv}")

    # Load candidate-review CSV
    df = pd.read_csv(candidates_csv, dtype=str, keep_default_na=False)
    len(df)

    # Build company index map if available
    company_map = build_company_index_map(companies_csv) if companies_csv else {}

    # Parse candidate JSON and pull best score (if not provided)
    best_scores = []
    parsed_candidates = []
    for _, row in df.iterrows():
        raw_best = row.get("best_match_score", "")
        best_score = None
        if raw_best and raw_best.strip() != "":
            try:
                best_score = float(str(raw_best).strip())
            except Exception:
                best_score = None
        # parse candidates JSON string (may be '[]' or JSON)
        cand_list = safe_load_json_candidates(
            row.get("candidates") or row.get("_match_candidates") or ""
        )
        parsed_candidates.append(cand_list)
        if best_score is None:
            # derive best score from parsed list if present
            if cand_list:
                # candidate entries might have 'score' or 'best_match_score' or similar
                max_score = None
                for c in cand_list:
                    for key in ("score", "best_match_score", "match_score"):
                        if key in c:
                            try:
                                val = float(c[key])
                                if max_score is None or val > max_score:
                                    max_score = val
                            except Exception:
                                continue
                best_score = float(max_score) if max_score is not None else None
        best_scores.append(best_score if best_score is not None else float("nan"))

    df["_parsed_candidates"] = parsed_candidates
    df["_best_score"] = best_scores

    # Basic stats
    num_with_score = int(df["_best_score"].notna().sum())
    score_series = pd.to_numeric(df["_best_score"], errors="coerce")
    float(score_series.mean()) if num_with_score > 0 else None
    float(score_series.median()) if num_with_score > 0 else None
    float(score_series.min()) if num_with_score > 0 else None
    max_score = float(score_series.max()) if num_with_score > 0 else None

    # bucket distribution
    buckets = Counter()
    for s in score_series.fillna(-1).tolist():
        if math.isnan(s) or s < 0:
            buckets["unknown"] += 1
        else:
            b = bucket_score(s)
            buckets[b] += 1

    # Top matched company indices (from best_match_idx) if present
    top_indices = Counter()
    for _, row in df.iterrows():
        idx = row.get("best_match_idx") or row.get("company_idx") or ""
        if idx and str(idx).strip() != "":
            top_indices[str(idx).strip()] += 1

    # Map top indices to company names if mapping is available
    top_mapped = []
    for idx, count in top_indices.most_common(25):
        name = company_map.get(str(idx), None)
        top_mapped.append({"index": idx, "company_name": name, "count": int(count)})

    # Samples: show a few candidate rows with parsed candidates expanded
    samples = []
    for _, row in df.head(sample_n).iterrows():
        parsed = row.get("_parsed_candidates", [])
        # normalize parsed candidate items to a simple form
        norm_cands = []
        for cand in parsed[:5]:
            idx = cand.get("idx") or cand.get("index") or cand.get("key") or cand.get("id") or ""
            score = (
                cand.get("score") or cand.get("best_match_score") or cand.get("match_score") or ""
            )
            name = cand.get("name") or cand.get("company") or ""
            norm_cands.append({"idx": idx, "score": score, "name": name})
        samples.append(
            {
                "award_index": row.get("award_index") or row.get("index") or "",
                "award_company": row.get("award_company") or row.get("company") or "",
                "best_match_idx": row.get("best_match_idx") or row.get("company_idx") or "",
                "best_match_score": row.get("best_match_score") or "",
                "candidates": norm_cands,
            }
        )
