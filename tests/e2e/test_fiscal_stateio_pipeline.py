"""End-to-end test for complete fiscal stateio pipeline.

This test validates the entire flow from SBIR awards to economic impact
and fiscal return calculations:

1. Load SBIR awards
2. Enrich with USAspending data (location)
3. Enrich with SAM.gov data (NAICS codes)
4. Map NAICS to BEA sectors
5. Aggregate into economic shocks
6. Calculate tax estimates
7. Calculate ROI and fiscal returns
8. Validate quality thresholds

This test uses sample data and demonstrates the complete fiscal analysis pipeline.
"""

from decimal import Decimal

import pandas as pd
import pytest

from src.enrichers.usaspending import enrich_sbir_with_usaspending
from src.transformers.fiscal.roi import FiscalROICalculator
from src.transformers.fiscal.shocks import calculate_fiscal_year
from src.transformers.fiscal.taxes import FiscalTaxEstimator
from src.transformers.naics_to_bea import NAICSToBEAMapper


pytestmark = [pytest.mark.e2e, pytest.mark.weekly]


@pytest.fixture
def sample_sbir_awards_fiscal():
    """Create sample SBIR awards with fiscal data."""
    return pd.DataFrame(
        [
            {
                "Company": "Quantum Dynamics Inc",
                "UEI": "Q1U2A3N4T5U6M7D8",
                "Duns": "111222333",
                "Contract": "W31P4Q-23-C-0001",
                "Agency": "DOD",
                "Award Amount": 150000.0,
                "Award Year": 2023,
                "Award Date": "2023-03-15",
                "Program": "SBIR",
                "Phase": "Phase I",
            },
            {
                "Company": "Neural Networks LLC",
                "UEI": "N2E3U4R5A6L7N8E9",
                "Duns": "444555666",
                "Contract": "NNX23CA01C",
                "Agency": "NASA",
                "Award Amount": 750000.0,
                "Award Year": 2023,
                "Award Date": "2023-06-20",
                "Program": "SBIR",
                "Phase": "Phase II",
            },
            {
                "Company": "BioMed Solutions Corp",
                "UEI": "B3I4O5M6E7D8S9O0",
                "Duns": "777888999",
                "Contract": "1R43GM123456-01",
                "Agency": "HHS",
                "Award Amount": 300000.0,
                "Award Year": 2024,
                "Award Date": "2023-11-10",  # FY 2024 (Oct-Sep)
                "Program": "STTR",
                "Phase": "Phase I",
            },
            {
                "Company": "AI Robotics Systems",
                "UEI": "A4I5R6O7B8O9T1I2",
                "Duns": "333444555",
                "Contract": "FA8650-23-C-7123",
                "Agency": "DOD",
                "Award Amount": 1000000.0,
                "Award Year": 2023,
                "Award Date": "2023-09-01",
                "Program": "SBIR",
                "Phase": "Phase II",
            },
        ]
    )


@pytest.fixture
def sample_usaspending_fiscal():
    """Create sample USAspending recipient data."""
    return pd.DataFrame(
        [
            {
                "recipient_name": "Quantum Dynamics Incorporated",
                "recipient_uei": "Q1U2A3N4T5U6M7D8",
                "recipient_duns": "111222333",
                "recipient_city": "Arlington",
                "recipient_state": "VA",
                "recipient_zip": "22201",
                "recipient_country": "USA",
                "business_types": "Small Business",
            },
            {
                "recipient_name": "Neural Networks LLC",
                "recipient_uei": "N2E3U4R5A6L7N8E9",
                "recipient_duns": "444555666",
                "recipient_city": "Pasadena",
                "recipient_state": "CA",
                "recipient_zip": "91101",
                "recipient_country": "USA",
                "business_types": "Small Business|Woman Owned",
            },
            {
                "recipient_name": "BioMed Solutions Corporation",
                "recipient_uei": "B3I4O5M6E7D8S9O0",
                "recipient_duns": "777888999",
                "recipient_city": "Cambridge",
                "recipient_state": "MA",
                "recipient_zip": "02139",
                "recipient_country": "USA",
                "business_types": "Small Business|Minority Owned",
            },
            {
                "recipient_name": "AI Robotics Systems Inc",
                "recipient_uei": "A4I5R6O7B8O9T1I2",
                "recipient_duns": "333444555",
                "recipient_city": "Austin",
                "recipient_state": "TX",
                "recipient_zip": "78701",
                "recipient_country": "USA",
                "business_types": "Small Business",
            },
        ]
    )


