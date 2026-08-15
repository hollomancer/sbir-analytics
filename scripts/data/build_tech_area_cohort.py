#!/usr/bin/env python3
"""CLI entry point for the exploratory technology-area cohort engine."""

import sys
from pathlib import Path

EPISTEMIC_TIER = "exploratory"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sbir_etl.reporting.tech_area_cohort import main  # noqa: E402


def _deprecated_main() -> int:
    import warnings

    warnings.warn(
        "build_tech_area_cohort.py is a compatibility shim; prefer "
        "scripts/data/run_analysis.py --profile <area_id>",
        DeprecationWarning,
        stacklevel=2,
    )
    return main()


if __name__ == "__main__":
    raise SystemExit(_deprecated_main())
