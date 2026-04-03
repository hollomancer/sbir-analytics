#!/usr/bin/env python3
"""Validation script for BEA I-O adapter.

Tests that the BEA API key is configured and the adapter can compute
sample economic impacts.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import typer
from loguru import logger


# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sbir_etl.config.loader import get_config
from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter


app = typer.Typer(help="Validate BEA I-O adapter installation and functionality")


@app.command()
def check_installation(
    output: str = typer.Option("reports/validation/bea_adapter_check.json", help="Output JSON file"),
):
    """Check if BEA API key is configured."""
    results = {
        "bea_api_available": False,
        "errors": [],
    }

    try:
        from sbir_etl.transformers.bea_api_client import BEAApiClient

        client = BEAApiClient()
        results["bea_api_available"] = True
        logger.info("✓ BEA API key is configured")
        client.close()
    except Exception as e:
        results["errors"].append(str(e))
        logger.error(f"✗ BEA API not available: {e}")
        logger.error("  Register at https://apps.bea.gov/API/signup/")

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Validation results written to {output_path}")
    return 0 if results["bea_api_available"] else 1


@app.command()
def test_adapter(
    output: str = typer.Option("reports/validation/bea_adapter_test.json", help="Output JSON file"),
):
    """Test BEA adapter with sample shocks data."""
    results = {
        "adapter_available": False,
        "computation_successful": False,
        "num_shocks": 0,
        "num_impacts": 0,
        "impact_columns": [],
        "errors": [],
        "warnings": [],
    }

    try:
        sample_shocks = pd.DataFrame(
            {
                "state": ["CA", "NY", "TX"],
                "bea_sector": ["11", "21", "31"],
                "fiscal_year": [2020, 2020, 2020],
                "shock_amount": [
                    Decimal("1000000"),
                    Decimal("500000"),
                    Decimal("750000"),
                ],
            }
        )
        results["num_shocks"] = len(sample_shocks)

        config = get_config()
        adapter = BEAIOAdapter(config=config.fiscal_analysis, cache_enabled=False)
        results["adapter_available"] = adapter.is_available()

        if not results["adapter_available"]:
            results["warnings"].append("BEA API key not set — using placeholder computation")
            logger.warning("BEA API key not set — using placeholder computation")

        impacts_df = adapter.compute_impacts(sample_shocks)
        results["computation_successful"] = True
        results["num_impacts"] = len(impacts_df)
        results["impact_columns"] = list(impacts_df.columns)

        logger.info(f"✓ Computed impacts for {len(impacts_df)} shocks")

        if "quality_flags" in impacts_df.columns:
            flags = impacts_df["quality_flags"].unique().tolist()
            results["quality_flags"] = flags
            if any("placeholder" in str(f) for f in flags):
                results["warnings"].append("Using placeholder computation")
            elif any("bea_api" in str(f) for f in flags):
                logger.info("✓ Using real BEA API computation")

    except Exception as e:
        results["errors"].append(str(e))
        logger.error(f"✗ Test failed: {e}")

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"Test results written to {output_path}")

    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)
    print(f"Adapter Available: {'✓' if results['adapter_available'] else '✗ (placeholder mode)'}")
    print(f"Computation Successful: {'✓' if results['computation_successful'] else '✗'}")
    print(f"Number of Impacts: {results['num_impacts']}")
    if results["errors"]:
        print(f"\nErrors ({len(results['errors'])}):")
        for error in results["errors"][:5]:
            print(f"  - {error}")
    if results["warnings"]:
        print(f"\nWarnings ({len(results['warnings'])}):")
        for warning in results["warnings"][:5]:
            print(f"  - {warning}")
    print("=" * 60)

    return 0 if results["computation_successful"] else 1


@app.command()
def full_check(output_dir: str = typer.Option("reports/validation", help="Output directory")):
    """Run full validation check (installation + adapter test)."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info("Running full validation check...")

    logger.info("\n1. Checking BEA API configuration...")
    install_result = check_installation(output=str(output_path / "bea_adapter_check.json"))

    logger.info("\n2. Testing adapter...")
    test_result = test_adapter(output=str(output_path / "bea_adapter_test.json"))

    overall_success = install_result == 0 and test_result == 0

    logger.info("\n" + "=" * 60)
    if overall_success:
        logger.info("✓ Full validation PASSED")
    else:
        logger.warning("✗ Full validation had issues - check reports for details")
    logger.info("=" * 60)

    return 0 if overall_success else 1


if __name__ == "__main__":
    app()
