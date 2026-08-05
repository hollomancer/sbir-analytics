"""Two-list capture arithmetic with explicit dependence and precision assumptions."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from pathlib import Path


def chapman_independence(
    code_total: int, description_total: int, overlap: int
) -> dict[str, float | str]:
    """Chapman total/dark scenario and Wald CI under homogeneous independence."""
    if min(code_total, description_total, overlap) < 0 or overlap > min(
        code_total, description_total
    ):
        raise ValueError("invalid two-list counts")
    if overlap == 0:
        raise ValueError("Chapman scenario requires a nonzero overlap")
    total = ((code_total + 1) * (description_total + 1) / (overlap + 1)) - 1
    observed = code_total + description_total - overlap
    variance = (
        (code_total + 1)
        * (description_total + 1)
        * (code_total - overlap)
        * (description_total - overlap)
        / ((overlap + 1) ** 2 * (overlap + 2))
    )
    se = math.sqrt(variance)
    return {
        "assumption": "homogeneous independent capture (list odds ratio = 1)",
        "total": total,
        "dark": total - observed,
        "standard_error": se,
        "dark_ci_low": total - observed - 1.96 * se,
        "dark_ci_high": total - observed + 1.96 * se,
    }


def odds_ratio_dark(
    code_only: int, description_only: int, overlap: int, odds_ratio: float
) -> float:
    """Implied missing cell for a specified 2x2 list odds ratio."""
    if overlap <= 0 or odds_ratio < 0 or min(code_only, description_only) < 0:
        raise ValueError("invalid sensitivity inputs")
    return odds_ratio * code_only * description_only / overlap


def capture_sensitivity(
    code_only: int,
    description_only: int,
    overlap: int,
    *,
    odds_ratios: Sequence[float] = (0.5, 1.0, 2.0, 5.0),
    description_only_false_positives: Sequence[int] = (0, 5, 10, 20),
) -> dict[str, object]:
    """Return assumption-indexed dark-cell and list-precision scenarios."""
    code_total = code_only + overlap
    description_total = description_only + overlap
    return {
        "status": "provisional",
        "cells": {"code_only": code_only, "description_only": description_only, "overlap": overlap},
        "chapman_or1_scenario": chapman_independence(code_total, description_total, overlap),
        "odds_ratio_sensitivity": [
            {
                "list_odds_ratio": value,
                "dark": odds_ratio_dark(code_only, description_only, overlap, value),
            }
            for value in odds_ratios
        ],
        "description_false_positive_sensitivity": [
            {
                "false_positives_removed": count,
                "remaining_description_only": description_only - count,
                "chapman_or1_dark": chapman_independence(
                    code_total, description_total - count, overlap
                )["dark"],
            }
            for count in description_only_false_positives
            if 0 <= count <= description_only
        ],
        "warnings": [
            "the sign and magnitude of list dependence are not identified by two observed lists",
            "the Chapman interval is conditional on independence, not an interval under unspecified dependence",
            "list precision and linkage error must be adjudicated",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-only", type=int, required=True)
    parser.add_argument("--description-only", type=int, required=True)
    parser.add_argument("--overlap", type=int, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = capture_sensitivity(args.code_only, args.description_only, args.overlap)
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
