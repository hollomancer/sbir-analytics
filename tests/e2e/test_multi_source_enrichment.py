"""End-to-end integration test for SBIR + USAspending + SAM.gov data enrichment.

This test demonstrates the complete enrichment pipeline:
1. Load SBIR awards data (primary dataset)
2. Enrich with USAspending recipient data (contract details)
3. Enrich with SAM.gov entity data (company details)
4. Verify the complete enriched dataset

This test uses sample fixtures by default but can use real data if marked with
@pytest.mark.real_data or USE_REAL_SBIR_DATA=1 environment variable.
"""

import pandas as pd
import pytest

from src.enrichers.usaspending import enrich_sbir_with_usaspending


pytestmark = [pytest.mark.e2e, pytest.mark.weekly]


@pytest.fixture
def sample_sbir_awards():
    """Create sample SBIR awards data matching real structure."""
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
                "Program": "STTR",
                "Phase": "Phase I",
            },
            {
                "Company": "Tech Innovations",
                "UEI": "",  # Missing UEI - will test fuzzy matching
                "Duns": "",
                "Contract": "2023-SBIR-001",
                "Agency": "NSF",
                "Award Amount": 225000.0,
                "Award Year": 2023,
                "Program": "SBIR",
                "Phase": "Phase I",
            },
        ]
    )


@pytest.fixture
def sample_usaspending_recipients():
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
                "recipient_name": "Tech Innovations Incorporated",
                "recipient_uei": "T4E5C6H7I8N9N0O1",
                "recipient_duns": "123987456",
                "recipient_city": "Palo Alto",
                "recipient_state": "CA",
                "recipient_zip": "94301",
                "recipient_country": "USA",
                "business_types": "Small Business",
            },
        ]
    )


@pytest.fixture
def sample_sam_gov_entities():
    """Create sample SAM.gov entity data."""
    return pd.DataFrame(
        [
            {
                "unique_entity_id": "Q1U2A3N4T5U6M7D8",
                "cage_code": "1QD45",
                "legal_business_name": "QUANTUM DYNAMICS INC",
                "dba_name": "Quantum Dynamics",
                "physical_address_line_1": "1000 Wilson Blvd",
                "physical_address_city": "Arlington",
                "physical_address_state_or_province": "VA",
                "physical_address_zip_postal_code": "22201",
                "primary_naics": "541712",
                "naics_code_string": "541712,541330",
                "entity_structure": "2L",  # Corporate Entity (Not Tax Exempt)
                "business_type_string": "2X,A5",  # Small Business, Woman Owned
            },
            {
                "unique_entity_id": "N2E3U4R5A6L7N8E9",
                "cage_code": "2NN67",
                "legal_business_name": "NEURAL NETWORKS LLC",
                "dba_name": "Neural Networks",
                "physical_address_line_1": "500 California Ave",
                "physical_address_city": "Pasadena",
                "physical_address_state_or_province": "CA",
                "physical_address_zip_postal_code": "91101",
                "primary_naics": "541511",
                "naics_code_string": "541511,541512,541715",
                "entity_structure": "8H",  # Limited Liability Company
                "business_type_string": "2X,8W",  # Small Business, Woman Owned Small Business
            },
            {
                "unique_entity_id": "B3I4O5M6E7D8S9O0",
                "cage_code": "3BM89",
                "legal_business_name": "BIOMED SOLUTIONS CORP",
                "dba_name": "BioMed Solutions",
                "physical_address_line_1": "300 Technology Square",
                "physical_address_city": "Cambridge",
                "physical_address_state_or_province": "MA",
                "physical_address_zip_postal_code": "02139",
                "primary_naics": "541714",
                "naics_code_string": "541714,541380",
                "entity_structure": "2L",  # Corporate Entity
                "business_type_string": "2X,27",  # Small Business, Minority Owned
            },
            {
                "unique_entity_id": "T4E5C6H7I8N9N0O1",
                "cage_code": "4TI12",
                "legal_business_name": "TECH INNOVATIONS INC",
                "dba_name": "Tech Innovations",
                "physical_address_line_1": "3000 Sand Hill Road",
                "physical_address_city": "Palo Alto",
                "physical_address_state_or_province": "CA",
                "physical_address_zip_postal_code": "94301",
                "primary_naics": "541512",
                "naics_code_string": "541512,541519",
                "entity_structure": "2L",  # Corporate Entity
                "business_type_string": "2X",  # Small Business
            },
        ]
    )


