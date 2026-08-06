#!/usr/bin/env python3
"""CLI entry point for the USAspending database download pipeline."""

import sys
from pathlib import Path

EPISTEMIC_TIER = "pipelines"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sbir_etl.extractors.source_downloads.usaspending import main  # noqa: E402


if __name__ == "__main__":
    main()
