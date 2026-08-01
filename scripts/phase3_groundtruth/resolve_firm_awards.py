#!/usr/bin/env python3
"""Resolve a success-story firm name to its SBIR awards in award_data.csv.

Phase-III success stories name the firm in prose ("Acme Photonics, Inc."), often
with a slightly different spelling than the SBIR award record. This resolves a
firm name to that firm's SBIR awards — UEI, contract numbers, topics — the
identifiers the ranker validation (specs/phase3-transition-groundtruth) needs to
turn a narrative into a scorable case.

Matching is exact-on-normalized-name first, then token-set fuzzy (rapidfuzz)
above a threshold, so "Acme Photonics" resolves to "ACME PHOTONICS INC" without
also grabbing "Acme Robotics". Every match reports its score and method so a
human can spot-check the fuzzy ones.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process


_SUFFIX_RE = re.compile(
    r"\b(INC|INCORPORATED|LLC|L\.?L\.?C|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLP|PC|PLLC)\b\.?",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^A-Z0-9 ]")

FUZZY_THRESHOLD = 88.0


def normalize_name(name: object) -> str:
    """Uppercase, drop legal suffixes and punctuation, collapse whitespace."""

    text = _SUFFIX_RE.sub(" ", str(name or "").upper())
    text = _NON_ALNUM.sub(" ", text)
    return " ".join(text.split())


@dataclass
class FirmResolution:
    query: str
    matched_company: str | None
    match_method: str  # "exact" | "fuzzy" | "none"
    match_score: float
    ueis: list[str] = field(default_factory=list)
    contracts: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    award_count: int = 0


@lru_cache(maxsize=1)
def _load_awards(path: str) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        usecols=["Company", "UEI", "Contract", "Topic Code", "Agency", "Branch", "Phase"],
        dtype=str,
    )
    df["name_key"] = df["Company"].map(normalize_name)
    return df


def _collect(rows: pd.DataFrame, matched_company: str, method: str, score: float, query: str):
    def _uniq(series: pd.Series) -> list[str]:
        return sorted({str(v).strip() for v in series.dropna() if str(v).strip()})

    return FirmResolution(
        query=query,
        matched_company=matched_company,
        match_method=method,
        match_score=score,
        ueis=_uniq(rows["UEI"]),
        contracts=_uniq(rows["Contract"]),
        topics=_uniq(rows["Topic Code"]),
        award_count=len(rows),
    )


def resolve_firm(
    firm_name: str, award_data_path: str, *, threshold: float = FUZZY_THRESHOLD
) -> FirmResolution:
    """Resolve one firm name to its SBIR awards; exact-normalized, then fuzzy."""

    awards = _load_awards(award_data_path)
    key = normalize_name(firm_name)
    if not key:
        return FirmResolution(firm_name, None, "none", 0.0)

    exact = awards.loc[awards["name_key"] == key]
    if not exact.empty:
        return _collect(exact, str(exact["Company"].iloc[0]), "exact", 100.0, firm_name)

    # Fuzzy: score the query against the distinct known name keys.
    choices = awards["name_key"].dropna().unique().tolist()
    best = process.extractOne(key, choices, scorer=fuzz.token_set_ratio)
    if best is not None and best[1] >= threshold:
        matched_key = best[0]
        rows = awards.loc[awards["name_key"] == matched_key]
        return _collect(rows, str(rows["Company"].iloc[0]), "fuzzy", float(best[1]), firm_name)
    return FirmResolution(firm_name, None, "none", float(best[1]) if best else 0.0)


def resolve_many(firm_names: list[str], award_data_path: str) -> pd.DataFrame:
    resolutions = [resolve_firm(name, award_data_path) for name in firm_names]
    return pd.DataFrame(
        {
            "query": [r.query for r in resolutions],
            "matched_company": [r.matched_company for r in resolutions],
            "match_method": [r.match_method for r in resolutions],
            "match_score": [r.match_score for r in resolutions],
            "award_count": [r.award_count for r in resolutions],
            "ueis": [";".join(r.ueis) for r in resolutions],
            "contracts": [";".join(r.contracts) for r in resolutions],
            "topics": [";".join(r.topics) for r in resolutions],
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--firms",
        type=Path,
        required=True,
        help="Newline- or CSV-listed firm names (first column).",
    )
    parser.add_argument("--award-data", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument(
        "--output", type=Path, default=Path("data/derived/phase3_groundtruth_firm_resolution.csv")
    )
    args = parser.parse_args()

    text = args.firms.read_text(encoding="utf-8")
    names = [line.split(",")[0].strip().strip('"') for line in text.splitlines() if line.strip()]
    names = [n for n in names if n and n.lower() not in {"firm", "company", "firm_name"}]
    resolution = resolve_many(names, str(args.award_data))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    resolution.to_csv(args.output, index=False)
    resolved = int((resolution["match_method"] != "none").sum())
    print(f"resolved {resolved}/{len(resolution)} firms -> {args.output}")
    print(resolution["match_method"].value_counts().to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