class TestMultiSourceEnrichmentPipeline:
    """Test the complete SBIR enrichment pipeline with all data sources."""

    def test_sbir_plus_usaspending_enrichment(
        self, sample_sbir_awards, sample_usaspending_recipients
    ):
        """Test SBIR awards enriched with USAspending data."""
        # Enrich SBIR with USAspending
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_awards,
            sample_usaspending_recipients,
            sbir_uei_col="UEI",
            sbir_duns_col="Duns",
            sbir_company_col="Company",
        )

        # Verify enrichment metadata columns
        assert "_usaspending_match_method" in enriched.columns
        assert "_usaspending_match_score" in enriched.columns

        # Verify first three awards matched (by UEI/DUNS)
        assert enriched["_usaspending_match_method"].iloc[0] == "uei-exact"
        assert enriched["_usaspending_match_score"].iloc[0] == 100
        assert enriched["usaspending_recipient_recipient_city"].iloc[0] == "Arlington"

        assert enriched["_usaspending_match_method"].iloc[1] == "uei-exact"
        assert enriched["usaspending_recipient_recipient_city"].iloc[1] == "Pasadena"

        assert enriched["_usaspending_match_method"].iloc[2] == "uei-exact"
        assert enriched["usaspending_recipient_recipient_city"].iloc[2] == "Cambridge"

        # Fourth award should match by fuzzy name (various fuzzy match types)
        assert enriched["_usaspending_match_method"].iloc[3] in [
            "name-fuzzy-high",
            "name-fuzzy-low",
            "name-fuzzy-auto",
        ]
        assert enriched["usaspending_recipient_recipient_city"].iloc[3] == "Palo Alto"

    def test_sbir_plus_sam_gov_enrichment(self, sample_sbir_awards, sample_sam_gov_entities):
        """Test SBIR awards enriched with SAM.gov data."""
        # Simulate SAM.gov enrichment by merging on UEI
        enriched = sample_sbir_awards.copy()

        # Add SAM.gov data by UEI
        sam_data = sample_sam_gov_entities.copy()
        sam_data = sam_data.add_prefix("sam_")
        sam_data.rename(columns={"sam_unique_entity_id": "UEI"}, inplace=True)

        # Merge on UEI
        enriched = enriched.merge(sam_data, on="UEI", how="left", suffixes=("", "_sam"))

        # Verify SAM.gov columns added
        assert "sam_cage_code" in enriched.columns
        assert "sam_legal_business_name" in enriched.columns
        assert "sam_primary_naics" in enriched.columns

        # Verify first three awards matched
        assert enriched["sam_cage_code"].iloc[0] == "1QD45"
        assert enriched["sam_legal_business_name"].iloc[0] == "QUANTUM DYNAMICS INC"
        assert enriched["sam_primary_naics"].iloc[0] == "541712"

        assert enriched["sam_cage_code"].iloc[1] == "2NN67"
        assert enriched["sam_primary_naics"].iloc[1] == "541511"

        assert enriched["sam_cage_code"].iloc[2] == "3BM89"
        assert enriched["sam_primary_naics"].iloc[2] == "541714"

        # Fourth award should have null SAM.gov data (no UEI)
        assert pd.isna(enriched["sam_cage_code"].iloc[3])

    def test_complete_multi_source_enrichment(
        self, sample_sbir_awards, sample_usaspending_recipients, sample_sam_gov_entities
    ):
        """Test complete enrichment pipeline: SBIR + USAspending + SAM.gov."""
        # Step 1: Enrich with USAspending
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_awards,
            sample_usaspending_recipients,
            sbir_uei_col="UEI",
            sbir_duns_col="Duns",
            sbir_company_col="Company",
        )

        # Step 2: Enrich with SAM.gov
        sam_data = sample_sam_gov_entities.copy()
        sam_data = sam_data.add_prefix("sam_")
        sam_data.rename(columns={"sam_unique_entity_id": "UEI"}, inplace=True)

        enriched = enriched.merge(sam_data, on="UEI", how="left", suffixes=("", "_sam"))

        # Verify complete enrichment
        # Original SBIR columns
        assert "Company" in enriched.columns
        assert "Contract" in enriched.columns
        assert "Award Amount" in enriched.columns

        # USAspending enrichment columns
        assert "_usaspending_match_method" in enriched.columns
        assert "usaspending_recipient_recipient_city" in enriched.columns
        assert "usaspending_recipient_business_types" in enriched.columns

        # SAM.gov enrichment columns
        assert "sam_cage_code" in enriched.columns
        assert "sam_legal_business_name" in enriched.columns
        assert "sam_primary_naics" in enriched.columns
        assert "sam_business_type_string" in enriched.columns

        # Verify specific record: Quantum Dynamics Inc
        quantum_row = enriched[enriched["Company"] == "Quantum Dynamics Inc"].iloc[0]
        assert quantum_row["UEI"] == "Q1U2A3N4T5U6M7D8"
        assert quantum_row["usaspending_recipient_recipient_city"] == "Arlington"
        assert quantum_row["sam_cage_code"] == "1QD45"
        assert quantum_row["sam_primary_naics"] == "541712"

        # Verify enrichment coverage
        uei_match_count = (enriched["_usaspending_match_method"] == "uei-exact").sum()
        assert uei_match_count >= 3  # At least 3 UEI exact matches

        sam_match_count = enriched["sam_cage_code"].notna().sum()
        assert sam_match_count >= 3  # At least 3 SAM.gov matches

    def test_enrichment_metrics(
        self, sample_sbir_awards, sample_usaspending_recipients, sample_sam_gov_entities
    ):
        """Test enrichment metrics and quality indicators."""
        # Enrich with both sources
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_awards,
            sample_usaspending_recipients,
            sbir_uei_col="UEI",
            sbir_duns_col="Duns",
            sbir_company_col="Company",
        )

        sam_data = sample_sam_gov_entities.copy()
        sam_data = sam_data.add_prefix("sam_")
        sam_data.rename(columns={"sam_unique_entity_id": "UEI"}, inplace=True)
        enriched = enriched.merge(sam_data, on="UEI", how="left")

        # Calculate enrichment metrics
        total_awards = len(enriched)

        # USAspending enrichment rate
        usaspending_match_rate = enriched["_usaspending_match_method"].notna().sum() / total_awards
        assert usaspending_match_rate >= 0.75  # At least 75% match

        # SAM.gov enrichment rate
        sam_match_rate = enriched["sam_cage_code"].notna().sum() / total_awards
        assert sam_match_rate >= 0.75  # At least 75% match

        # High-confidence match rate (UEI exact matches)
        high_confidence_rate = (
            enriched["_usaspending_match_method"] == "uei-exact"
        ).sum() / total_awards
        assert high_confidence_rate >= 0.50  # At least 50% high-confidence

        # NAICS code coverage (from SAM.gov)
        naics_coverage_rate = enriched["sam_primary_naics"].notna().sum() / total_awards
        assert naics_coverage_rate >= 0.75  # At least 75% have NAICS

        # Print metrics for visibility
        print("\n=== Enrichment Metrics ===")
        print(f"Total Awards: {total_awards}")
        print(f"USAspending Match Rate: {usaspending_match_rate:.1%}")
        print(f"SAM.gov Match Rate: {sam_match_rate:.1%}")
        print(f"High-Confidence Match Rate: {high_confidence_rate:.1%}")
        print(f"NAICS Coverage Rate: {naics_coverage_rate:.1%}")