@pytest.fixture
def sample_sam_gov_fiscal():
    """Create sample SAM.gov entity data."""
    return pd.DataFrame(
        [
            {
                "unique_entity_id": "Q1U2A3N4T5U6M7D8",
                "cage_code": "1QD45",
                "legal_business_name": "QUANTUM DYNAMICS INC",
                "dba_name": "Quantum Dynamics",
                "primary_naics": "541712",  # R&D in Physical/Engineering Sciences
                "naics_code_string": "541712,541330",
            },
            {
                "unique_entity_id": "N2E3U4R5A6L7N8E9",
                "cage_code": "2NN67",
                "legal_business_name": "NEURAL NETWORKS LLC",
                "dba_name": "Neural Networks",
                "primary_naics": "541511",  # Custom Computer Programming
                "naics_code_string": "541511,541512,541715",
            },
            {
                "unique_entity_id": "B3I4O5M6E7D8S9O0",
                "cage_code": "3BM89",
                "legal_business_name": "BIOMED SOLUTIONS CORP",
                "dba_name": "BioMed Solutions",
                "primary_naics": "541714",  # R&D in Biotechnology
                "naics_code_string": "541714,541380",
            },
            {
                "unique_entity_id": "A4I5R6O7B8O9T1I2",
                "cage_code": "4AI12",
                "legal_business_name": "AI ROBOTICS SYSTEMS INC",
                "dba_name": "AI Robotics",
                "primary_naics": "541715",  # R&D in Physical/Engineering Sciences
                "naics_code_string": "541715,541512",
            },
        ]
    )


@pytest.fixture
def sample_naics_to_bea_mapping(tmp_path):
    """Create sample NAICS-to-BEA mapping file."""
    mapping_file = tmp_path / "naics_to_bea_mapping.csv"
    mapping_data = """naics_prefix,bea_sector,bea_description
5417,54,Professional Scientific and Technical Services
5415,54,Computer Systems Design and Related Services
54,54,Professional Scientific and Technical Services
"""
    mapping_file.write_text(mapping_data)
    return mapping_file


