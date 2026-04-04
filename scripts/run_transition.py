#!/usr/bin/env python3
"""Run the transition detection MVP pipeline via Dagster.

Usage:
    python scripts/run_transition.py
    python scripts/run_transition.py --contracts-path data/contracts.parquet
    python scripts/run_transition.py --no-seed
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

from sbir_etl.config.loader import get_config
from sbir_etl.utils.path_utils import ensure_parent_dir

from sbir_analytics.clients import DagsterClient

TRANSITION_ASSET_KEYS = [
    "validated_contracts_sample",
    "enriched_sbir_awards",
    "enriched_vendor_resolution",
    "transformed_transition_scores",
    "transformed_transition_evidence",
    "transformed_transition_detections",
]


def seed_contracts(path: Path) -> None:
    """Create a minimal sample contracts file with the schema expected by downstream assets."""
    if path.exists() or path.with_suffix(".csv").exists():
        logger.info(f"Contracts sample already present at {path}")
        return

    ensure_parent_dir(path)
    df = pd.DataFrame(
        [
            {
                "contract_id": "C1",
                "piid": "PIID-001",
                "fain": None,
                "vendor_uei": "UEI123",
                "vendor_duns": None,
                "vendor_name": "UEI Vendor Inc",
                "action_date": "2023-01-01",
                "obligated_amount": 100000,
                "awarding_agency_code": "9700",
                "awarding_agency_name": "DEPT OF DEFENSE",
            },
            {
                "contract_id": "C2",
                "piid": "PIID-002",
                "fain": None,
                "vendor_uei": None,
                "vendor_duns": None,
                "vendor_name": "Acme Corporation",
                "action_date": "2023-02-01",
                "obligated_amount": 50000,
                "awarding_agency_code": "9700",
                "awarding_agency_name": "DEPT OF DEFENSE",
            },
        ]
    )
    try:
        df.to_parquet(path, index=False)
        logger.info(f"Seeded sample contracts to {path}")
    except Exception:
        csv_path = path.with_suffix(".csv")
        df.to_csv(csv_path, index=False)
        logger.warning(f"PyArrow missing; wrote contracts seed to {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run transition detection MVP pipeline")
    parser.add_argument("--contracts-path", help="Path to contracts sample file")
    parser.add_argument("--no-seed", action="store_true", help="Skip seeding sample contracts")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    config = get_config()

    # Resolve contracts path using the same PathsConfig key as the Dagster assets
    default_path = Path(config.paths.resolve_path("transition_contracts_output"))
    seed_path = Path(args.contracts_path) if args.contracts_path else default_path

    # Optionally seed sample data
    if not args.no_seed:
        seed_contracts(seed_path)

    ensure_parent_dir(Path("reports/validation/transition_mvp.json"))

    # Set env var so Dagster assets find the contracts file.
    # Always set it to the resolved path for consistency.
    env_key = "SBIR_ETL__TRANSITION__CONTRACTS_SAMPLE__PATH"
    previous_value = os.environ.get(env_key)
    os.environ[env_key] = str(seed_path)

    # Trigger materialization
    client = DagsterClient(config)
    try:
        result = client.trigger_materialization(asset_keys=TRANSITION_ASSET_KEYS)
    except Exception as e:
        logger.error(f"Transition pipeline failed: {e}")
        sys.exit(1)
    finally:
        # Restore previous env var state
        if previous_value is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = previous_value

    if result.status == "success":
        print(f"Transition pipeline completed successfully (run_id={result.run_id})")
    else:
        print(f"Transition pipeline failed (run_id={result.run_id})", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
