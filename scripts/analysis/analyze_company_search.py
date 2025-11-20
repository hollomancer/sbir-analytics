#!/usr/bin/env python3
"""
sbir-analytics/scripts/analyze_company_search.py

Analyze a SBIR.gov "company_search" CSV and estimate enrichment value vs an awards CSV.

This script:
- Reads a company_search CSV (many company rows) and an awards CSV (award rows).
- Summarizes company CSV: UEI/DUNS coverage, address completeness, URL presence,
  common states, unique company name counts, and duplicates.
- Estimates enrichment potential:
  - Exact UEI join coverage for awards
  - Exact DUNS join coverage for awards
  - Additional fuzzy-name matches (token-based) among unmatched awards using rapidfuzz
- Writes a Markdown report and a JSON diagnostics file with details.

Usage:
    python sbir-analytics/scripts/analyze_company_search.py \
        --company data/raw/sbir/company_search_1761473980.csv \
        --awards tests/fixtures/sbir_sample.csv \
        --out reports/company_search_analysis.md \
        --json reports/company_search_analysis.json

Notes:
- Requires pandas and rapidfuzz (for best fuzzy matching). If rapidfuzz is not available,
  the script will fall back to Python's difflib for approximate matching (lower quality).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# Optional dependencies
try:
    import pandas as pd
except Exception as e:  # pragma: no cover - runtime guard
    raise RuntimeError("pandas is required to run this script. Install via pip.") from e

# Prefer rapidfuzz for fuzzy matching; fallback to difflib if not installed
try:
    from rapidfuzz import fuzz, process  # type: ignore

    _RAPIDFUZZ_AVAILABLE = True
except Exception:
    _RAPIDFUZZ_AVAILABLE = False


# -------------------------
# Helpers
# -------------------------
def normalize_name_for_matching(s: str | None) -> str:
    """Normalize name for matching using centralized utility.
    
    Uses centralized text normalization utility with suffix normalization.
    """
    from src.utils.text_normalization import normalize_name as normalize_name_util
    
    return normalize_name_util(s, remove_suffixes=False)


def digits_only(s: str | None) -> str:
    if not s:
        return ""
    return "".join(ch for ch in str(s) if ch.isdigit())


def alnum_upper(s: str | None) -> str:
    if not s:
        return ""
    return "".join(ch for ch in str(s) if ch.isalnum()).upper()


def pct(n: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(100.0 * n / total, 2)


# -------------------------
# Analysis functions
# -------------------------
@dataclass
class CompanySummary:
    total_rows: int
    uei_nonnull: int
    duns_nonnull: int
    url_nonnull: int
    addr1_nonnull: int
    addr2_nonnull: int
    city_nonnull: int
    state_nonnull: int
    zip_nonnull: int
    unique_names: int
    top_states: list[tuple[str, int]]
    top_domains: list[tuple[str, int]]
    duplicate_name_count: int


def summarize_company_csv(df: pd.DataFrame) -> CompanySummary:
    total = len(df)
    uei_nonnull = df.get("UEI", "").replace("", pd.NA).dropna().shape[0]
    # DUNs column sometimes spelled differently: detect likely names
    duns_col = None
    for c in ("DUNs", "Duns", "DUN"):
        if c in df.columns:
            duns_col = c
            break
    if duns_col is None:
        duns_nonnull = 0
    else:
        duns_nonnull = df.get(duns_col, "").replace("", pd.NA).dropna().shape[0]

    url_nonnull = df.get("Company URL", "").replace("", pd.NA).dropna().shape[0]
    addr1_nonnull = df.get("Address 1", "").replace("", pd.NA).dropna().shape[0]
    addr2_nonnull = df.get("Address 2", "").replace("", pd.NA).dropna().shape[0]
    city_nonnull = df.get("City", "").replace("", pd.NA).dropna().shape[0]
    state_nonnull = df.get("State", "").replace("", pd.NA).dropna().shape[0]
    zip_nonnull = df.get("ZIP", "").replace("", pd.NA).dropna().shape[0]

    # Company Name column variants
    company_col = None
    for c in ("Company Name", "company", "Company"):
        if c in df.columns:
            company_col = c
            break
    if company_col is None:
        unique_names = 0
        duplicate_name_count = 0
    else:
        names = df[company_col].fillna("").astype(str)
        unique_names = names.replace("", pd.NA).dropna().nunique()
        dup_counts = names.value_counts()
        duplicate_name_count = int((dup_counts > 1).sum())

    top_states = []
    if "State" in df.columns:
        top_states = list(df["State"].fillna("").value_counts().head(10).items())

    # Derive domain from Company URL for top domains
    top_domains = []
    if "Company URL" in df.columns:
        domains = []
        for u in df["Company URL"].fillna("").astype(str):
            if not u:
                continue
            # naive domain extraction
            m = re.search(r"https?://([^/]+)", u)
            if m:
                domains.append(m.group(1).lower())
            else:
                domains.append(u.split("/")[0].lower() if "/" in u else u.lower())
        top_domains = list(Counter(domains).most_common(10))

    return CompanySummary(
        total_rows=total,
        uei_nonnull=uei_nonnull,
        duns_nonnull=duns_nonnull,
        url_nonnull=url_nonnull,
        addr1_nonnull=addr1_nonnull,
        addr2_nonnull=addr2_nonnull,
        city_nonnull=city_nonnull,
        state_nonnull=state_nonnull,
        zip_nonnull=zip_nonnull,
        unique_names=unique_names,
        top_states=top_states,
        top_domains=top_domains,
        duplicate_name_count=duplicate_name_count,
    )


def estimate_enrichment_value(
    companies_df: pd.DataFrame,
    awards_df: pd.DataFrame,
    company_name_col: str = "Company Name",
    awards_company_col: str = "Company",
    uei_col: str = "UEI",
    duns_col_candidates: Sequence[str] = ("DUNs", "Duns"),
    high_threshold: int = 90,
    med_threshold: int = 75,
    fuzzy_limit: int = 1,
) -> dict[str, object]:
    """
    Compute:
    - counts of exact matches by UEI and DUNs
    - counts of potential fuzzy matches among unmatched awards using token-based scorer
    """
    # Prepare company maps
    comp = companies_df.copy()
    comp_cols = comp.columns.tolist()
    # Normalize company name col detection
    if company_name_col not in comp_cols:
        # try to find 'Company Name' header variants
        for c in comp_cols:
            if c.strip().lower() in ("company name", "company"):
                company_name_col = c
                break
    comp_names = comp[company_name_col].fillna("").astype(str)

    # UEI map
    comp_uei_map = {}
    if uei_col in comp.columns:
        for idx, v in comp[uei_col].fillna("").astype(str).items():
            k = alnum_upper(v)
            if k:
                comp_uei_map[k] = idx

    # DUNS map (clean digits)
    duns_col = None
    for cand in duns_col_candidates:
        if cand in comp.columns:
            duns_col = cand
            break
    comp_duns_map = {}
    if duns_col:
        for idx, v in comp[duns_col].fillna("").astype(str).items():
            k = digits_only(v)
            if k:
                comp_duns_map[k] = idx

    # Awards identifiers
    awards = awards_df.copy()
    awards_cols = awards.columns.tolist()
    # Compute cleaned UEI and DUNs on awards if present
    if "UEI" in awards_cols:
        awards["UEI_clean"] = awards["UEI"].fillna("").astype(str).map(alnum_upper)
    else:
        awards["UEI_clean"] = ""

    # find Duns column name in awards if present
    award_duns_col = None
    for cand in duns_col_candidates:
        if cand in awards_cols:
            award_duns_col = cand
            break
    if award_duns_col:
        awards["Duns_clean"] = awards[award_duns_col].fillna("").astype(str).map(digits_only)
    else:
        awards["Duns_clean"] = ""

    total_awards = len(awards)

    # Exact matches
    exact_uei_matches = awards["UEI_clean"].apply(lambda u: (u != "") and (u in comp_uei_map)).sum()
    exact_duns_matches = (
        awards["Duns_clean"].apply(lambda d: (d != "") and (d in comp_duns_map)).sum()
    )
    exact_either = int(
        (
            (awards["UEI_clean"].apply(lambda u: u in comp_uei_map if u else False))
            | (awards["Duns_clean"].apply(lambda d: d in comp_duns_map if d else False))
        ).sum()
    )

    # Unmatched awards (by identifiers)
    unmatched_mask = ~(
        awards["UEI_clean"].apply(lambda u: bool(u and (u in comp_uei_map)))
        | awards["Duns_clean"].apply(lambda d: bool(d and (d in comp_duns_map)))
    )
    unmatched_awards = awards[unmatched_mask].copy()

    # Prepare fuzzy matching choices (normalized company names)
    comp_norm_map = {i: normalize_name_for_matching(n) for i, n in comp_names.items() if n}
    # Use rapidfuzz if available, else difflib fallback
    fuzzy_high = 0
    fuzzy_med = 0
    fuzzy_examples = []

    if len(unmatched_awards) == 0:
        fuzzy_high = fuzzy_med = 0
    else:
        # We'll run fuzzy matching on a small sample to estimate potential
        sample = unmatched_awards.head(200)  # conservative sample to estimate
        if _RAPIDFUZZ_AVAILABLE:
            for _, r in sample.iterrows():
                tgt = normalize_name_for_matching(
                    str(
                        r.get(awards_company_col, "") or r.get(awards_company_col.lower(), "") or ""
                    )
                )
                if not tgt:
                    continue
                res = process.extractOne(tgt, comp_norm_map, scorer=fuzz.token_set_ratio)
                if not res:
                    continue
                match_value, score, key = res
                if score >= high_threshold:
                    fuzzy_high += 1
                elif score >= med_threshold:
                    fuzzy_med += 1
                if len(fuzzy_examples) < 5:
                    fuzzy_examples.append(
                        {
                            "award_company": r.get(awards_company_col, ""),
                            "best_match": match_value,
                            "score": score,
                        }
                    )
        else:
            # difflib fallback
            from difflib import SequenceMatcher

            choices = list(comp_norm_map.items())
            for _, r in sample.iterrows():
                tgt = normalize_name_for_matching(str(r.get(awards_company_col, "") or ""))
                if not tgt:
                    continue
                best_score = 0.0
                best_name = ""
                for idx, cname in choices:
                    score = SequenceMatcher(None, tgt, cname).ratio() * 100.0
                    if score > best_score:
                        best_score = score
                        best_name = cname
                if best_score >= high_threshold:
                    fuzzy_high += 1
                elif best_score >= med_threshold:
                    fuzzy_med += 1
                if len(fuzzy_examples) < 5:
                    fuzzy_examples.append(
                        {
                            "award_company": r.get(awards_company_col, ""),
                            "best_match": best_name,
                            "score": best_score,
                        }
                    )

    # Extrapolate fuzzy hits proportionally from sample to full unmatched set, if sample smaller
    sample_size = min(len(unmatched_awards), 200)
    total_unmatched = len(unmatched_awards)
    if sample_size > 0 and sample_size < total_unmatched:
        fuzzy_high_est = int(round((fuzzy_high / sample_size) * total_unmatched))
        fuzzy_med_est = int(round((fuzzy_med / sample_size) * total_unmatched))
    else:
        fuzzy_high_est = fuzzy_high
        fuzzy_med_est = fuzzy_med

    diagnostics = {
        "company_rows": len(comp),
        "company_columns": comp.columns.tolist(),
        "company_summary": {
            "uei_nonnull": int(comp.get("UEI", "").replace("", pd.NA).dropna().shape[0]),
            "duns_nonnull": int(
                (comp.get(duns_col, "").replace("", pd.NA).dropna().shape[0]) if duns_col else 0
            ),
            "url_nonnull": int(comp.get("Company URL", "").replace("", pd.NA).dropna().shape[0])
            if "Company URL" in comp.columns
            else 0,
            "addr1_nonnull": int(comp.get("Address 1", "").replace("", pd.NA).dropna().shape[0])
            if "Address 1" in comp.columns
            else 0,
            "state_counts": comp.get("State", "").value_counts().to_dict()
            if "State" in comp.columns
            else {},
        },
        "awards_rows": total_awards,
        "exact_uei_matches": int(exact_uei_matches),
        "exact_duns_matches": int(exact_duns_matches),
        "exact_either_matches": int(exact_either),
        "unmatched_awards": int(total_awards - exact_either),
        "fuzzy_estimates": {
            "sample_size": sample_size,
            "fuzzy_high_sample": int(fuzzy_high),
            "fuzzy_med_sample": int(fuzzy_med),
            "fuzzy_high_estimated_total": int(fuzzy_high_est),
            "fuzzy_med_estimated_total": int(fuzzy_med_est),
            "fuzzy_examples": fuzzy_examples,
        },
    }

    return diagnostics


# -------------------------
# Reporting
# -------------------------
def render_markdown_report(out_path: Path, diagnostics: dict[str, object]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write("# Company Search Enrichment Analysis\n\n")
        fh.write(f"Generated: {datetime.utcnow().isoformat()} UTC\n\n")
        fh.write("## Summary\n\n")
        fh.write(f"- Company rows: **{diagnostics['company_rows']}**\n")
        fh.write(f"- Awards rows: **{diagnostics['awards_rows']}**\n\n")
        fh.write("## Identifier coverage\n\n")
        cs = diagnostics["company_summary"]
        fh.write(f"- UEI non-null: **{cs.get('uei_nonnull',0)}**\n")
        fh.write(f"- DUNS non-null: **{cs.get('duns_nonnull',0)}**\n")
        fh.write(f"- Company URLs present: **{cs.get('url_nonnull',0)}**\n\n")
        fh.write("## Exact match counts (awards -> companies)\n\n")
        fh.write(f"- Exact UEI matches: **{diagnostics['exact_uei_matches']}**\n")
        fh.write(f"- Exact DUNS matches: **{diagnostics['exact_duns_matches']}**\n")
        fh.write(f"- Exact (UEI or DUNS) matches: **{diagnostics['exact_either_matches']}**\n\n")
        fh.write("## Fuzzy match estimates (sample-based)\n\n")
        fe = diagnostics["fuzzy_estimates"]
        fh.write(f"- Sample size used for fuzzy estimate: **{fe['sample_size']}**\n")
        fh.write(
            f"- High-confidence fuzzy matches in sample (>= threshold): **{fe['fuzzy_high_sample']}**\n"
        )
        fh.write(
            f"- Medium-confidence fuzzy matches in sample (>= threshold): **{fe['fuzzy_med_sample']}**\n"
        )
        fh.write(
            f"- Estimated high-confidence matches in full unmatched set: **{fe['fuzzy_high_estimated_total']}**\n"
        )
        fh.write(
            f"- Estimated medium-confidence matches in full unmatched set: **{fe['fuzzy_med_estimated_total']}**\n\n"
        )
        fh.write("Top fuzzy match examples (from sample):\n\n")
        for ex in fe.get("fuzzy_examples", []):
            fh.write(
                f"- Award company: {ex.get('award_company')} → Best match: {ex.get('best_match')} (score {ex.get('score')})\n"
            )
        fh.write("\n---\n")
        fh.write("Recommendations:\n\n")
        fh.write("1. Use UEI and DUNS for exact enrichment where present (deterministic).\n")
        fh.write(
            "2. Use fuzzy matching (token-based) as a conservative fallback; accept only high-score matches automatically.\n"
        )
        fh.write(
            "3. Persist match score & method on enriched awards for auditing and manual review of medium-confidence candidates.\n"
        )
        fh.write(
            "4. Consider additional blocking (state/zip) to reduce candidate set size for large company corpora.\n"
        )


def write_json(out_path: Path, diagnostics: dict[str, object]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(diagnostics, fh, indent=2, default=str)


# -------------------------
# CLI
# -------------------------
def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze a company_search CSV and estimate enrichment value vs awards CSV."
    )
    parser.add_argument(
        "--company",
        "-c",
        required=True,
        help="Path to company_search CSV file (company rows).",
    )
    parser.add_argument(
        "--awards",
        "-a",
        required=True,
        help="Path to awards CSV file (award rows) to estimate enrichment against.",
    )
    parser.add_argument(
        "--out",
        "-o",
        default="reports/company_search_analysis.md",
        help="Output Markdown report path.",
    )
    parser.add_argument(
        "--json",
        "-j",
        default="reports/company_search_analysis.json",
        help="Output JSON diagnostics path.",
    )
    parser.add_argument(
        "--high", type=int, default=90, help="High threshold for fuzzy accept (0-100)"
    )
    parser.add_argument(
        "--med", type=int, default=75, help="Medium threshold for fuzzy candidate (0-100)"
    )
    args = parser.parse_args(argv)

    company_path = Path(args.company)
    awards_path = Path(args.awards)
    out_md = Path(args.out)
    out_json = Path(args.json)

    if not company_path.exists():
        print(f"Company CSV not found: {company_path}")
        return 2
    if not awards_path.exists():
        print(f"Awards CSV not found: {awards_path}")
        return 3

    companies = pd.read_csv(company_path, dtype=str, keep_default_na=False)
    awards = pd.read_csv(awards_path, dtype=str, keep_default_na=False)

    summary = summarize_company_csv(companies)
    diagnostics = estimate_enrichment_value(
        companies,
        awards,
        company_name_col="Company Name"
        if "Company Name" in companies.columns
        else companies.columns[0],
        awards_company_col="Company",
        uei_col="UEI",
        duns_col_candidates=("DUNs", "Duns"),
        high_threshold=args.high,
        med_threshold=args.med,
    )

    # augment diagnostics with company summary counts
    diagnostics["company_summary_brief"] = {
        "total_rows": summary.total_rows,
        "uei_nonnull": summary.uei_nonnull,
        "duns_nonnull": summary.duns_nonnull,
        "url_nonnull": summary.url_nonnull,
        "unique_names": summary.unique_names,
        "duplicate_name_count": summary.duplicate_name_count,
    }

    render_markdown_report(out_md, diagnostics)
    write_json(out_json, diagnostics)

    print(f"Analysis complete. Report: {out_md} ; Diagnostics: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
