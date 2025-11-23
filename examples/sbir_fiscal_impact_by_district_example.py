"""Example: Calculate fiscal impacts by congressional district.

This example demonstrates the complete pipeline for analyzing SBIR fiscal impacts
at the congressional district level:
1. Load SBIR awards with full addresses
2. Resolve congressional districts
3. Calculate state-level economic impacts (StateIO)
4. Allocate impacts to districts proportionally
5. Generate district-level reports

Usage:
    python examples/sbir_fiscal_impact_by_district_example.py
"""

from pathlib import Path
import sys

import pandas as pd

# Ensure the src package is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import mock versions for demonstration
from examples.sbir_fiscal_impact_example_mock import (
    MockSBIRFiscalImpactCalculator,
)

# Import district-specific components
from src.transformers.fiscal.district_allocator import (
    allocate_state_impacts_to_districts,
    summarize_by_district,
    compare_districts_within_state,
)


class MockCongressionalDistrictResolver:
    """Mock congressional district resolver for demonstration.

    In production, use src.enrichers.congressional_district_resolver.CongressionalDistrictResolver
    """

    def __init__(self, method="mock"):
        self.method = method

    def enrich_awards_with_districts(self, awards_df: pd.DataFrame) -> pd.DataFrame:
        """Add mock congressional districts based on ZIP codes."""
        enriched = awards_df.copy()

        # Mock district assignments based on state and city
        district_mapping = {
            ("CA", "Mountain View"): ("CA-16", "16", 0.95),
            ("CA", "San Francisco"): ("CA-11", "11", 0.92),
            ("CA", "Los Angeles"): ("CA-34", "34", 0.90),
            ("MA", "Cambridge"): ("MA-07", "07", 0.93),
            ("MA", "Boston"): ("MA-07", "07", 0.95),
            ("NY", "New York"): ("NY-12", "12", 0.91),
            ("TX", "Austin"): ("TX-37", "37", 0.94),
            ("TX", "Houston"): ("TX-07", "07", 0.89),
        }

        enriched["congressional_district"] = None
        enriched["district_number"] = None
        enriched["congressional_district_confidence"] = None
        enriched["congressional_district_method"] = "mock"

        for idx, row in enriched.iterrows():
            state = row.get("company_state")
            city = row.get("company_city")
            key = (state, city)

            if key in district_mapping:
                cd, num, conf = district_mapping[key]
                enriched.at[idx, "congressional_district"] = cd
                enriched.at[idx, "district_number"] = num
                enriched.at[idx, "congressional_district_confidence"] = conf

        return enriched


def create_sample_sbir_awards_with_addresses() -> pd.DataFrame:
    """Create sample SBIR awards with full address information."""
    return pd.DataFrame(
        {
            "award_id": [
                "SBIR-2023-001",
                "SBIR-2023-002",
                "SBIR-2023-003",
                "SBIR-2023-004",
                "SBIR-2023-005",
                "SBIR-2023-006",
                "SBIR-2023-007",
                "SBIR-2023-008",
            ],
            "company_name": [
                "Tech Innovations Inc",
                "Silicon Valley AI Corp",
                "Engineering Solutions LLC",
                "MedTech Research Corp",
                "BioLife Sciences Inc",
                "Communications Systems Inc",
                "Data Analytics Co",
                "Clean Energy Solutions",
            ],
            "award_amount": [
                1_000_000,  # $1M
                800_000,  # $800K
                500_000,  # $500K
                750_000,  # $750K
                600_000,  # $600K
                1_200_000,  # $1.2M
                400_000,  # $400K
                900_000,  # $900K
            ],
            "company_address": [
                "1600 Amphitheatre Parkway",
                "3500 Deer Creek Road",
                "100 Main Street",
                "One Kendall Square",
                "200 Boston Avenue",
                "500 Congress Avenue",
                "350 Fifth Avenue",
                "1000 Innovation Drive",
            ],
            "company_city": [
                "Mountain View",
                "Mountain View",
                "Cambridge",
                "Cambridge",
                "Boston",
                "Austin",
                "New York",
                "Austin",
            ],
            "company_state": [
                "CA",
                "CA",
                "MA",
                "MA",
                "MA",
                "TX",
                "NY",
                "TX",
            ],
            "company_zip": [
                "94043",
                "94043",
                "02142",
                "02142",
                "02101",
                "78701",
                "10001",
                "78701",
            ],
            "naics_code": [
                "541512",  # Computer Systems Design
                "541512",  # Computer Systems Design
                "541330",  # Engineering Services
                "621111",  # Physician Offices
                "541714",  # Biotech R&D
                "334220",  # Broadcasting Equipment Mfg
                "541512",  # Computer Systems Design
                "221114",  # Solar Electric Power
            ],
            "fiscal_year": [2023] * 8,
            # Note: fiscal pipeline expects 'state' column (gets mapped from company_state in real pipeline)
            "state": ["CA", "CA", "MA", "MA", "MA", "TX", "NY", "TX"],
        }
    )


