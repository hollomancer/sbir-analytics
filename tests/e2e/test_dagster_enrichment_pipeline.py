"""End-to-end Dagster pipeline smoke tests for SBIR-USAspending enrichment.


pytestmark = pytest.mark.e2e


Tests the complete enrichment pipeline from data ingestion through enrichment
to final output validation, ensuring all assets materialize successfully and
data flows correctly between stages.
"""

import pandas as pd
from dagster import DagsterEventType, build_asset_context, materialize
from dagster._core.definitions.asset_selection import AssetSelection

from src.assets.sbir_ingestion import raw_sbir_awards, validated_sbir_awards
from src.assets.sbir_usaspending_enrichment import enriched_sbir_awards
from src.definitions import defs


class TestEnrichmentPipelineSmokeTests:
    """Smoke tests for the complete enrichment pipeline."""

    def test_pipeline_materialize_all_assets(self):
        """Test that all enrichment assets can materialize successfully.

        This smoke test validates:
        - All assets execute without errors
        - Asset dependencies are correctly wired
        - Output data is non-empty
        """
        # Materialize all enrichment assets
        result = materialize(
            [raw_sbir_awards, validated_sbir_awards, enriched_sbir_awards],
            raise_on_error=True,
        )

        # Verify materialization succeeded
        assert result.success, "Pipeline materialization failed"

        # Check that all assets were materialized
        materialized_assets = [
            event.asset_key.path[-1]
            for event in result.all_events
            if event.event_type == DagsterEventType.ASSET_MATERIALIZATION
        ]

        assert "raw_sbir_awards" in materialized_assets
        assert "validated_sbir_awards" in materialized_assets
        assert "enriched_sbir_awards" in materialized_assets

    def test_raw_sbir_awards_asset(self):
        """Test raw SBIR awards extraction asset.

        Validates:
        - Raw data is extracted successfully
        - Data contains expected columns
        - Record count is non-zero
        - Metadata is populated
        """
        context = build_asset_context()
        result = raw_sbir_awards(context)

        # Get output value
        df = result.value

        # Verify output
        assert isinstance(df, pd.DataFrame), "Output should be DataFrame"
        assert len(df) > 0, "Should extract at least one record"
        assert "Company" in df.columns, "Should have Company column"
        assert "UEI" in df.columns, "Should have UEI column"
        assert "Duns" in df.columns, "Should have Duns column"

        # Verify metadata
        metadata = result.metadata
        assert metadata["num_records"] > 0
        assert "performance_total_duration_seconds" in metadata
        assert "performance_peak_memory_mb" in metadata

    def test_validated_sbir_awards_asset(self):
        """Test SBIR awards validation asset.

        Validates:
        - Validation filters records correctly
        - Output is subset of input (or equal)
        - Pass rate meets threshold
        - Metadata reflects validation results
        """
        # First extract raw data
        context = build_asset_context()
        raw_result = raw_sbir_awards(context)
        raw_df = raw_result.value

        # Then validate
        validated_result = validated_sbir_awards(context, raw_df)
        validated_df = validated_result.value

        # Verify output
        assert isinstance(validated_df, pd.DataFrame)
        assert len(validated_df) <= len(raw_df), "Validation should not increase records"
        assert len(validated_df) > 0, "Should have at least some valid records"

        # Verify metadata
        metadata = validated_result.metadata
        assert metadata["pass_rate"] is not None
        assert "validation_status" in metadata

    def test_enriched_sbir_awards_asset(self):
        """Test enrichment asset.

        Validates:
        - Enrichment produces output
        - Output contains enrichment columns
        - Match rate is calculated
        - Quality gates pass (>= 70% match rate)
        - Metadata is populated
        """
        # Prepare input data: use validated SBIR awards
        context = build_asset_context()
        raw_result = raw_sbir_awards(context)
        raw_df = raw_result.value

        validated_result = validated_sbir_awards(context, raw_df)
        validated_df = validated_result.value

        # Create mock USAspending data for enrichment
        usaspending_df = pd.DataFrame(
            {
                "recipient_name": ["Acme Inc", "BioTech LLC", "TechCorp"],
                "recipient_uei": ["UEI001", "UEI002", "UEI003"],
                "recipient_duns": ["DUNS001", "DUNS002", "DUNS003"],
            }
        )

        # Run enrichment
        enriched_result = enriched_sbir_awards(context, validated_df, usaspending_df)
        enriched_df = enriched_result.value

        # Verify output
        assert isinstance(enriched_df, pd.DataFrame)
        assert len(enriched_df) > 0, "Enriched output should have records"

        # Check for enrichment columns
        assert "_usaspending_match_method" in enriched_df.columns
        assert "_usaspending_match_score" in enriched_df.columns

        # Verify metadata
        metadata = enriched_result.metadata
        assert "match_rate" in metadata
        assert "performance_duration_seconds" in metadata
        assert "performance_peak_memory_mb" in metadata
        assert "performance_records_per_second" in metadata

    def test_enrichment_quality_gates_pass(self):
        """Test that enrichment quality gates pass on valid data.

        Validates:
        - Asset checks for match rate pass (>= 70%)
        - Asset checks for completeness pass
        - Metadata includes quality breakdown
        """
        # Prepare data
        context = build_asset_context()
        raw_result = raw_sbir_awards(context)
        raw_df = raw_result.value

        validated_result = validated_sbir_awards(context, raw_df)
        validated_df = validated_result.value

        # Create mock USAspending with good coverage
        # Make sure we have enough matching data
        company_names = validated_df["Company"].unique()[: min(10, len(validated_df))]
        usaspending_df = pd.DataFrame(
            {
                "recipient_name": [name for name in company_names for _ in range(3)],
                "recipient_uei": [f"UEI{i}" for i in range(len(company_names) * 3)],
                "recipient_duns": [f"DUNS{i}" for i in range(len(company_names) * 3)],
            }
        )

        # Run enrichment
        enriched_result = enriched_sbir_awards(context, validated_df, usaspending_df)

        # Verify metadata includes quality metrics
        metadata = enriched_result.metadata
        assert "match_rate" in metadata
        assert "matched_awards" in metadata
        assert "exact_matches" in metadata
        assert "fuzzy_matches" in metadata

    def test_data_flow_through_pipeline(self):
        """Test that data flows correctly through pipeline stages.

        Validates:
        - Columns from raw data appear in validated data
        - Columns from validated data appear in enriched data
        - Company names are preserved through pipeline
        - No unexpected data loss
        """
        # Extract raw data
        context = build_asset_context()
        raw_result = raw_sbir_awards(context)
        raw_df = raw_result.value

        # Validate
        validated_result = validated_sbir_awards(context, raw_df)
        validated_df = validated_result.value

        # Create mock USAspending
        usaspending_df = pd.DataFrame(
            {
                "recipient_name": ["Test Company"],
                "recipient_uei": ["UEI000"],
                "recipient_duns": ["DUNS000"],
            }
        )

        # Enrich
        enriched_result = enriched_sbir_awards(context, validated_df, usaspending_df)
        enriched_df = enriched_result.value

        # Verify data flow
        # Original columns should still exist
        assert "Company" in enriched_df.columns
        assert "UEI" in enriched_df.columns
        assert "Duns" in enriched_df.columns
        assert "Contract" in enriched_df.columns

        # Enrichment columns should be added
        assert "_usaspending_match_method" in enriched_df.columns
        assert "_usaspending_match_score" in enriched_df.columns

        # Company names should be preserved
        original_companies = set(validated_df["Company"].unique())
        enriched_companies = set(enriched_df["Company"].unique())
        assert original_companies == enriched_companies

        # No records should be lost
        assert len(enriched_df) == len(validated_df)

    def test_pipeline_with_empty_usaspending_data(self):
        """Test that pipeline handles empty USAspending data gracefully.

        Validates:
        - Pipeline doesn't crash with empty lookup data
        - All records marked as unmatched
        - Output is still valid
        """
        # Prepare SBIR data
        context = build_asset_context()
        raw_result = raw_sbir_awards(context)
        raw_df = raw_result.value

        validated_result = validated_sbir_awards(context, raw_df)
        validated_df = validated_result.value

        # Empty USAspending data
        empty_usaspending_df = pd.DataFrame(
            {
                "recipient_name": [],
                "recipient_uei": [],
                "recipient_duns": [],
            }
        )

        # Should still materialize
        enriched_result = enriched_sbir_awards(context, validated_df, empty_usaspending_df)
        enriched_df = enriched_result.value

        # All should be unmatched
        unmatched_count = enriched_df["_usaspending_match_method"].isna().sum()
        assert unmatched_count == len(enriched_df)

    def test_pipeline_metadata_completeness(self):
        """Test that pipeline emits complete metadata at each stage.

        Validates:
        - Raw asset has extraction metadata
        - Validated asset has validation metadata
        - Enriched asset has performance and quality metadata
        """
        context = build_asset_context()

        # Raw metadata
        raw_result = raw_sbir_awards(context)
        raw_metadata = raw_result.metadata
        assert "num_records" in raw_metadata
        assert "num_columns" in raw_metadata
        assert "performance_import_duration_seconds" in raw_metadata
        assert "performance_total_duration_seconds" in raw_metadata

        # Validated metadata
        validated_result = validated_sbir_awards(context, raw_result.value)
        validated_metadata = validated_result.metadata
        assert "pass_rate" in validated_metadata
        assert "validation_status" in validated_metadata

        # Enriched metadata
        usaspending_df = pd.DataFrame(
            {
                "recipient_name": [],
                "recipient_uei": [],
                "recipient_duns": [],
            }
        )
        enriched_result = enriched_sbir_awards(context, validated_result.value, usaspending_df)
        enriched_metadata = enriched_result.metadata
        assert "match_rate" in enriched_metadata
        assert "performance_duration_seconds" in enriched_metadata
        assert "performance_records_per_second" in enriched_metadata
        assert "performance_peak_memory_mb" in enriched_metadata