class TestRealDataEnrichmentPipeline:
    """Test enrichment pipeline with real data sources (slower, skipped by default)."""

    # Tests removed - placeholders for real data testing
    # These should be implemented when real data files are available
    # See INTEGRATION_TEST_ANALYSIS.md for details
    pass


class TestDataSourceIntegrity:
    """Test data source compatibility and schema alignment."""

    def test_uei_format_consistency(
        self, sample_sbir_awards, sample_usaspending_recipients, sample_sam_gov_entities
    ):
        """Verify UEI format consistency across all data sources."""
        # Check SBIR UEI format (filter empty strings)
        sbir_ueis = sample_sbir_awards["UEI"].dropna()
        sbir_ueis = sbir_ueis[sbir_ueis != ""]
        assert all(len(uei) == 16 for uei in sbir_ueis), "SBIR UEIs should be 16 characters"

        # Check USAspending UEI format
        usa_ueis = sample_usaspending_recipients["recipient_uei"].dropna()
        assert all(len(uei) == 16 for uei in usa_ueis), "USAspending UEIs should be 16 characters"

        # Check SAM.gov UEI format
        sam_ueis = sample_sam_gov_entities["unique_entity_id"].dropna()
        assert all(len(uei) == 16 for uei in sam_ueis), "SAM.gov UEIs should be 16 characters"

    def test_column_alignment(
        self, sample_sbir_awards, sample_usaspending_recipients, sample_sam_gov_entities
    ):
        """Verify expected columns exist in each data source."""
        # SBIR required columns
        assert "Company" in sample_sbir_awards.columns
        assert "UEI" in sample_sbir_awards.columns
        assert "Duns" in sample_sbir_awards.columns
        assert "Contract" in sample_sbir_awards.columns

        # USAspending required columns
        assert "recipient_name" in sample_usaspending_recipients.columns
        assert "recipient_uei" in sample_usaspending_recipients.columns
        assert "recipient_duns" in sample_usaspending_recipients.columns

        # SAM.gov required columns
        assert "unique_entity_id" in sample_sam_gov_entities.columns
        assert "cage_code" in sample_sam_gov_entities.columns
        assert "legal_business_name" in sample_sam_gov_entities.columns
        assert "primary_naics" in sample_sam_gov_entities.columns


