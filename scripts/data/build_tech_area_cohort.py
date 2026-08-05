#!/usr/bin/env python3
"""CLI entry point for the exploratory technology-area cohort engine."""

import sys
from pathlib import Path

EPISTEMIC_TIER = "exploratory"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sbir_etl.reporting.tech_area_cohort import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