class TestFiscalStateIOPipelineE2E:
    """End-to-end tests for complete fiscal stateio pipeline."""

    def test_step1_enrich_with_usaspending(
        self, sample_sbir_awards_fiscal, sample_usaspending_fiscal
    ):
        """Step 1: Test SBIR enrichment with USAspending data."""
        # Enrich with USAspending
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_awards_fiscal,
            sample_usaspending_fiscal,
            sbir_uei_col="UEI",
            sbir_duns_col="Duns",
            sbir_company_col="Company",
        )

        # Verify enrichment
        assert len(enriched) == 4
        assert "_usaspending_match_method" in enriched.columns
        assert "usaspending_recipient_recipient_state" in enriched.columns

        # Verify all awards matched
        match_rate = enriched["_usaspending_match_method"].notna().sum() / len(enriched)
        assert match_rate == 1.0, "All awards should match USAspending data"

        # Verify state coverage (required for fiscal analysis)
        state_coverage = enriched["usaspending_recipient_recipient_state"].notna().sum() / len(
            enriched
        )
        assert state_coverage >= 0.90, "State coverage should be ≥90% for fiscal analysis"

        return enriched

    def test_step2_enrich_with_sam_gov(
        self, sample_sbir_awards_fiscal, sample_usaspending_fiscal, sample_sam_gov_fiscal
    ):
        """Step 2: Test SAM.gov enrichment with NAICS codes."""
        # First enrich with USAspending
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_awards_fiscal,
            sample_usaspending_fiscal,
            sbir_uei_col="UEI",
            sbir_duns_col="Duns",
            sbir_company_col="Company",
        )

        # Then enrich with SAM.gov
        sam_data = sample_sam_gov_fiscal.copy()
        sam_data = sam_data.add_prefix("sam_")
        sam_data.rename(columns={"sam_unique_entity_id": "UEI"}, inplace=True)

        enriched = enriched.merge(sam_data, on="UEI", how="left")

        # Verify SAM.gov enrichment
        assert "sam_primary_naics" in enriched.columns
        assert "sam_cage_code" in enriched.columns

        # Verify NAICS coverage (required for fiscal analysis)
        naics_coverage = enriched["sam_primary_naics"].notna().sum() / len(enriched)
        assert naics_coverage >= 0.85, "NAICS coverage should be ≥85% for fiscal analysis"

        return enriched

    def test_step3_map_naics_to_bea(
        self,
        sample_sbir_awards_fiscal,
        sample_usaspending_fiscal,
        sample_sam_gov_fiscal,
        sample_naics_to_bea_mapping,
    ):
        """Step 3: Test NAICS to BEA sector mapping."""
        # Enrich with both sources
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_awards_fiscal,
            sample_usaspending_fiscal,
            sbir_uei_col="UEI",
            sbir_duns_col="Duns",
            sbir_company_col="Company",
        )

        sam_data = sample_sam_gov_fiscal.copy()
        sam_data = sam_data.add_prefix("sam_")
        sam_data.rename(columns={"sam_unique_entity_id": "UEI"}, inplace=True)
        enriched = enriched.merge(sam_data, on="UEI", how="left")

        # Map NAICS to BEA
        mapper = NAICSToBEAMapper(mapping_path=str(sample_naics_to_bea_mapping))

        enriched["bea_sector_code"] = enriched["sam_primary_naics"].apply(
            lambda x: mapper.map_code(x) if pd.notna(x) else None
        )

        # Verify BEA mapping
        bea_mapped = enriched["bea_sector_code"].notna().sum() / len(enriched)
        assert bea_mapped >= 0.90, "BEA sector mapping should be ≥90%"

        # Verify all mapped to sector 54 (Professional Services)
        assert all(code == "54" for code in enriched["bea_sector_code"].dropna()), (
            "All sample NAICS codes should map to BEA sector 54"
        )

        return enriched

    def test_step4_calculate_fiscal_years(self, sample_sbir_awards_fiscal):
        """Step 4: Test fiscal year calculation."""
        # Test fiscal year calculation
        test_dates = {
            "2023-03-15": 2023,  # March -> FY 2023
            "2023-06-20": 2023,  # June -> FY 2023
            "2023-09-01": 2023,  # September -> FY 2023
            "2023-10-01": 2024,  # October -> FY 2024
            "2023-11-10": 2024,  # November -> FY 2024
            "2023-12-31": 2024,  # December -> FY 2024
        }

        for date_str, expected_fy in test_dates.items():
            calculated_fy = calculate_fiscal_year(date_str)
            assert calculated_fy == expected_fy, (
                f"Date {date_str} should be FY {expected_fy}, got {calculated_fy}"
            )

        # Test on DataFrame
        df = sample_sbir_awards_fiscal.copy()
        df["fiscal_year"] = df["Award Date"].apply(calculate_fiscal_year)

        # Verify fiscal years
        assert df["fiscal_year"].iloc[0] == 2023  # 2023-03-15
        assert df["fiscal_year"].iloc[1] == 2023  # 2023-06-20
        assert df["fiscal_year"].iloc[2] == 2024  # 2023-11-10 (Nov -> FY 2024)
        assert df["fiscal_year"].iloc[3] == 2023  # 2023-09-01

    def test_step5_aggregate_into_shocks(
        self,
        sample_sbir_awards_fiscal,
        sample_usaspending_fiscal,
        sample_sam_gov_fiscal,
        sample_naics_to_bea_mapping,
    ):
        """Step 5: Test aggregation into economic shocks."""
        # Prepare enriched data
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_awards_fiscal,
            sample_usaspending_fiscal,
            sbir_uei_col="UEI",
            sbir_duns_col="Duns",
            sbir_company_col="Company",
        )

        sam_data = sample_sam_gov_fiscal.copy()
        sam_data = sam_data.add_prefix("sam_")
        sam_data.rename(columns={"sam_unique_entity_id": "UEI"}, inplace=True)
        enriched = enriched.merge(sam_data, on="UEI", how="left")

        # Map NAICS to BEA
        mapper = NAICSToBEAMapper(mapping_path=str(sample_naics_to_bea_mapping))
        enriched["bea_sector_code"] = enriched["sam_primary_naics"].apply(
            lambda x: mapper.map_code(x) if pd.notna(x) else None
        )

        # Add fiscal year
        enriched["fiscal_year"] = enriched["Award Date"].apply(calculate_fiscal_year)

        # Aggregate by state-sector-fiscal year
        shock_aggregates = (
            enriched.groupby(
                [
                    "usaspending_recipient_recipient_state",
                    "bea_sector_code",
                    "fiscal_year",
                ]
            )
            .agg(
                {
                    "Award Amount": "sum",
                    "Contract": "count",  # Number of awards
                }
            )
            .reset_index()
        )

        shock_aggregates.rename(
            columns={
                "usaspending_recipient_recipient_state": "state",
                "bea_sector_code": "bea_sector",
                "Award Amount": "shock_amount",
                "Contract": "num_awards",
            },
            inplace=True,
        )

        # Verify aggregation
        assert len(shock_aggregates) > 0, "Should have at least one shock"
        assert "state" in shock_aggregates.columns
        assert "bea_sector" in shock_aggregates.columns
        assert "shock_amount" in shock_aggregates.columns

        # Verify total shock amount matches total awards
        total_awards = enriched["Award Amount"].sum()
        total_shocks = shock_aggregates["shock_amount"].sum()
        assert abs(total_awards - total_shocks) < 0.01, "Shock amounts should match award totals"

        # Verify we have multiple states
        assert shock_aggregates["state"].nunique() >= 3, "Should have shocks in multiple states"

        return shock_aggregates

    def test_step6_calculate_tax_estimates(
        self,
        sample_sbir_awards_fiscal,
        sample_usaspending_fiscal,
        sample_sam_gov_fiscal,
        sample_naics_to_bea_mapping,
    ):
        """Step 6: Test tax estimation from economic components."""
        # Prepare data with BEA sectors
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_awards_fiscal,
            sample_usaspending_fiscal,
            sbir_uei_col="UEI",
            sbir_duns_col="Duns",
            sbir_company_col="Company",
        )

        sam_data = sample_sam_gov_fiscal.copy()
        sam_data = sam_data.add_prefix("sam_")
        sam_data.rename(columns={"sam_unique_entity_id": "UEI"}, inplace=True)
        enriched = enriched.merge(sam_data, on="UEI", how="left")

        mapper = NAICSToBEAMapper(mapping_path=str(sample_naics_to_bea_mapping))
        enriched["bea_sector_code"] = enriched["sam_primary_naics"].apply(
            lambda x: mapper.map_code(x) if pd.notna(x) else None
        )

        # Create mock economic components (wage impacts, etc.)
        # In real pipeline, these come from StateIO model
        economic_components = []
        for _, row in enriched.iterrows():
            shock_amount = Decimal(str(row["Award Amount"]))

            # Mock multipliers (simplified)
            # Real values would come from StateIO model
            wage_multiplier = Decimal("0.4")  # 40% goes to wages
            proprietor_multiplier = Decimal("0.15")  # 15% to proprietor income
            corporate_multiplier = Decimal("0.10")  # 10% corporate profits

            economic_components.append(
                {
                    "state": row["usaspending_recipient_recipient_state"],
                    "bea_sector": row["bea_sector_code"],
                    "shock_amount": shock_amount,
                    "wage_impact": shock_amount * wage_multiplier,
                    "proprietor_income": shock_amount * proprietor_multiplier,
                    "gross_operating_surplus": shock_amount * corporate_multiplier,
                }
            )

        components_df = pd.DataFrame(economic_components)

        # Estimate taxes
        tax_estimator = FiscalTaxEstimator()

        tax_estimates = []
        for _, comp in components_df.iterrows():
            # Individual income tax
            individual_tax = tax_estimator.estimate_individual_income_tax(
                comp["wage_impact"], comp["proprietor_income"]
            )

            # Payroll tax (simplified)
            payroll_rate = Decimal("0.153")  # 15.3% (both employer and employee)
            payroll_tax = comp["wage_impact"] * payroll_rate

            # Corporate income tax (simplified)
            corporate_rate = Decimal("0.21")  # 21% federal rate
            corporate_tax = comp["gross_operating_surplus"] * corporate_rate

            total_tax = individual_tax + payroll_tax + corporate_tax

            tax_estimates.append(
                {
                    "state": comp["state"],
                    "bea_sector": comp["bea_sector"],
                    "individual_income_tax": individual_tax,
                    "payroll_tax": payroll_tax,
                    "corporate_income_tax": corporate_tax,
                    "total_tax_receipt": total_tax,
                }
            )

        tax_df = pd.DataFrame(tax_estimates)

        # Verify tax estimates
        assert len(tax_df) > 0, "Should have tax estimates"
        assert "total_tax_receipt" in tax_df.columns
        assert tax_df["total_tax_receipt"].sum() > 0, "Total tax receipts should be positive"

        # Verify tax receipts are reasonable (should be < total investment)
        total_investment = enriched["Award Amount"].sum()
        total_taxes = float(tax_df["total_tax_receipt"].sum())
        assert total_taxes < total_investment, (
            "Tax receipts should be less than total investment (without multiplier effects)"
        )

        return tax_df

    def test_step7_calculate_roi_metrics(
        self,
        sample_sbir_awards_fiscal,
        sample_usaspending_fiscal,
        sample_sam_gov_fiscal,
        sample_naics_to_bea_mapping,
    ):
        """Step 7: Test ROI calculation from tax estimates."""
        # Use the tax estimates from previous step
        # For this test, create simplified tax estimates
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_awards_fiscal,
            sample_usaspending_fiscal,
            sbir_uei_col="UEI",
            sbir_duns_col="Duns",
            sbir_company_col="Company",
        )

        # Simplified tax calculation
        total_investment = Decimal(str(enriched["Award Amount"].sum()))

        # Mock tax receipts (in real pipeline, comes from StateIO + tax estimator)
        # Assume 25% effective return rate (simplified)
        tax_receipts_df = pd.DataFrame(
            [
                {
                    "state": "VA",
                    "total_tax_receipt": total_investment * Decimal("0.08"),
                },
                {
                    "state": "CA",
                    "total_tax_receipt": total_investment * Decimal("0.10"),
                },
                {
                    "state": "MA",
                    "total_tax_receipt": total_investment * Decimal("0.07"),
                },
                {
                    "state": "TX",
                    "total_tax_receipt": total_investment * Decimal("0.05"),
                },
            ]
        )

        # Calculate ROI
        roi_calculator = FiscalROICalculator()

        roi_summary = roi_calculator.calculate_roi_summary(
            tax_receipts_df,
            sbir_investment=total_investment,
            discount_rate=0.03,
            time_horizon_years=10,
        )

        # Verify ROI metrics
        assert roi_summary.total_sbir_investment == total_investment
        assert roi_summary.total_tax_receipts > 0
        assert roi_summary.roi_ratio > 0, "ROI ratio should be positive"

        # With 30% return rate, ROI should be around 0.30 (30%)
        expected_roi = 0.30
        assert 0.15 <= roi_summary.roi_ratio <= 0.45, (
            f"ROI should be around {expected_roi}, got {roi_summary.roi_ratio}"
        )

        # Verify other metrics
        assert roi_summary.benefit_cost_ratio > 0

        print("\nROI Summary:")
        print(f"  Total Investment: ${roi_summary.total_sbir_investment:,.2f}")
        print(f"  Total Tax Receipts: ${roi_summary.total_tax_receipts:,.2f}")
        print(f"  ROI Ratio: {roi_summary.roi_ratio:.2%}")
        print(f"  Benefit-Cost Ratio: {roi_summary.benefit_cost_ratio:.2f}")
        print(f"  Payback Period: {roi_summary.payback_period_years} years")

        return roi_summary

    def test_complete_pipeline_integration(
        self,
        sample_sbir_awards_fiscal,
        sample_usaspending_fiscal,
        sample_sam_gov_fiscal,
        sample_naics_to_bea_mapping,
    ):
        """Test complete end-to-end fiscal pipeline integration."""
        print("\n" + "=" * 80)
        print("COMPLETE FISCAL STATEIO PIPELINE TEST")
        print("=" * 80)

        # Step 1: Enrich with USAspending
        print("\n[Step 1] Enriching SBIR awards with USAspending data...")
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_awards_fiscal,
            sample_usaspending_fiscal,
            sbir_uei_col="UEI",
            sbir_duns_col="Duns",
            sbir_company_col="Company",
        )
        print(f"  ✓ Enriched {len(enriched)} awards with USAspending data")
        print(
            f"  ✓ State coverage: {enriched['usaspending_recipient_recipient_state'].notna().sum()}/{len(enriched)}"
        )

        # Step 2: Enrich with SAM.gov
        print("\n[Step 2] Enriching with SAM.gov data (NAICS codes)...")
        sam_data = sample_sam_gov_fiscal.copy()
        sam_data = sam_data.add_prefix("sam_")
        sam_data.rename(columns={"sam_unique_entity_id": "UEI"}, inplace=True)
        enriched = enriched.merge(sam_data, on="UEI", how="left")
        naics_coverage = enriched["sam_primary_naics"].notna().sum() / len(enriched)
        print(
            f"  ✓ NAICS coverage: {enriched['sam_primary_naics'].notna().sum()}/{len(enriched)} ({naics_coverage:.1%})"
        )

        # Step 3: Map NAICS to BEA
        print("\n[Step 3] Mapping NAICS codes to BEA sectors...")
        mapper = NAICSToBEAMapper(mapping_path=str(sample_naics_to_bea_mapping))
        enriched["bea_sector_code"] = enriched["sam_primary_naics"].apply(
            lambda x: mapper.map_code(x) if pd.notna(x) else None
        )
        bea_coverage = enriched["bea_sector_code"].notna().sum() / len(enriched)
        print(
            f"  ✓ BEA mapping coverage: {enriched['bea_sector_code'].notna().sum()}/{len(enriched)} ({bea_coverage:.1%})"
        )

        # Step 4: Calculate fiscal years
        print("\n[Step 4] Calculating fiscal years...")
        enriched["fiscal_year"] = enriched["Award Date"].apply(calculate_fiscal_year)
        print(f"  ✓ Fiscal years: {enriched['fiscal_year'].unique()}")

        # Step 5: Aggregate into shocks
        print("\n[Step 5] Aggregating awards into economic shocks...")
        shock_aggregates = (
            enriched.groupby(
                [
                    "usaspending_recipient_recipient_state",
                    "bea_sector_code",
                    "fiscal_year",
                ]
            )
            .agg({"Award Amount": ["sum", "count"]})
            .reset_index()
        )
        shock_aggregates.columns = [
            "state",
            "bea_sector",
            "fiscal_year",
            "shock_amount",
            "num_awards",
        ]
        print(f"  ✓ Created {len(shock_aggregates)} economic shocks")
        print(f"  ✓ States: {shock_aggregates['state'].unique()}")
        print(f"  ✓ Total shock amount: ${shock_aggregates['shock_amount'].sum():,.2f}")

        # Step 6: Calculate tax estimates (simplified)
        print("\n[Step 6] Calculating tax estimates...")
        total_investment = Decimal(str(enriched["Award Amount"].sum()))
        # Simplified: 30% effective tax return rate
        total_tax_receipts = total_investment * Decimal("0.30")
        print(f"  ✓ Total investment: ${total_investment:,.2f}")
        print(f"  ✓ Estimated tax receipts: ${total_tax_receipts:,.2f}")

        # Step 7: Calculate ROI
        print("\n[Step 7] Calculating ROI metrics...")
        tax_df = pd.DataFrame([{"total_tax_receipt": total_tax_receipts}])
        roi_calculator = FiscalROICalculator()
        roi_summary = roi_calculator.calculate_roi_summary(
            tax_df, sbir_investment=total_investment, discount_rate=0.03
        )
        print(f"  ✓ ROI Ratio: {roi_summary.roi_ratio:.2%}")
        print(f"  ✓ Benefit-Cost Ratio: {roi_summary.benefit_cost_ratio:.2f}")
        print(f"  ✓ Payback Period: {roi_summary.payback_period_years} years")

        # Final validation
        print("\n" + "=" * 80)
        print("PIPELINE VALIDATION")
        print("=" * 80)

        # Validate quality thresholds
        assert naics_coverage >= 0.85, f"NAICS coverage {naics_coverage:.1%} below 85% threshold"
        assert bea_coverage >= 0.90, f"BEA coverage {bea_coverage:.1%} below 90% threshold"
        assert roi_summary.roi_ratio > 0, "ROI should be positive"
        assert len(shock_aggregates) > 0, "Should have economic shocks"

        print("✓ NAICS coverage threshold: PASS (≥85%)")
        print("✓ BEA mapping threshold: PASS (≥90%)")
        print("✓ ROI calculation: PASS (positive return)")
        print("✓ Economic shocks: PASS (created successfully)")
        print("\n✅ COMPLETE PIPELINE TEST: PASSED")
        print("=" * 80)


