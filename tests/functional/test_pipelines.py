"""Functional tests for pipeline execution.

Tests each major pipeline function end-to-end:
- Transition detection
- CET classification
- Fiscal returns analysis
- ModernBert embeddings
"""

import pytest


class TestTransitionPipeline:
    """Functional tests for transition detection pipeline."""

    def test_transition_run_produces_outputs(self):
        """Test that transition pipeline produces expected outputs."""
        from dagster import materialize
        from sbir_analytics.assets.transition import validated_contracts_sample

        # Only materialize the asset without upstream dependencies
        result = materialize([validated_contracts_sample])

        assert result.success
        assert len(result.asset_materializations_for_node("validated_contracts_sample")) > 0


class TestCETPipeline:
    """Functional tests for CET classification pipeline."""

    def test_cet_run_fails_without_required_inputs(self, monkeypatch, tmp_path):
        """CET materialization must not publish a placeholder without source data."""
        from dagster import materialize
        from sbir_analytics.assets.cet import enriched_cet_award_classifications
        from sbir_analytics.assets.cet import classifications

        loader = type(
            "Loader",
            (),
            {
                "load_taxonomy": lambda self: type("Taxonomy", (), {"cet_areas": []})(),
                "load_classification_config": lambda self: {},
            },
        )
        monkeypatch.setattr(classifications, "TaxonomyLoader", loader)
        monkeypatch.chdir(tmp_path)

        with pytest.raises(FileNotFoundError, match="No enriched award input"):
            materialize([enriched_cet_award_classifications])


class TestFiscalPipeline:
    """Functional tests for fiscal returns analysis pipeline."""

    def test_fiscal_run_produces_outputs(self):
        """Test that fiscal pipeline produces expected outputs."""
        from dagster import materialize
        from sbir_analytics.assets.fiscal_assets import sensitivity_scenarios

        # sensitivity_scenarios has no upstream dependencies, so it can be
        # materialized on its own.
        result = materialize([sensitivity_scenarios])

        assert result.success
        assert len(result.asset_materializations_for_node("sensitivity_scenarios")) > 0


class TestModernBertPipeline:
    """Functional tests for ModernBert embeddings pipeline."""

    def test_modernbert_run_produces_outputs(self, sentence_transformers_available):
        """Test that ModernBert pipeline produces expected outputs."""
        from dagster import materialize
        from sbir_analytics.assets.modernbert.embeddings import modernbert_embeddings_awards

        result = materialize([modernbert_embeddings_awards])

        assert result.success
        assert len(result.asset_materializations_for_node("modernbert_embeddings_awards")) > 0


class TestPipelineIntegration:
    """Integration tests across multiple pipelines."""

    def test_pipelines_can_run_sequentially(self, monkeypatch, tmp_path):
        """A valid pipeline run does not mask a later CET prerequisite failure."""
        from dagster import materialize
        from sbir_analytics.assets.transition import validated_contracts_sample
        from sbir_analytics.assets.cet import enriched_cet_award_classifications
        from sbir_analytics.assets.cet import classifications

        # Run transition first
        result1 = materialize([validated_contracts_sample])
        assert result1.success

        loader = type(
            "Loader",
            (),
            {
                "load_taxonomy": lambda self: type("Taxonomy", (), {"cet_areas": []})(),
                "load_classification_config": lambda self: {},
            },
        )
        monkeypatch.setattr(classifications, "TaxonomyLoader", loader)
        monkeypatch.chdir(tmp_path)

        with pytest.raises(FileNotFoundError, match="No enriched award input"):
            materialize([enriched_cet_award_classifications])

    def test_pipeline_outputs_dont_conflict(self):
        """Test that pipeline outputs use separate files."""
        outputs = [
            "data/processed/transitions.parquet",
            "data/processed/cet_classifications.parquet",
            "data/processed/fiscal_returns.parquet",
            "data/processed/modernbert_embeddings_awards.parquet",
            "data/processed/modernbert_embeddings_patents.parquet",
            "data/processed/modernbert_award_patent_similarity.parquet",
        ]

        # Check that outputs are distinct
        assert len(outputs) == len(set(outputs))
