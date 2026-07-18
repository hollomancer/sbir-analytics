"""Describe the coded DoD Phase III text available to Phase II firms.

Every richness/negative experiment so far ran on NASA TechPort (rich descriptions). The memo's spine is DoD,
which carries most program dollars. Same-firm overlap is a proxy cohort, not
verified technical lineage, and description sparsity is not proven to cause
element-10Q miscoding.

Positive = a firm holding both a DoD Phase II SBIR award (query side, has an abstract) and a coded DoD Phase
III contract (target side, m0a_coded_dod). Target text = that contract's `desc`.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def target_text_coverage(lengths: np.ndarray, floor: int = 150) -> dict[str, float]:
    """Share of Phase III target descriptions usable by a text ranker. Pure."""
    n = len(lengths)
    if n == 0:
        return {"n": 0, "median_chars": 0.0, "pct_usable": 0.0, "pct_below_floor": 0.0}
    return {"n": int(n), "median_chars": float(np.median(lengths)),
            "pct_usable": round(100 * float((lengths >= floor).mean()), 1),
            "pct_below_floor": round(100 * float((lengths < floor).mean()), 1)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--coded", type=Path, default=Path("data/derived/m0a_coded_dod.parquet"))
    parser.add_argument("--floor", type=int, default=150, help="min target chars for the rich-text regime")
    args = parser.parse_args(argv)

    awards = pd.read_csv(args.awards, dtype=str, keep_default_na=False)
    awards = awards[(awards["UEI"].str.len() > 5) & (awards["Agency"] == "Department of Defense")]
    phase2 = awards[awards["Phase"].str.contains("II", na=False)
                    & ~awards["Phase"].str.contains("III", na=False)]
    p2_firms = set(phase2["UEI"])

    coded = pd.read_parquet(args.coded)
    p3_firms = set(coded["uei"].dropna())
    positive_firms = p2_firms & p3_firms
    positives = coded[coded["uei"].isin(positive_firms)]

    print(f"DoD Phase II SBIR firms: {len(p2_firms)}  |  coded DoD Phase III firms: {len(p3_firms)}")
    print(f"POSITIVE firms (both Phase II and Phase III): {len(positive_firms)}")
    print(f"POSITIVE Phase III contracts (linkable to a Phase II of same firm): {len(positives)}\n")

    cov = target_text_coverage(positives["desc"].astype(str).str.len().to_numpy(), args.floor)
    print(f"Target text = Phase III 'desc': median {cov['median_chars']:.0f} chars")
    print(f"  usable (>= {args.floor} chars): {cov['pct_usable']}%   below floor: {cov['pct_below_floor']}%")
    print("\n  These are coded same-firm proxy targets. Description coverage is reported without a causal claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