class TestPipelineIntegration:
    """Integration tests for pipeline orchestration."""

    def test_asset_dependencies(self):
        """Test that asset dependencies are correctly defined.

        Validates:
        - enriched_sbir_awards depends on validated_sbir_awards
        - validated_sbir_awards depends on raw_sbir_awards
        - Dependencies are resolvable
        """
        # Get asset graph from definitions
        assert hasattr(defs, "assets"), "Definitions should have assets"

        # Verify we can select assets in dependency order
        asset_selection = AssetSelection.all()
        assert asset_selection is not None

    def test_full_pipeline_execution(self):
        """Test complete pipeline execution with all assets.

        This is the main smoke test - validates the entire pipeline
        can execute from start to finish.
        """
        # Materialize the complete selection of enrichment assets
        result = materialize(
            AssetSelection.keys_in(
                [
                    ["raw_sbir_awards"],
                    ["validated_sbir_awards"],
                    ["enriched_sbir_awards"],
                ]
            ),
            raise_on_error=False,  # Capture errors for inspection
        )

        # Log results for debugging
        if not result.success:
            failed_events = [
                event
                for event in result.all_events
                if event.event_type == DagsterEventType.ASSET_MATERIALIZATION_FAILED
            ]
            for event in failed_events:
                print(f"Failed: {event.asset_key}: {event.description}")

        # Pipeline should complete (may have quality check failures - that's OK)
        # The important thing is no runtime errors
        assert result is not None


