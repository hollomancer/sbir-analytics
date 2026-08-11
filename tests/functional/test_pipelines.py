"""Functional tests for pipeline execution.

Tests each major pipeline function end-to-end:
- Transition detection
- CET classification
- Fiscal returns analysis
- ModernBert embeddings
"""


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

    def test_cet_run_produces_outputs(self):
        """Test that CET pipeline produces expected outputs."""
        from dagster import materialize
        from sbir_analytics.assets.cet import enriched_cet_award_classifications

        result = materialize([enriched_cet_award_classifications])

        assert result.success
        # Asset uses key_prefix="ml", so node name includes prefix
        materializations = result.asset_materializations_for_node(
            "ml__enriched_cet_award_classifications"
        )
        assert len(materializations) > 0


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

    def test_pipelines_can_run_sequentially(self):
        """Test that pipelines can run in sequence without conflicts."""
        from dagster import materialize
        from sbir_analytics.assets.transition import validated_contracts_sample
        from sbir_analytics.assets.cet import enriched_cet_award_classifications

        # Run transition first
        result1 = materialize([validated_contracts_sample])
        assert result1.success

        # Run CET second
        result2 = materialize([enriched_cet_award_classifications])
        assert result2.success
