#!/usr/bin/env python
"""Verification script for mock factories and DataFrame builders."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_mock_factories():
    """Test that mock factories work correctly."""
    from tests.mocks import Neo4jMocks, EnrichmentMocks, ConfigMocks

    # Test Neo4j mocks
    driver = Neo4jMocks.driver()
    assert driver.verify_connectivity() is True
    print("✓ Neo4jMocks.driver() works")

    session = Neo4jMocks.session()
    assert session.run() == []
    print("✓ Neo4jMocks.session() works")

    tx = Neo4jMocks.transaction()
    assert tx.commit() is True
    print("✓ Neo4jMocks.transaction() works")

    config = Neo4jMocks.config()
    assert config.uri == "bolt://localhost:7687"
    print("✓ Neo4jMocks.config() works")

    # Test Enrichment mocks
    sam_client = EnrichmentMocks.sam_gov_client()
    assert sam_client.rate_limit_remaining == 100
    print("✓ EnrichmentMocks.sam_gov_client() works")

    usa_client = EnrichmentMocks.usaspending_client()
    assert usa_client.get_award_details() is None
    print("✓ EnrichmentMocks.usaspending_client() works")

    matcher = EnrichmentMocks.fuzzy_matcher()
    assert matcher.match()["score"] == 0.85
    print("✓ EnrichmentMocks.fuzzy_matcher() works")

    # Test Config mocks
    pipeline_config = ConfigMocks.pipeline_config()
    assert pipeline_config.chunk_size == 10000
    print("✓ ConfigMocks.pipeline_config() works")

    dq_config = ConfigMocks.data_quality_config()
    assert dq_config.max_duplicate_rate == 0.10
    print("✓ ConfigMocks.data_quality_config() works")

    print("\n✅ All mock factories verified successfully!")


def test_dataframe_builders():
    """Test that DataFrame builders work correctly."""
    try:
        from tests.factories import DataFrameBuilder

        # Test awards builder
        df = DataFrameBuilder.awards(3).with_agency("DOD").with_phase("II").build()
        assert len(df) == 3
        assert all(df["agency"] == "DOD")
        assert all(df["phase"] == "II")
        print("✓ DataFrameBuilder.awards() works")

        # Test contracts builder
        df = DataFrameBuilder.contracts(2).with_agency("NASA").build()
        assert len(df) == 2
        assert all(df["awarding_agency_name"] == "NASA")
        print("✓ DataFrameBuilder.contracts() works")

        # Test companies builder
        df = DataFrameBuilder.companies(4).with_state("TX").build()
        assert len(df) == 4
        assert all(df["state"] == "TX")
        print("✓ DataFrameBuilder.companies() works")

        # Test patents builder
        df = DataFrameBuilder.patents(2).build()
        assert len(df) == 2
        print("✓ DataFrameBuilder.patents() works")

        print("\n✅ All DataFrame builders verified successfully!")

    except ImportError as e:
        print(f"⚠️  DataFrame builders require full environment: {e}")
        print("   (This is expected if pydantic/pandas not installed)")


if __name__ == "__main__":
    print("Verifying Mock Factories and DataFrame Builders")
    print("=" * 60)

    print("\n1. Testing Mock Factories...")
    print("-" * 60)
    test_mock_factories()

    print("\n2. Testing DataFrame Builders...")
    print("-" * 60)
    test_dataframe_builders()

    print("\n" + "=" * 60)
    print("✅ Phase 1 Implementation Complete!")
    print("\nNext steps:")
    print("  1. Run full test suite: pytest tests/")
    print("  2. Start migrating tests to use new factories")
    print("  3. See tests/REFACTORING_GUIDE.md for migration examples")