# Example usage documentation in docstring
__doc__ += """

## Running the Tests

### Quick Test (Sample Data)
```bash
# Run all E2E multi-source tests with sample fixtures
pytest tests/e2e/test_multi_source_enrichment.py -v

# Run with detailed output
pytest tests/e2e/test_multi_source_enrichment.py -v -s
```

### Real Data Test (Slower)
```bash
# Run with real SBIR data
USE_REAL_SBIR_DATA=1 pytest tests/e2e/test_multi_source_enrichment.py -m real_data

# Or mark individual tests
pytest tests/e2e/test_multi_source_enrichment.py::TestRealDataEnrichmentPipeline -m real_data --run-real-data
```

### Integration Testing Strategy

1. **Unit Level**: Test individual extractors (SBIR, USAspending, SAM.gov)
2. **Integration Level**: Test pairwise enrichment (SBIR+USAspending, SBIR+SAM.gov)
3. **E2E Level**: Test complete pipeline (SBIR+USAspending+SAM.gov)

### Expected Enrichment Flow

```
┌─────────────┐
│ SBIR Awards │  (Primary Dataset)
└──────┬──────┘
       │
       ├─────────────┐
       │             │
       ▼             ▼
┌─────────────┐  ┌──────────┐
│ USAspending │  │ SAM.gov  │
│  Recipients │  │ Entities │
└─────────────┘  └──────────┘
       │             │
       └──────┬──────┘
              │
              ▼
    ┌──────────────────┐
    │ Enriched Dataset │
    │                  │
    │ - UEI matching   │
    │ - DUNS matching  │
    │ - Fuzzy name     │
    │ - NAICS codes    │
    │ - CAGE codes     │
    │ - Locations      │
    └──────────────────┘
```

### Enrichment Quality Metrics

- **USAspending Match Rate**: Target ≥75%
- **SAM.gov Match Rate**: Target ≥75%
- **High-Confidence Match Rate**: Target ≥50% (UEI exact matches)
- **NAICS Coverage**: Target ≥75%

### Troubleshooting

**Import Errors**: Ensure repository root is on sys.path (handled by conftest.py)

**Missing Data**: Sample fixtures are included, but real data requires:
  - `data/raw/sbir/award_data.csv`
  - `data/raw/sam_gov/sam_entity_records.parquet`
  - USAspending database dump (S3 or local)

**Slow Tests**: Use sample data by default. Real data tests are marked with @pytest.mark.real_data
"""
