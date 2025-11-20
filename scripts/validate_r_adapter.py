#!/usr/bin/env python3
"""Validation script for R StateIO adapter.

This script checks if R and required packages are installed, tests the adapter
with sample data, and generates a validation report.
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

from src.config.loader import get_config
from src.transformers.r_stateio_adapter import RStateIOAdapter


app = typer.Typer(help="Validate R StateIO adapter installation and functionality")


@app.command()
def check_installation(
    output: str = typer.Option("reports/validation/r_adapter_check.json", help="Output JSON file"),
):
    """Check if R and required packages are installed."""
    results = {
        "rpy2_available": False,
        "stateio_available": False,
        "r_version": None,
        "errors": [],
    }

    # Check rpy2
    try:
        import rpy2.robjects as ro
        from rpy2.robjects.packages import importr

        results["rpy2_available"] = True
        logger.info("✓ rpy2 is installed")

        # Try to get R version
        try:
            r_version = ro.r("R.version.string")[0]
            results["r_version"] = str(r_version)
            logger.info(f"✓ R version: {r_version}")
        except Exception as e:
            results["errors"].append(f"Could not get R version: {e}")

        # Check StateIO package
        try:
            importr("stateior")
            results["stateio_available"] = True
            logger.info("✓ StateIO R package is installed")
        except Exception as e:
            results["errors"].append(f"StateIO package not available: {e}")
            logger.warning(f"✗ StateIO package not available: {e}")

    except ImportError:
        results["errors"].append("rpy2 is not installed")
        logger.error("✗ rpy2 is not installed. Install with: poetry install --extras r")

    # Write results
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Validation results written to {output_path}")

    # Return success status
    return 0 if results["rpy2_available"] and results["stateio_available"] else 1


@app.command()
def test_adapter(
    output: str = typer.Option("reports/validation/r_adapter_test.json", help="Output JSON file"),
):
    """Test R adapter with sample shocks data."""
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
        # Create sample shocks
        sample_shocks = pd.DataFrame(
            {
                "state": ["CA", "NY", "TX"],
                "bea_sector": ["11", "21", "31"],
                "fiscal_year": [2023, 2023, 2023],
                "shock_amount": [
                    Decimal("1000000"),
                    Decimal("500000"),
                    Decimal("750000"),
                ],
            }
        )
        results["num_shocks"] = len(sample_shocks)

        # Initialize adapter
        try:
            config = get_config()
            adapter = RStateIOAdapter(config=config.fiscal_analysis, cache_enabled=False)
            results["adapter_available"] = adapter.is_available()

            if not results["adapter_available"]:
                results["errors"].append("R adapter is not available")
                logger.warning("R adapter is not available")
                return 1

            logger.info("✓ R adapter initialized successfully")

            # Test computation
            try:
                impacts_df = adapter.compute_impacts(sample_shocks)
                results["computation_successful"] = True
                results["num_impacts"] = len(impacts_df)
                results["impact_columns"] = list(impacts_df.columns)

                logger.info(f"✓ Computed impacts for {len(impacts_df)} shocks")

                # Check if using placeholder computation
                if "quality_flags" in impacts_df.columns:
                    quality_flags = impacts_df["quality_flags"].unique()
                    if "placeholder_computation" in quality_flags:
                        results["warnings"].append(
                            "Using placeholder computation - R functions may not be working correctly"
                        )
                        logger.warning(
                            "⚠ Using placeholder computation. Verify R package installation."
                        )
                    elif "r_computation" in quality_flags:
                        logger.info("✓ Using real R computation")

                # Validate impact columns
                required_cols = [
                    "wage_impact",
                    "proprietor_income_impact",
                    "gross_operating_surplus",
                    "consumption_impact",
                    "tax_impact",
                    "production_impact",
                ]
                missing_cols = [col for col in required_cols if col not in impacts_df.columns]
                if missing_cols:
                    results["errors"].append(f"Missing impact columns: {missing_cols}")

                # Check for reasonable impact values
                for col in required_cols:
                    if col in impacts_df.columns:
                        values = impacts_df[col].dropna()
                        if len(values) > 0:
                            min_val = float(values.min())
                            max_val = float(values.max())
                            if min_val < 0:
                                results["warnings"].append(f"{col} has negative values")
                            if max_val == 0:
                                results["warnings"].append(f"{col} is all zeros")

            except Exception as e:
                results["errors"].append(f"Impact computation failed: {str(e)}")
                logger.error(f"✗ Impact computation failed: {e}")
                import traceback

                results["errors"].append(f"Traceback: {traceback.format_exc()}")

        except Exception as e:
            results["errors"].append(f"Adapter initialization failed: {str(e)}")
            logger.error(f"✗ Adapter initialization failed: {e}")
            import traceback

            results["errors"].append(f"Traceback: {traceback.format_exc()}")

    except Exception as e:
        results["errors"].append(f"Test setup failed: {str(e)}")
        logger.error(f"✗ Test setup failed: {e}")

    # Write results
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        # Convert Decimal to string for JSON serialization
        json_results = json.loads(json.dumps(results, indent=2, default=str, ensure_ascii=False))
        json.dump(json_results, f, indent=2)

    logger.info(f"Test results written to {output_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)
    print(f"Adapter Available: {'✓' if results['adapter_available'] else '✗'}")
    print(f"Computation Successful: {'✓' if results['computation_successful'] else '✗'}")
    print(f"Number of Impacts: {results['num_impacts']}")
    if results["errors"]:
        print(f"\nErrors ({len(results['errors'])}):")
        for error in results["errors"][:5]:  # Show first 5
            print(f"  - {error}")
    if results["warnings"]:
        print(f"\nWarnings ({len(results['warnings'])}):")
        for warning in results["warnings"][:5]:  # Show first 5
            print(f"  - {warning}")
    print("=" * 60)

    return 0 if results["computation_successful"] else 1


@app.command()
def full_check(output_dir: str = typer.Option("reports/validation", help="Output directory")):
    """Run full validation check (installation + adapter test)."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info("Running full validation check...")

    # Check installation
    logger.info("\n1. Checking R installation...")
    install_result = check_installation(output=str(output_path / "r_adapter_check.json"))

    # Test adapter
    logger.info("\n2. Testing adapter...")
    test_result = test_adapter(output=str(output_path / "r_adapter_test.json"))

    # Overall result
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
