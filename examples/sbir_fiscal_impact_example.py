"""Example: Calculate fiscal impacts from SBIR awards.

This example demonstrates the complete pipeline from SBIR awards to
tax and job impact analysis by state and industry.

Usage:
    python examples/sbir_fiscal_impact_example.py
"""

from pathlib import Path
import sys

import pandas as pd

# Ensure the src package is importable when running the example directly
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import the pipeline calculator
from src.transformers.sbir_fiscal_pipeline import SBIRFiscalImpactCalculator


def create_sample_sbir_awards() -> pd.DataFrame:
    """Create sample SBIR awards for demonstration.

    In production, this data would come from your SBIR database or
    after enrichment from USAspending API.
    """
    return pd.DataFrame(
        {
            "award_id": [
                "SBIR-2023-001",
                "SBIR-2023-002",
                "SBIR-2023-003",
                "SBIR-2023-004",
                "SBIR-2023-005",
            ],
            "award_amount": [
                1_000_000,  # $1M
                500_000,  # $500K
                750_000,  # $750K
                1_200_000,  # $1.2M
                600_000,  # $600K
            ],
            "state": [
                "CA",  # California
                "CA",  # California
                "NY",  # New York
                "TX",  # Texas
                "MA",  # Massachusetts
            ],
            "naics_code": [
                "541512",  # Computer Systems Design Services
                "541330",  # Engineering Services
                "621111",  # Physician Offices
                "334220",  # Radio/TV Broadcasting Equipment Manufacturing
                "541714",  # R&D in Biotechnology
            ],
            "fiscal_year": [2023, 2023, 2023, 2023, 2023],
            "company_name": [
                "Tech Innovations Inc",
                "Engineering Solutions LLC",
                "MedTech Research Corp",
                "Communications Systems Inc",
                "BioLife Sciences Inc",
            ],
        }
    )


def main():
    """Run SBIR fiscal impact analysis example."""
    print("=" * 80)
    print("SBIR Fiscal Impact Analysis Example")
    print("=" * 80)
    print()

    # Step 1: Create/load SBIR awards
    print("Step 1: Loading SBIR awards...")
    awards = create_sample_sbir_awards()
    print(f"  Loaded {len(awards)} SBIR awards")
    print(f"  Total award amount: ${awards['award_amount'].sum():,.2f}")
    print(f"  States: {', '.join(awards['state'].unique())}")
    print()

    # Step 2: Initialize the fiscal impact calculator
    print("Step 2: Initializing fiscal impact calculator...")
    calculator = SBIRFiscalImpactCalculator()
    print("  ✓ Calculator initialized")
    print("  ✓ NAICS→BEA mapper loaded")
    print("  ✓ R economic models ready (USEEIOR/StateIO)")
    print()

    # Step 3: Calculate impacts
    print("Step 3: Calculating fiscal and employment impacts...")
    print("  (This may take a moment as economic models are loaded...)")

    try:
        impacts = calculator.calculate_impacts_from_sbir_awards(awards)

        print(f"  ✓ Calculated impacts for {len(impacts)} state/sector combinations")
        print()

        # Step 4: Display results
        print("=" * 80)
        print("IMPACT RESULTS")
        print("=" * 80)
        print()

        # Show detailed impacts
        print("Detailed Impacts by State and Sector:")
        print("-" * 80)

        display_cols = [
            "state",
            "bea_sector",
            "award_total",
            "production_impact",
            "wage_impact",
            "tax_impact",
            "jobs_created",
        ]

        pd.options.display.float_format = "{:,.2f}".format
        print(impacts[display_cols].to_string(index=False))
        print()

        # Step 5: State-level summary
        print("=" * 80)
        print("STATE-LEVEL SUMMARY")
        print("=" * 80)
        print()

        state_summary = calculator.calculate_summary_by_state(impacts)
        print(state_summary.to_string(index=False))
        print()

        # Step 6: Sector-level summary
        print("=" * 80)
        print("SECTOR-LEVEL SUMMARY")
        print("=" * 80)
        print()

        sector_summary = calculator.calculate_summary_by_sector(impacts)
        print(sector_summary[["bea_sector", "sector_description", "total_awards", "total_tax_impact", "total_jobs_created"]].to_string(index=False))
        print()

        # Step 7: Key metrics
        print("=" * 80)
        print("KEY METRICS")
        print("=" * 80)
        print()

        total_awards = float(impacts["award_total"].sum())
        total_production = float(impacts["production_impact"].sum())
        total_tax = float(impacts["tax_impact"].sum())
        total_jobs = float(impacts["jobs_created"].sum())

        production_multiplier = total_production / total_awards if total_awards > 0 else 0
        tax_multiplier = total_tax / total_awards if total_awards > 0 else 0
        jobs_per_million = (total_jobs / total_awards) * 1_000_000 if total_awards > 0 else 0

        print(f"  Total SBIR Awards:        ${total_awards:,.2f}")
        print(f"  Total Production Impact:  ${total_production:,.2f}")
        print(f"  Total Tax Revenue Impact: ${total_tax:,.2f}")
        print(f"  Total Jobs Created:       {total_jobs:,.1f} jobs")
        print()
        print(f"  Production Multiplier:    {production_multiplier:.2f}x")
        print(f"  Tax Revenue Multiplier:   {tax_multiplier:.2f}x (${tax_multiplier*100:.2f} per $100 invested)")
        print(f"  Jobs per $1M Investment:  {jobs_per_million:.1f} jobs")
        print()

        # Step 8: Quality indicators
        print("=" * 80)
        print("DATA QUALITY")
        print("=" * 80)
        print()

        quality_counts = impacts["quality_flags"].value_counts()
        print("Quality Flags Distribution:")
        for flag, count in quality_counts.items():
            print(f"  {flag}: {count} records")
        print()

        avg_confidence = float(impacts["confidence"].mean())
        print(f"Average Confidence Score: {avg_confidence:.2%}")
        print()

    except Exception as e:
        print(f"  ✗ Error calculating impacts: {e}")
        print()
        print("Note: This example requires R and StateIO/USEEIOR packages installed.")
        print("Run in Docker environment or install dependencies:")
        print("  - Install R: https://www.r-project.org/")
        print("  - Install rpy2: uv sync --extra r")
        print("  - Install R packages: remotes::install_github('USEPA/stateior')")
        return

    print("=" * 80)
    print("Analysis Complete!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("  - Export results to CSV/database")
    print("  - Create visualizations")
    print("  - Compare across fiscal years")
    print("  - Generate reports for stakeholders")


if __name__ == "__main__":
    main()
