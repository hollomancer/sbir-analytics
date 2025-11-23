"""Example: Calculate fiscal impacts from SBIR awards (Mock/Demo version).

This example demonstrates the complete pipeline from SBIR awards to
tax and job impact analysis by state and industry using mock data.

This version works WITHOUT R and provides realistic demo outputs.
For real calculations, use Docker or install R + stateio packages.

Usage:
    python examples/sbir_fiscal_impact_example_mock.py
"""

from pathlib import Path
import sys
from decimal import Decimal

import pandas as pd

# Ensure the src package is importable when running the example directly
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.transformers.naics_bea_mapper import NAICSBEAMapper


class MockRStateIOAdapter:
    """Mock R adapter that provides realistic outputs without requiring R."""

    def __init__(self):
        """Initialize mock adapter."""
        self.model_version = "v2.1-mock"

    def compute_impacts(self, shocks_df: pd.DataFrame) -> pd.DataFrame:
        """Compute mock impacts using simple but realistic multipliers.

        Args:
            shocks_df: DataFrame with state, bea_sector, fiscal_year, shock_amount

        Returns:
            DataFrame with economic impact components
        """
        result_df = shocks_df.copy()

        # Convert shock_amount to float for calculations
        result_df["shock_amount_float"] = result_df["shock_amount"].apply(
            lambda x: float(x) if isinstance(x, Decimal) else float(x)
        )

        # Realistic I-O multipliers (vary by sector)
        # High-tech sectors (541xxx, 334xxx) typically have higher multipliers
        def get_production_multiplier(bea_sector):
            # Simplified multiplier logic
            if bea_sector in ["541", "54"]:  # Professional/Technical Services
                return 2.3
            elif bea_sector in ["334", "33"]:  # Manufacturing
                return 2.5
            elif bea_sector in ["621", "62"]:  # Healthcare
                return 2.1
            else:
                return 2.0

        result_df["production_multiplier"] = result_df["bea_sector"].apply(
            get_production_multiplier
        )

        # Calculate impacts based on shock amount and multipliers
        result_df["production_impact"] = (
            result_df["shock_amount_float"] * result_df["production_multiplier"]
        )

        # Wage impact typically 30-40% of production impact
        result_df["wage_impact"] = result_df["production_impact"] * 0.35

        # Proprietor income ~8% of production
        result_df["proprietor_income_impact"] = result_df["production_impact"] * 0.08

        # Gross operating surplus ~15% of production
        result_df["gross_operating_surplus"] = result_df["production_impact"] * 0.15

        # Tax impact (combined federal + state) ~12% of production
        result_df["tax_impact"] = result_df["production_impact"] * 0.12

        # Consumption impact ~25% of production
        result_df["consumption_impact"] = result_df["production_impact"] * 0.25

        # Add metadata
        result_df["model_version"] = self.model_version
        result_df["confidence"] = 0.85  # Mock confidence score
        result_df["quality_flags"] = "mock_data"

        # Clean up temporary columns
        result_df = result_df.drop(["shock_amount_float", "production_multiplier"], axis=1)

        return result_df