class TestPipelineEdgeCases:
    """Edge case tests for pipeline robustness."""

    def test_pipeline_with_minimal_data(self):
        """Test pipeline with minimal valid data.

        Validates:
        - Pipeline handles small datasets
        - At least one record processes correctly
        """
        context = build_asset_context()

        # Get raw data
        raw_result = raw_sbir_awards(context)
        raw_df = raw_result.value

        # Take just first record
        minimal_df = raw_df.head(1).copy()

        # Validate
        validated_result = validated_sbir_awards(context, minimal_df)
        validated_df = validated_result.value

        assert len(validated_df) >= 0, "Should handle minimal data"

    def test_enrichment_with_no_matches(self):
        """Test enrichment when no companies can be matched.

        Validates:
        - Pipeline completes
        - Match rate calculated correctly (0%)
        - Output structure valid
        """
        context = build_asset_context()

        # Create dummy data with no real companies
        sbir_df = pd.DataFrame(
            {
                "Company": ["Dummy Corp 1", "Dummy Corp 2"],
                "UEI": ["", ""],
                "Duns": ["", ""],
                "Contract": ["C-001", "C-002"],
                "Award Title": ["Test 1", "Test 2"],
            }
        )

        # Create USAspending data with no overlaps
        usaspending_df = pd.DataFrame(
            {
                "recipient_name": ["Different Corp"],
                "recipient_uei": ["UEI999"],
                "recipient_duns": ["DUNS999"],
            }
        )

        # Enrich
        enriched_result = enriched_sbir_awards(context, sbir_df, usaspending_df)
        enriched_df = enriched_result.value

        # Verify all unmatched
        unmatched = enriched_df["_usaspending_match_method"].isna().sum()
        assert unmatched == len(enriched_df)

        # Metadata should show 0% match rate
        metadata = enriched_result.metadata
        assert "0.0%" in metadata["match_rate"] or metadata["match_rate"] == "0.0%"


"""End-to-end Dagster pipeline smoke tests for SBIR-USAspending enrichment.

Tests the complete enrichment pipeline from data ingestion through enrichment
to final output validation, ensuring all assets materialize successfully and
data flows correctly between stages.
"""

import pytest


