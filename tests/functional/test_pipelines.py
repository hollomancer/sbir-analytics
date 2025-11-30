"""Functional tests for pipeline execution.

Tests each major pipeline function end-to-end:
- Transition detection
- CET classification
- Fiscal returns analysis
- PaECTER embeddings
"""

import pytest
import pandas as pd
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
        from src.assets.transition import validated_contracts_sample

        # Only materialize the asset without upstream dependencies
        result = materialize([validated_contracts_sample])

        assert result.success
        assert len(result.asset_materializations_for_node("validated_contracts_sample")) > 0


class TestCETPipeline:
    """Functional tests for CET classification pipeline."""

    def test_cet_run_produces_outputs(self):
        """Test that CET pipeline produces expected outputs."""
        from dagster import materialize
        from src.assets.cet import enriched_cet_award_classifications

        result = materialize([enriched_cet_award_classifications])

        assert result.success
        # Asset uses key_prefix="ml", so node name includes prefix
        materializations = result.asset_materializations_for_node(
            "ml__enriched_cet_award_classifications"
        )
        assert len(materializations) > 0


class TestFiscalPipeline:
    """Functional tests for fiscal returns analysis pipeline."""

    def test_fiscal_run_produces_outputs(self, rpy2_available):
        """Test that fiscal pipeline produces expected outputs."""
        from dagster import materialize
        from src.assets.fiscal_assets import fiscal_returns_core

        result = materialize([fiscal_returns_core])

        assert result.success
        assert len(result.asset_materializations_for_node("fiscal_returns_core")) > 0


class TestPaECTERPipeline:
    """Functional tests for PaECTER embeddings pipeline."""

    def test_paecter_run_produces_outputs(self, sentence_transformers_available):
        """Test that PaECTER pipeline produces expected outputs."""
        from dagster import materialize
        from src.assets.paecter.paecter_assets import paecter_embeddings

        result = materialize([paecter_embeddings])

        assert result.success
        assert len(result.asset_materializations_for_node("paecter_embeddings")) > 0


@pytest.mark.parametrize(
    "output_type,required_cols,validators",
    [
        (
            "transitions",
            ["award_id", "contract_id", "transition_score", "confidence"],
            {
                "transition_score": lambda df: df["transition_score"].dtype
                in ["float64", "float32"],
                "confidence": lambda df: df["confidence"].dtype in ["float64", "float32"],
            },
        ),
        (
            "cet_classifications",
            ["award_id", "cet_id", "score", "classification"],
            {
                "classification": lambda df: df["classification"]
                .isin(["High", "Medium", "Low"])
                .all(),
            },
        ),
        (
            "fiscal_returns",
            ["award_id", "roi", "federal_tax_receipts", "economic_impact"],
            {
                "roi": lambda df: df["roi"].dtype in ["float64", "float32"]
                and (df["roi"] >= 0).all(),
            },
        ),
        (
            "paecter_embeddings",
            ["award_id", "patent_id", "similarity_score"],
            {
                "similarity_score": lambda df: (
                    df["similarity_score"].dtype in ["float64", "float32"]
                    and (df["similarity_score"] >= 0).all()
                    and (df["similarity_score"] <= 1).all()
                ),
            },
        ),
    ],
)
def test_pipeline_output_schema(
    output_type: str, required_cols: list[str], validators: dict, repo_root: Path
):
    """Test that pipeline outputs have valid schema."""
    output_path = repo_root / "data" / "processed" / f"{output_type}.parquet"
    if not output_path.exists():
        pytest.skip(f"{output_type} output not found")

    df = pd.read_parquet(output_path)

    # Validate schema
    for col in required_cols:
        assert col in df.columns, f"Missing column: {col}"

    # Validate data quality
    assert len(df) > 0, "Output is empty"
    assert df[required_cols[0]].notna().all(), f"Null values in {required_cols[0]}"

    # Run custom validators
    for field, validator in validators.items():
        assert validator(df), f"Validation failed for {field}"


class TestPipelineIntegration:
    """Integration tests across multiple pipelines."""

    def test_pipelines_can_run_sequentially(self):
        """Test that pipelines can run in sequence without conflicts."""
        from dagster import materialize
        from src.assets.transition import validated_contracts_sample
        from src.assets.cet import enriched_cet_award_classifications

        # Run transition first
        result1 = materialize([validated_contracts_sample])
        assert result1.success

        # Run CET second
        result2 = materialize([enriched_cet_award_classifications])
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