class MockSBIRFiscalImpactCalculator:
    """Mock fiscal impact calculator that works without R."""

    def __init__(self):
        """Initialize mock calculator."""
        self.r_adapter = MockRStateIOAdapter()
        self.naics_mapper = NAICSBEAMapper()

    def calculate_impacts_from_sbir_awards(
        self,
        awards_df: pd.DataFrame,
        include_employment: bool = True,
    ) -> pd.DataFrame:
        """Calculate complete fiscal impacts from SBIR awards.

        Args:
            awards_df: DataFrame with SBIR awards
            include_employment: Whether to calculate employment impacts

        Returns:
            DataFrame with impact components
        """
        # Validate input
        required_columns = ["award_amount", "state", "naics_code", "fiscal_year"]
        missing = [col for col in required_columns if col not in awards_df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Map NAICS to BEA
        awards_with_bea = awards_df.copy()
        awards_with_bea["bea_sector"] = awards_with_bea["naics_code"].apply(
            lambda naics: self.naics_mapper.map_naics_to_bea_summary(str(naics))
        )

        # Aggregate to shocks
        shocks = (
            awards_with_bea.groupby(["state", "bea_sector", "fiscal_year"])["award_amount"]
            .sum()
            .reset_index()
        )
        shocks.rename(columns={"award_amount": "shock_amount"}, inplace=True)
        shocks["shock_amount"] = shocks["shock_amount"].apply(
            lambda x: Decimal(str(x)) if pd.notnull(x) else Decimal("0")
        )

        # Compute impacts
        impacts = self.r_adapter.compute_impacts(shocks)

        # Add employment
        if include_employment:
            impacts["jobs_created"] = (impacts["wage_impact"].astype(float) / 100_000).round(1)

        # Add award totals
        impacts = impacts.merge(
            shocks[["state", "bea_sector", "fiscal_year", "shock_amount"]].rename(
                columns={"shock_amount": "award_total"}
            ),
            on=["state", "bea_sector", "fiscal_year"],
            how="left",
        )

        return impacts

    def calculate_summary_by_state(self, impacts: pd.DataFrame) -> pd.DataFrame:
        """Calculate state-level summary."""
        summary = (
            impacts.groupby("state")
            .agg(
                {
                    "award_total": "sum",
                    "tax_impact": "sum",
                    "jobs_created": "sum",
                    "wage_impact": "sum",
                    "production_impact": "sum",
                }
            )
            .reset_index()
        )
        summary.rename(
            columns={
                "award_total": "total_awards",
                "tax_impact": "total_tax_impact",
                "jobs_created": "total_jobs_created",
                "wage_impact": "total_wage_impact",
                "production_impact": "total_production_impact",
            },
            inplace=True,
        )
        return summary

    def calculate_summary_by_sector(self, impacts: pd.DataFrame) -> pd.DataFrame:
        """Calculate sector-level summary."""
        summary = (
            impacts.groupby("bea_sector")
            .agg(
                {
                    "award_total": "sum",
                    "tax_impact": "sum",
                    "jobs_created": "sum",
                    "wage_impact": "sum",
                    "production_impact": "sum",
                }
            )
            .reset_index()
        )
        summary.rename(
            columns={
                "award_total": "total_awards",
                "tax_impact": "total_tax_impact",
                "jobs_created": "total_jobs_created",
                "wage_impact": "total_wage_impact",
                "production_impact": "total_production_impact",
            },
            inplace=True,
        )
        summary["sector_description"] = summary["bea_sector"].apply(
            self.naics_mapper.get_bea_code_description
        )
        return summary


def create_sample_sbir_awards() -> pd.DataFrame:
    """Create sample SBIR awards for demonstration."""
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
    print("SBIR Fiscal Impact Analysis Example (MOCK VERSION)")
    print("=" * 80)
    print()
    print("NOTE: This is a demonstration using mock economic multipliers.")
    print("      For real calculations, run in Docker with R and StateIO installed.")
    print("      See Dockerfile and docker-compose.yml for setup.")
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
    calculator = MockSBIRFiscalImpactCalculator()
    print("  ✓ Mock calculator initialized")
    print("  ✓ NAICS→BEA mapper loaded")
    print("  ✓ Using simplified economic multipliers (not real StateIO)")
    print()

    # Step 3: Calculate impacts
    print("Step 3: Calculating fiscal and employment impacts...")

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
    print(
        sector_summary[
            [
                "bea_sector",
                "sector_description",
                "total_awards",
                "total_tax_impact",
                "total_jobs_created",
            ]
        ].to_string(index=False)
    )
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
    print(
        f"  Tax Revenue Multiplier:   {tax_multiplier:.2f}x (${tax_multiplier * 100:.2f} per $100 invested)"
    )
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

    print("=" * 80)
    print("Analysis Complete!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("  - For real calculations: docker compose --profile dev up --build")
    print(
        "  - Then run: docker compose exec dagster-webserver python examples/sbir_fiscal_impact_example.py"
    )
    print("  - Export results to CSV/database")
    print("  - Create visualizations")
    print("  - Compare across fiscal years")


if __name__ == "__main__":
    main()
