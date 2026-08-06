#!/usr/bin/env python3
"""CLI entry point for the exploratory phase-transition report."""

import sys
from pathlib import Path

EPISTEMIC_TIER = "exploratory"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sbir_etl.reporting.phase_transition_analysis import main  # noqa: E402


if __name__ == "__main__":
    main()