class TestFiscalDataQualityThresholds:
    """Test that enriched data meets fiscal analysis quality thresholds."""

    def test_naics_coverage_threshold(
        self,
        sample_sbir_awards_fiscal,
        sample_usaspending_fiscal,
        sample_sam_gov_fiscal,
    ):
        """Test that NAICS coverage meets 85% threshold."""
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_awards_fiscal,
            sample_usaspending_fiscal,
            sbir_uei_col="UEI",
            sbir_duns_col="Duns",
            sbir_company_col="Company",
        )

        sam_data = sample_sam_gov_fiscal.copy()
        sam_data = sam_data.add_prefix("sam_")
        sam_data.rename(columns={"sam_unique_entity_id": "UEI"}, inplace=True)
        enriched = enriched.merge(sam_data, on="UEI", how="left")

        naics_coverage = enriched["sam_primary_naics"].notna().sum() / len(enriched)

        # Verify threshold from config
        # fiscal_analysis.quality_thresholds.naics_coverage_rate: 0.85
        assert naics_coverage >= 0.85, f"NAICS coverage {naics_coverage:.1%} below 85% threshold"

    def test_state_coverage_threshold(self, sample_sbir_awards_fiscal, sample_usaspending_fiscal):
        """Test that state coverage meets 90% threshold."""
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_awards_fiscal,
            sample_usaspending_fiscal,
            sbir_uei_col="UEI",
            sbir_duns_col="Duns",
            sbir_company_col="Company",
        )

        state_coverage = enriched["usaspending_recipient_recipient_state"].notna().sum() / len(
            enriched
        )

        # Verify threshold from config
        # fiscal_analysis.quality_thresholds.geographic_resolution_rate: 0.90
        assert state_coverage >= 0.90, f"State coverage {state_coverage:.1%} below 90% threshold"

    def test_bea_mapping_threshold(
        self,
        sample_sbir_awards_fiscal,
        sample_usaspending_fiscal,
        sample_sam_gov_fiscal,
        sample_naics_to_bea_mapping,
    ):
        """Test that BEA sector mapping meets 90% threshold."""
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_awards_fiscal,
            sample_usaspending_fiscal,
            sbir_uei_col="UEI",
            sbir_duns_col="Duns",
            sbir_company_col="Company",
        )

        sam_data = sample_sam_gov_fiscal.copy()
        sam_data = sam_data.add_prefix("sam_")
        sam_data.rename(columns={"sam_unique_entity_id": "UEI"}, inplace=True)
        enriched = enriched.merge(sam_data, on="UEI", how="left")

        mapper = NAICSToBEAMapper(mapping_path=str(sample_naics_to_bea_mapping))
        enriched["bea_sector_code"] = enriched["sam_primary_naics"].apply(
            lambda x: mapper.map_code(x) if pd.notna(x) else None
        )

        bea_coverage = enriched["bea_sector_code"].notna().sum() / len(enriched)

        # Verify threshold from config
        # fiscal_analysis.quality_thresholds.bea_sector_mapping_rate: 0.90
        assert bea_coverage >= 0.90, f"BEA mapping {bea_coverage:.1%} below 90% threshold"


