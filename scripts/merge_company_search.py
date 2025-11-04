#!/usr/bin/env python3
"""
sbir-etl/scripts/merge_company_search.py

Merge multiple SBIR.gov "company_search" CSV files into a single canonical
companies_merged.csv file.

Strategy
--------
1. Read all CSV files matching a pattern (default: data/raw/sbir/company_search_*.csv).
2. Normalize key identifiers:
   - UEI: strip non-alphanumeric, uppercase
   - DUNS: strip non-digits
   - Company name: lowercase, strip punctuation/extra spaces for deduping
3. Deduplication / canonicalization policy:
   - Prefer rows with UEI (unique by UEI_clean). When multiple rows share the same
     UEI, pick the row with the most non-empty key fields (URL, address, city, state, ZIP).
   - For rows without UEI, prefer rows with DUNS (unique by DUNs_clean), selected
     similarly by the most-complete row.
   - For remaining rows (no UEI, no DUNS), dedupe by normalized company name and
     pick the best row by the same completeness metric.
4. Output:
   - Canonical CSV at `data/raw/sbir/companies_merged.csv` (configurable).
   - Optional JSON diagnostics with counts and simple provenance.

Usage
-----
python sbir-etl/scripts/merge_company_search.py \
    --input-dir data/raw/sbir \
    --pattern "company_search_*.csv" \
    --output data/raw/sbir/companies_merged.csv \
    --diagnostics reports/companies_merge_diagnostics.json
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


try:
    import pandas as pd
except Exception as e:  # pragma: no cover - runtime guard
    raise RuntimeError("pandas is required to run this script. Please install pandas.") from e


# ---- Normalization helpers ----
def clean_uei(v: str | None) -> str:
    """Strip non-alphanumeric and uppercase."""
    if not v or str(v).strip() == "":
        return ""
    return "".join(ch for ch in str(v) if ch.isalnum()).upper()


def clean_duns(v: str | None) -> str:
    """Strip non-digits."""
    if not v or str(v).strip() == "":
        return ""
    return "".join(ch for ch in str(v) if ch.isdigit())


def normalize_name(v: str | None) -> str:
    """Lowercase, remove punctuation, collapse whitespace."""
    if not v or str(v).strip() == "":
        return ""
    s = str(v).strip().lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---- Canonical selection helpers ----
KEY_FIELDS_FOR_COMPLETENESS = [
    "Company URL",
    "Address 1",
    "Address 2",
    "City",
    "State",
    "ZIP",
    # include UEI / DUNs themselves in scored completeness
    "UEI",
    "DUNs",
    "Number Awards",
]


def completeness_score(row: pd.Series, keys: Iterable[str] = KEY_FIELDS_FOR_COMPLETENESS) -> int:
    """Compute a simple completeness score: number of non-empty fields among a selection."""
    score = 0
    for k in keys:
        if k in row.index:
            v = row.get(k)
            if v is None:
                continue
            s = str(v).strip()
            if s != "":
                score += 1
    return score


def choose_preferred_row(df: pd.DataFrame) -> pd.Series:
    """
    Given a DataFrame of candidate rows (same schema), choose the preferred canonical row.
    Preference order:
      - highest completeness score
      - if tie, prefer non-empty UEI
      - if tie, prefer non-empty DUNs
      - if tie, prefer non-empty Company URL
      - else first occurrence
    """
    if df.shape[0] == 1:
        return df.iloc[0]
    scores = df.apply(lambda r: completeness_score(r), axis=1)
    max_score = int(scores.max())
    candidates = df[scores == max_score].copy()
    # prefer UEI
    if "UEI" in candidates.columns:
        cand_with_uei = candidates[candidates["UEI"].astype(str).str.strip() != ""]
        if len(cand_with_uei) == 1:
            return cand_with_uei.iloc[0]
        if len(cand_with_uei) > 1:
            candidates = cand_with_uei
    # prefer DUNs
    duns_cols = [c for c in candidates.columns if c.lower().startswith("dun")]
    if duns_cols:
        dcol = duns_cols[0]
        cand_with_duns = candidates[candidates[dcol].astype(str).str.strip() != ""]
        if len(cand_with_duns) == 1:
            return cand_with_duns.iloc[0]
        if len(cand_with_duns) > 1:
            candidates = cand_with_duns
    # prefer URL
    if "Company URL" in candidates.columns:
        cand_with_url = candidates[candidates["Company URL"].astype(str).str.strip() != ""]
        if len(cand_with_url) == 1:
            return cand_with_url.iloc[0]
        if len(cand_with_url) > 1:
            candidates = cand_with_url
    # fallback: first row (preserve order as in original concatenation)
    return candidates.iloc[0]


# ---- Main merge process ----
@dataclass
class MergeDiagnostics:
    total_input_rows: int = 0
    unique_by_uei: int = 0
    unique_by_duns: int = 0
    leftover_rows: int = 0
    canonical_count: int = 0
    sources: dict[str, int] = None

    def to_dict(self):
        # Ensure all numeric values are native Python ints so json.dump won't fail
        sources_clean = {}
        if self.sources:
            for k, v in (self.sources or {}).items():
                try:
                    sources_clean[k] = int(v)
                except Exception:
                    # Fallback: convert to string if it can't be cast to int
                    sources_clean[k] = str(v)
        return {
            "total_input_rows": int(self.total_input_rows),
            "unique_by_uei": int(self.unique_by_uei),
            "unique_by_duns": int(self.unique_by_duns),
            "leftover_rows": int(self.leftover_rows),
            "canonical_count": int(self.canonical_count),
            "sources": sources_clean,
        }


def find_company_search_files(input_dir: Path, pattern: str = "company_search_*.csv") -> list[Path]:
    """List matching CSV files in input_dir (non-recursive)."""
    p = Path(input_dir)
    if not p.exists() or not p.is_dir():
        return []
    return sorted(p.glob(pattern))


def read_and_concatenate(files: Iterable[Path]) -> pd.DataFrame:
    """Read all CSVs into a single DataFrame, preserving source filename."""
    frames = []
    for f in files:
        try:
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
        except Exception as e:
            # If reading fails for a single file, continue with others and log in diagnostics
            print(f"Warning: failed to read {f}: {e}")
            continue
        df["__source_file"] = f.name
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def merge_company_search_files(
    input_dir: Path,
    pattern: str = "company_search_*.csv",
    output_path: Path = Path("data/raw/sbir/companies_merged.csv"),
    diagnostics_path: Path | None = None,
) -> MergeDiagnostics:
    files = find_company_search_files(input_dir, pattern)
    if not files:
        raise FileNotFoundError(f"No company search files found in {input_dir} matching {pattern}")
    df = read_and_concatenate(files)
    diag = MergeDiagnostics()
    diag.total_input_rows = len(df)
    diag.sources = dict(df["__source_file"].value_counts())

    # Normalize key fields
    # Standardize company name column detection
    company_col_candidates = ["Company Name", "company", "Company"]
    company_col = next((c for c in company_col_candidates if c in df.columns), None)
    if company_col is None:
        # Fallback: use first column
        company_col = df.columns[0] if len(df.columns) > 0 else None

    # Ensure UEI and DUNs columns exist (create empty if missing)
    uei_col = "UEI"
    duns_col = None
    for c in df.columns:
        if c.strip().lower().startswith("dun"):
            duns_col = c
            break
    if duns_col is None:
        # Create a column to standardize downstream code
        duns_col = "DUNs"
        df[duns_col] = ""

    # Add cleaned fields
    df["UEI_clean"] = df.get(uei_col, "").astype(str).map(clean_uei)
    df["DUNs_clean"] = df.get(duns_col, "").astype(str).map(clean_duns)
    df["_norm_name"] = df[company_col].astype(str).map(normalize_name)

    # STEP 1: Keep one canonical row per UEI (where UEI_clean is non-empty)
    uei_rows = df[df["UEI_clean"] != ""].copy()
    if len(uei_rows) > 0:
        # group by UEI_clean, choose preferred row per UEI
        canonical_by_uei = []
        for _uei, group in uei_rows.groupby("UEI_clean", sort=False):
            chosen = choose_preferred_row(group)
            canonical_by_uei.append(chosen)
        df_uei = pd.DataFrame(canonical_by_uei)
        diag.unique_by_uei = len(df_uei)
    else:
        df_uei = pd.DataFrame(columns=df.columns)
        diag.unique_by_uei = 0

    # Remove rows with UEI from consideration
    remaining = df[~df.index.isin(df_uei.index)].copy()

    # STEP 2: For remaining, keep unique by DUNs_clean where present
    duns_rows = remaining[remaining["DUNs_clean"] != ""].copy()
    if len(duns_rows) > 0:
        canonical_by_duns = []
        for _duns, group in duns_rows.groupby("DUNs_clean", sort=False):
            chosen = choose_preferred_row(group)
            canonical_by_duns.append(chosen)
        df_duns = pd.DataFrame(canonical_by_duns)
        diag.unique_by_duns = len(df_duns)
    else:
        df_duns = pd.DataFrame(columns=df.columns)
        diag.unique_by_duns = 0

    # Remove DUNs rows from remaining
    remaining = remaining[~remaining.index.isin(df_duns.index)].copy()

    # STEP 3: Deduplicate leftover by normalized name (simple approach)
    # For large corpora you might prefer clustering/fuzzy grouping — keep simple here.
    leftover = remaining.copy()
    diag.leftover_rows = len(leftover)
    if len(leftover) > 0:
        # Drop duplicates by normalized name keeping the most complete row per normalized name
        chosen_leftover = []
        for norm, group in leftover.groupby("_norm_name", sort=False):
            if not norm:
                # If name empty, treat individually and just pick the most complete row
                chosen_leftover.append(choose_preferred_row(group))
            else:
                chosen_leftover.append(choose_preferred_row(group))
        df_leftover = pd.DataFrame(chosen_leftover)
    else:
        df_leftover = pd.DataFrame(columns=df.columns)

    # Combine canonical sets
    canonical = pd.concat([df_uei, df_duns, df_leftover], ignore_index=True, sort=False)

    # Final cleanup: remove helper columns if desired, but keep UEI_clean/DUNs_clean for debugging
    # We'll write canonical rows with original columns plus UEI_clean and DUNs_clean.
    # Also include explicit canonical columns 'company' and 'company_url' if present so downstream
    # enrichment code can use consistent column names regardless of source header variants.
    # Reorder columns: original columns first, then canonical company columns (if present),
    # then UEI_clean, DUNs_clean, and source metadata.
    orig_cols = [
        c for c in df.columns if c not in ("UEI_clean", "DUNs_clean", "_norm_name", "__source_file")
    ]
    # Collect any canonical columns that may have been added
    extra_canonical_cols = []
    if "company" in canonical.columns:
        extra_canonical_cols.append("company")
    if "company_url" in canonical.columns:
        extra_canonical_cols.append("company_url")
    final_cols = orig_cols + extra_canonical_cols + ["UEI_clean", "DUNs_clean", "__source_file"]
    canonical = canonical.loc[:, [c for c in final_cols if c in canonical.columns]]

    # Write output
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canonical.to_csv(out_path, index=False)

    diag.canonical_count = len(canonical)

    # Optionally write diagnostics JSON
    if diagnostics_path:
        diagnostics_path = Path(diagnostics_path)
        diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
        with diagnostics_path.open("w", encoding="utf-8") as fh:
            json.dump(diag.to_dict(), fh, indent=2)

    return diag


# ---- CLI ----
def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Merge company_search CSVs into canonical companies_merged.csv"
    )
    parser.add_argument(
        "--input-dir", "-i", default="data/raw/sbir", help="Directory with company_search CSVs"
    )
    parser.add_argument(
        "--pattern", "-p", default="company_search_*.csv", help="Filename glob pattern"
    )
    parser.add_argument(
        "--output", "-o", default="data/raw/sbir/companies_merged.csv", help="Output path"
    )
    parser.add_argument(
        "--diagnostics",
        "-d",
        default="reports/companies_merge_diagnostics.json",
        help="Diagnostics JSON path",
    )
    args = parser.parse_args(argv)

    input_dir = Path(args.input_dir)
    try:
        diag = merge_company_search_files(
            input_dir=input_dir,
            pattern=args.pattern,
            output_path=Path(args.output),
            diagnostics_path=Path(args.diagnostics),
        )
    except Exception as e:
        print(f"ERROR: {e}")
        return 2

    print("Merge complete.")
    print(json.dumps(diag.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
