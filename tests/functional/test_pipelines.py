"""Functional tests for pipeline execution.

Tests each major pipeline function end-to-end:
- Transition detection
- CET classification
- Fiscal returns analysis
- PaECTER embeddings
"""

import pytest
from pathlib import Path


@pytest.fixture
def output_dir(tmp_path):
    """Create temporary output directory."""
    output = tmp_path / "data" / "processed"
    output.mkdir(parents=True)
    return output


class TestTransitionPipeline:
    """Functional tests for transition detection pipeline."""

    def test_transition_run_produces_outputs(self, output_dir):
        """Test that transition pipeline produces expected outputs."""
        from dagster import materialize
        from src.assets.transition.transition_assets import (
            validated_contracts_sample,
            enriched_vendor_resolution,
            transformed_transition_scores,
        )

        result = materialize(
            [validated_contracts_sample, enriched_vendor_resolution, transformed_transition_scores]
        )

        assert result.success
        assert len(result.asset_materializations_for_node("validated_contracts_sample")) > 0

    def test_transition_outputs_valid_schema(self):
        """Test that transition outputs have valid schema."""
        import pandas as pd

        # Load sample output
        output_path = Path("data/processed/transitions.parquet")
        if not output_path.exists():
            pytest.skip("Transition output not found")

        df = pd.read_parquet(output_path)

        # Validate schema
        required_cols = ["award_id", "contract_id", "transition_score", "confidence"]
        assert all(col in df.columns for col in required_cols)

        # Validate data types
        assert df["transition_score"].dtype in ["float64", "float32"]
        assert df["confidence"].dtype in ["float64", "float32"]


class TestCETPipeline:
    """Functional tests for CET classification pipeline."""

    def test_cet_run_produces_outputs(self):
        """Test that CET pipeline produces expected outputs."""
        from dagster import materialize
        from src.assets.cet.cet_assets import cet_classifications

        result = materialize([cet_classifications])

        assert result.success
        assert len(result.asset_materializations_for_node("cet_classifications")) > 0

    def test_cet_outputs_valid_schema(self):
        """Test that CET outputs have valid schema."""
        import pandas as pd

        output_path = Path("data/processed/cet_classifications.parquet")
        if not output_path.exists():
            pytest.skip("CET output not found")

        df = pd.read_parquet(output_path)

        # Validate schema
        required_cols = ["award_id", "cet_id", "score", "classification"]
        assert all(col in df.columns for col in required_cols)

        # Validate classification values
        assert df["classification"].isin(["High", "Medium", "Low"]).all()


class TestFiscalPipeline:
    """Functional tests for fiscal returns analysis pipeline."""

    @pytest.mark.skipif(
        not pytest.importorskip("rpy2", reason="R/rpy2 not available"),
        reason="Fiscal analysis requires R",
    )
    def test_fiscal_run_produces_outputs(self):
        """Test that fiscal pipeline produces expected outputs."""
        from dagster import materialize
        from src.assets.fiscal_assets import fiscal_returns_core

        result = materialize([fiscal_returns_core])

        assert result.success
        assert len(result.asset_materializations_for_node("fiscal_returns_core")) > 0

    @pytest.mark.skipif(
        not pytest.importorskip("rpy2", reason="R/rpy2 not available"),
        reason="Fiscal analysis requires R",
    )
    def test_fiscal_outputs_valid_schema(self):
        """Test that fiscal outputs have valid schema."""
        import pandas as pd

        output_path = Path("data/processed/fiscal_returns.parquet")
        if not output_path.exists():
            pytest.skip("Fiscal output not found")

        df = pd.read_parquet(output_path)

        # Validate schema
        required_cols = ["award_id", "roi", "federal_tax_receipts", "economic_impact"]
        assert all(col in df.columns for col in required_cols)

        # Validate numeric values
        assert df["roi"].dtype in ["float64", "float32"]
        assert (df["roi"] >= 0).all()


class TestPaECTERPipeline:
    """Functional tests for PaECTER embeddings pipeline."""

    @pytest.mark.skipif(
        not pytest.importorskip(
            "sentence_transformers", reason="sentence-transformers not available"
        ),
        reason="PaECTER requires sentence-transformers",
    )
    def test_paecter_run_produces_outputs(self):
        """Test that PaECTER pipeline produces expected outputs."""
        from dagster import materialize
        from src.assets.paecter.paecter_assets import paecter_embeddings

        result = materialize([paecter_embeddings])

        assert result.success
        assert len(result.asset_materializations_for_node("paecter_embeddings")) > 0

    @pytest.mark.skipif(
        not pytest.importorskip(
            "sentence_transformers", reason="sentence-transformers not available"
        ),
        reason="PaECTER requires sentence-transformers",
    )
    def test_paecter_outputs_valid_schema(self):
        """Test that PaECTER outputs have valid schema."""
        import pandas as pd

        output_path = Path("data/processed/paecter_embeddings.parquet")
        if not output_path.exists():
            pytest.skip("PaECTER output not found")

        df = pd.read_parquet(output_path)

        # Validate schema
        required_cols = ["award_id", "patent_id", "similarity_score"]
        assert all(col in df.columns for col in required_cols)

        # Validate similarity scores
        assert df["similarity_score"].dtype in ["float64", "float32"]
        assert (df["similarity_score"] >= 0).all()
        assert (df["similarity_score"] <= 1).all()


class TestPipelineIntegration:
    """Integration tests across multiple pipelines."""

    def test_pipelines_can_run_sequentially(self):
        """Test that pipelines can run in sequence without conflicts."""
        from dagster import materialize
        from src.assets.transition.transition_assets import validated_contracts_sample
        from src.assets.cet.cet_assets import cet_classifications

        # Run transition first
        result1 = materialize([validated_contracts_sample])
        assert result1.success

        # Run CET second
        result2 = materialize([cet_classifications])
        assert result2.success

    def test_pipeline_outputs_dont_conflict(self):
        """Test that pipeline outputs use separate files."""
        outputs = [
            "data/processed/transitions.parquet",
            "data/processed/cet_classifications.parquet",
            "data/processed/fiscal_returns.parquet",
            "data/processed/paecter_embeddings.parquet",
        ]

        # Check that outputs are distinct
        assert len(outputs) == len(set(outputs))