# Documentation in docstring
__doc__ += """

## Running the Fiscal StateIO Pipeline Tests

### Quick Test
```bash
# Run all fiscal pipeline tests
pytest tests/e2e/test_fiscal_stateio_pipeline.py -v

# Run with verbose output
pytest tests/e2e/test_fiscal_stateio_pipeline.py -v -s
```

### Test Individual Steps
```bash
# Test specific step
pytest tests/e2e/test_fiscal_stateio_pipeline.py::TestFiscalStateIOPipelineE2E::test_step1_enrich_with_usaspending -v

# Test complete pipeline
pytest tests/e2e/test_fiscal_stateio_pipeline.py::TestFiscalStateIOPipelineE2E::test_complete_pipeline_integration -v -s
```

### Expected Output
```
[Step 1] Enriching SBIR awards with USAspending data...
  ✓ Enriched 4 awards with USAspending data
  ✓ State coverage: 4/4

[Step 2] Enriching with SAM.gov data (NAICS codes)...
  ✓ NAICS coverage: 4/4 (100.0%)

[Step 3] Mapping NAICS codes to BEA sectors...
  ✓ BEA mapping coverage: 4/4 (100.0%)

[Step 4] Calculating fiscal years...
  ✓ Fiscal years: [2023 2024]

[Step 5] Aggregating awards into economic shocks...
  ✓ Created 4 economic shocks
  ✓ States: ['VA' 'CA' 'MA' 'TX']
  ✓ Total shock amount: $2,200,000.00

[Step 6] Calculating tax estimates...
  ✓ Total investment: $2,200,000.00
  ✓ Estimated tax receipts: $660,000.00

[Step 7] Calculating ROI metrics...
  ✓ ROI Ratio: 30.00%
  ✓ Benefit-Cost Ratio: 1.30
  ✓ Payback Period: 3.33 years

================================================================================
PIPELINE VALIDATION
================================================================================
✓ NAICS coverage threshold: PASS (≥85%)
✓ BEA mapping threshold: PASS (≥90%)
✓ ROI calculation: PASS (positive return)
✓ Economic shocks: PASS (created successfully)

✅ COMPLETE PIPELINE TEST: PASSED
```

## Pipeline Steps Validated

1. ✅ **USAspending Enrichment**: State location data
2. ✅ **SAM.gov Enrichment**: NAICS codes for industry mapping
3. ✅ **NAICS-to-BEA Mapping**: Industry sector classification
4. ✅ **Fiscal Year Calculation**: Government fiscal year determination
5. ✅ **Economic Shock Aggregation**: State-sector-year grouping
6. ✅ **Tax Estimation**: Federal tax receipt calculation
7. ✅ **ROI Calculation**: Return on investment metrics

## Quality Thresholds Tested

- NAICS Coverage: ≥85% (config: fiscal_analysis.quality_thresholds.naics_coverage_rate)
- State Coverage: ≥90% (config: fiscal_analysis.quality_thresholds.geographic_resolution_rate)
- BEA Mapping: ≥90% (config: fiscal_analysis.quality_thresholds.bea_sector_mapping_rate)

## Data Flow

```
SBIR Awards (4 records, $2.2M total)
    ↓ [USAspending Enrichment]
+ State/Location Data (100% coverage)
    ↓ [SAM.gov Enrichment]
+ NAICS Codes (100% coverage)
    ↓ [NAICS-to-BEA Mapping]
+ BEA Sector Codes (100% coverage)
    ↓ [Fiscal Year Calculation]
+ Fiscal Years (FY 2023-2024)
    ↓ [Economic Shock Aggregation]
Economic Shocks (4 state-sector-year shocks)
    ↓ [Tax Estimation]
Tax Receipts (~$660K estimated, 30% effective rate)
    ↓ [ROI Calculation]
ROI Metrics (30% ROI, 1.30 B/C ratio, 3.33 year payback)
```
"""
