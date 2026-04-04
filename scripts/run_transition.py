#!/usr/bin/env python3
"""Run the transition detection MVP pipeline via Dagster.

Usage:
    python scripts/run_transition.py
    python scripts/run_transition.py --contracts-path data/contracts.parquet
    python scripts/run_transition.py --seed  # Create sample contracts if missing
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd
from loguru import logger

from sbir_etl.config.loader import get_config

from sbir_analytics.clients import DagsterClient

TRANSITION_ASSET_KEYS = [
    "validated_contracts_sample",
    "enriched_sbir_awards",
    "enriched_vendor_resolution",
    "transformed_transition_scores",
    "transformed_transition_evidence",
    "transformed_transition_detections",
]


def seed_contracts(path: str) -> None:
    """Create a minimal sample contracts file for testing."""
    df = pd.DataFrame(
        {
            "vendor_duns": ["123456789", "987654321"],
            "vendor_name": ["Acme Corp", "Beta Inc"],
            "contract_amount": [100000, 250000],
            "award_date": ["2023-01-15", "2023-06-20"],
        }
    )
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_parquet(path, index=False)
    logger.info(f"Seeded sample contracts to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run transition detection MVP pipeline")
    parser.add_argument("--contracts-path", help="Path to contracts sample file")
    parser.add_argument("--seed", action="store_true", help="Create sample contracts if missing")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    config = get_config()

    # Resolve contracts path
    contracts_path = args.contracts_path
    if not contracts_path:
        contracts_path = str(config.paths.resolve_path("transition/contracts_sample.parquet"))

    if args.seed and not os.path.exists(contracts_path):
        seed_contracts(contracts_path)

    # Set env var for Dagster assets
    if args.contracts_path:
        os.environ["SBIR_ETL__TRANSITION__CONTRACTS_SAMPLE__PATH"] = contracts_path

    # Trigger materialization
    client = DagsterClient(config)
    try:
        result = client.trigger_materialization(asset_keys=TRANSITION_ASSET_KEYS)
        if result.status == "success":
            print(f"Transition pipeline completed successfully (run_id={result.run_id})")
        else:
            print(f"Transition pipeline failed (run_id={result.run_id})", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        logger.error(f"Transition pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