def main():
    """Run congressional district fiscal impact analysis example."""
    print("=" * 80)
    print("SBIR FISCAL IMPACT ANALYSIS BY CONGRESSIONAL DISTRICT")
    print("=" * 80)
    print()
    print("NOTE: This is a demonstration using mock data and simplified multipliers.")
    print("      For real analysis, use production CongressionalDistrictResolver")
    print("      with Census API or ZIP crosswalk data.")
    print()

    # Step 1: Load SBIR awards with addresses
    print("Step 1: Loading SBIR awards with address information...")
    awards = create_sample_sbir_awards_with_addresses()
    print(f"  Loaded {len(awards)} SBIR awards")
    print(f"  Total award amount: ${awards['award_amount'].sum():,.2f}")
    print(f"  States: {', '.join(awards['company_state'].unique())}")
    print()

    # Step 2: Resolve congressional districts
    print("Step 2: Resolving congressional districts from addresses...")
    district_resolver = MockCongressionalDistrictResolver()
    awards_with_districts = district_resolver.enrich_awards_with_districts(awards)

    resolved_count = awards_with_districts["congressional_district"].notna().sum()
    print(
        f"  ✓ Resolved {resolved_count}/{len(awards)} districts ({resolved_count / len(awards):.1%})"
    )

    districts = awards_with_districts["congressional_district"].dropna().unique()
    print(f"  Districts found: {', '.join(sorted(districts))}")
    print()

    # Step 3: Calculate state-level impacts
    print("Step 3: Calculating state-level economic impacts (using mock StateIO)...")
    calculator = MockSBIRFiscalImpactCalculator()
    state_impacts = calculator.calculate_impacts_from_sbir_awards(awards)
    print(f"  ✓ Calculated impacts for {len(state_impacts)} state/sector combinations")
    print()

    # Step 4: Allocate state impacts to districts
    print("Step 4: Allocating state-level impacts to congressional districts...")
    district_impacts = allocate_state_impacts_to_districts(
        state_impacts_df=state_impacts,
        awards_with_districts_df=awards_with_districts,
    )
    print(f"  ✓ Created {len(district_impacts)} district/sector impact records")
    print()

    # Step 5: Display detailed district impacts
    print("=" * 80)
    print("DETAILED DISTRICT IMPACTS (by District and Sector)")
    print("=" * 80)
    print()

    display_cols = [
        "congressional_district",
        "state",
        "bea_sector",
        "district_award_total",
        "allocation_share",
        "tax_impact_allocated",
        "jobs_created_allocated",
    ]

    pd.options.display.float_format = "{:,.2f}".format
    print(district_impacts[display_cols].to_string(index=False))
    print()

    # Step 6: District-level summary
    print("=" * 80)
    print("CONGRESSIONAL DISTRICT SUMMARY")
    print("=" * 80)
    print()

    district_summary = summarize_by_district(district_impacts)
    print(district_summary.to_string(index=False))
    print()

    # Step 7: State comparison (California districts)
    print("=" * 80)
    print("CALIFORNIA CONGRESSIONAL DISTRICTS COMPARISON")
    print("=" * 80)
    print()

    ca_districts = compare_districts_within_state(district_impacts, "CA")
    if not ca_districts.empty:
        print(ca_districts.to_string(index=False))
    print()

    # Step 8: Key metrics by granularity level
    print("=" * 80)
    print("KEY METRICS BY GRANULARITY LEVEL")
    print("=" * 80)
    print()

    # National totals
    total_awards = float(awards["award_amount"].sum())
    total_tax_district = float(district_impacts["tax_impact_allocated"].sum())
    total_jobs_district = float(district_impacts["jobs_created_allocated"].sum())

    print("NATIONAL LEVEL:")
    print(f"  Total SBIR Awards:        ${total_awards:,.2f}")
    print(f"  Total Tax Revenue Impact: ${total_tax_district:,.2f}")
    print(f"  Total Jobs Created:       {total_jobs_district:,.1f} jobs")
    print()

    # State-level breakdown
    print("STATE LEVEL:")
    state_summary = calculator.calculate_summary_by_state(state_impacts)
    for _, row in state_summary.iterrows():
        print(
            f"  {row['state']}: ${row['total_tax_impact']:,.2f} tax impact, "
            f"{row['total_jobs_created']:.1f} jobs"
        )
    print()

    # District-level breakdown (top 5)
    print("CONGRESSIONAL DISTRICT LEVEL (Top 5 by Tax Impact):")
    top_districts = district_summary.nlargest(5, "total_tax_impact")
    for _, row in top_districts.iterrows():
        print(
            f"  {row['congressional_district']}: ${row['total_tax_impact']:,.2f} tax impact, "
            f"{row['total_jobs_created']:.1f} jobs, {row['sector_count']} sectors"
        )
    print()

    # Step 9: Use case examples
    print("=" * 80)
    print("ANSWERING STAKEHOLDER QUESTIONS")
    print("=" * 80)
    print()

    # Question 1: What's the impact in a specific district?
    target_district = "CA-16"
    district_data = district_summary[district_summary["congressional_district"] == target_district]
    if not district_data.empty:
        row = district_data.iloc[0]
        print(f"Q: What's the economic impact in district {target_district}?")
        print(f"A: District {target_district} received ${row['total_awards']:,.2f} in SBIR awards,")
        print(f"   generating ${row['total_tax_impact']:,.2f} in tax revenue and")
        print(
            f"   creating {row['total_jobs_created']:.1f} jobs across {row['sector_count']} sectors."
        )
        print()

    # Question 2: How do districts compare within a state?
    print("Q: How do California congressional districts compare?")
    if not ca_districts.empty:
        print(f"A: California has {len(ca_districts)} districts with SBIR activity.")
        top_ca = ca_districts.iloc[0]
        print(
            f"   Top district: {top_ca['congressional_district']} with ${top_ca['total_tax_impact']:,.2f}"
        )
        print(f"   Combined CA impact: ${ca_districts['total_tax_impact'].sum():,.2f}")
    print()

    # Question 3: Which districts benefit most from specific sectors?
    print("Q: Which districts benefit most from Professional/Scientific services (BEA 54)?")
    prof_sci_districts = district_impacts[district_impacts["bea_sector"] == "54"].copy()
    if not prof_sci_districts.empty:
        prof_sci_summary = (
            prof_sci_districts.groupby("congressional_district")["tax_impact_allocated"]
            .sum()
            .nlargest(3)
        )
        print("A: Top districts for Professional/Scientific services:")
        for district, tax_impact in prof_sci_summary.items():
            print(f"   {district}: ${tax_impact:,.2f}")
    print()

    print("=" * 80)
    print("Analysis Complete!")
    print("=" * 80)
    print()
    print("Supported Granularity Levels:")
    print("  ✅ National: Total across all awards")
    print("  ✅ State: Impacts by 50 states + DC + territories")
    print("  ✅ Congressional District: Impacts by 435 districts")
    print("  ✅ Industry (BEA Sector): Impacts by ~71 economic sectors")
    print("  ✅ Cross-tabulated: State × Sector, District × Sector, etc.")
    print()
    print("Next Steps:")
    print("  1. Use real CongressionalDistrictResolver with Census API")
    print("  2. Download HUD ZIP-to-district crosswalk for offline resolution")
    print("  3. Run with real StateIO economic models (Docker)")
    print("  4. Export results to CSV/Excel for further analysis")
    print("  5. Create visualizations (maps, charts)")


if __name__ == "__main__":
    main()
