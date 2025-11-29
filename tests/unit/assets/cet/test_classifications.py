"""Tests for CET classification assets."""

import json
from unittest.mock import Mock, mock_open, patch

import pandas as pd
import pytest

from src.assets.cet.classifications import (
    cet_award_classifications_quality_check,
    enriched_cet_award_classifications,
    enriched_cet_patent_classifications,
)


def _get_check_compute_fn(check_asset):
    """Extract the compute function from a Dagster asset check."""
    if hasattr(check_asset, "node_def") and hasattr(check_asset.node_def, "compute_fn"):
        return check_asset.node_def.compute_fn
    elif hasattr(check_asset, "compute_fn"):
        return check_asset.compute_fn
    else:
        return check_asset


# ==================== Fixtures ====================


pytestmark = pytest.mark.fast


@pytest.fixture
def sample_checks_data():
    """Sample checks JSON data."""
    return {
        "high_conf_rate": 0.75,
        "evidence_coverage_rate": 0.85,
        "total_classified": 1000,
        "high_confidence_count": 750,
        "with_evidence_count": 850,
        "reason": "success",
    }


@pytest.fixture
def sample_awards_df():
    """Sample awards DataFrame."""
    return pd.DataFrame(
        {
            "Award Number": ["AWD001", "AWD002", "AWD003"],
            "Company": ["TechCo", "BioCo", "AeroCo"],
            "Abstract": [
                "Artificial intelligence and machine learning for data analysis",
                "Biotechnology research for drug development",
                "Aerospace engineering and quantum computing systems",
            ],
            "Amount": [100000, 150000, 200000],
        }
    )


@pytest.fixture
def sample_patents_df():
    """Sample patents DataFrame."""
    return pd.DataFrame(
        {
            "patent_id": ["PAT001", "PAT002", "PAT003"],
            "title": ["AI System", "Bio Method", "Quantum Computer"],
            "abstract": [
                "Machine learning system for pattern recognition",
                "Biotechnology method for gene therapy",
                "Quantum computing hardware design",
            ],
        }
    )


@pytest.fixture
def sample_taxonomy():
    """Sample CET taxonomy."""
    return {
        "cet_areas": [
            {
                "id": "ai_ml",
                "name": "Artificial Intelligence and Machine Learning",
                "keywords": ["artificial intelligence", "machine learning", "neural networks"],
            },
            {
                "id": "quantum",
                "name": "Quantum Information Science",
                "keywords": ["quantum computing", "quantum", "qubit"],
            },
            {
                "id": "biotechnology",
                "name": "Biotechnology",
                "keywords": ["biotechnology", "gene therapy", "biotech"],
            },
        ]
    }


@pytest.fixture
def sample_classification_results():
    """Sample classification results."""
    return pd.DataFrame(
        {
            "award_id": ["AWD001", "AWD002", "AWD003"],
            "primary_cet": ["ai_ml", "biotechnology", "quantum"],
            "primary_score": [0.95, 0.88, 0.92],
            "supporting_cets": [["quantum"], ["ai_ml"], ["ai_ml"]],
            "evidence": [
                ["machine learning mentioned in abstract"],
                ["biotechnology research mentioned"],
                ["quantum computing in abstract"],
            ],
            "classified_at": ["2023-01-01T10:00:00"] * 3,
            "taxonomy_version": ["v1.0"] * 3,
        }
    )


# ==================== Quality Check Tests ====================


class TestCETAwardClassificationsQualityCheck:
    """Tests for CET award classifications quality check."""

    def test_quality_check_passes(self, mock_context, sample_checks_data, tmp_path):
        """Test quality check passes with good metrics."""
        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text(json.dumps(sample_checks_data))

        with patch("src.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            # Set up context manager for open()
            mock_file_context = Mock()
            mock_file_context.__enter__ = Mock(return_value=open(checks_path, encoding="utf-8"))
            mock_file_context.__exit__ = Mock(return_value=None)
            mock_path.open.return_value = mock_file_context
            mock_path_class.return_value = mock_path

            # Call the check function directly (it's decorated but still callable)
            from src.assets.cet.classifications import cet_award_classifications_quality_check

            result = cet_award_classifications_quality_check(mock_context)

        assert result.passed is True
        assert "meets thresholds" in result.description.lower()
        assert result.metadata["high_conf_rate"].value == 0.75
        assert result.metadata["evidence_coverage_rate"].value == 0.85

    def test_quality_check_fails_low_confidence(self, mock_context, tmp_path):
        """Test quality check fails with low confidence rate."""
        checks_data = {
            "high_conf_rate": 0.40,  # Below 0.60 threshold
            "evidence_coverage_rate": 0.85,
            "reason": "success",
        }
        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text(json.dumps(checks_data))

        with patch("src.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            # Set up context manager for open()
            mock_file_context = Mock()
            mock_file_context.__enter__ = Mock(return_value=open(checks_path, encoding="utf-8"))
            mock_file_context.__exit__ = Mock(return_value=None)
            mock_path.open.return_value = mock_file_context
            mock_path_class.return_value = mock_path

            result = cet_award_classifications_quality_check(mock_context)

        assert result.passed is False
        assert "below thresholds" in result.description.lower()

    def test_quality_check_fails_low_evidence_coverage(self, mock_context, tmp_path):
        """Test quality check fails with low evidence coverage."""
        checks_data = {
            "high_conf_rate": 0.75,
            "evidence_coverage_rate": 0.50,  # Below 0.80 threshold
            "reason": "success",
        }
        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text(json.dumps(checks_data))

        with patch("src.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            # Set up context manager for open()
            mock_file_context = Mock()
            mock_file_context.__enter__ = Mock(return_value=open(checks_path, encoding="utf-8"))
            mock_file_context.__exit__ = Mock(return_value=None)
            mock_path.open.return_value = mock_file_context
            mock_path_class.return_value = mock_path

            # Direct call
            result = cet_award_classifications_quality_check(mock_context)

        assert result.passed is False

    def test_quality_check_missing_checks_file(self, mock_context):
        """Test quality check fails when checks file is missing."""
        with patch("src.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = False
            mock_path_class.return_value = mock_path

            # Direct call
            result = cet_award_classifications_quality_check(mock_context)

        assert result.passed is False
        assert "Missing" in result.description or "missing" in result.description
        mock_context.log.error.assert_called()

    def test_quality_check_invalid_json(self, mock_context, tmp_path):
        """Test quality check handles invalid JSON."""
        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text("{invalid json}")

        with patch("src.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            # Set up context manager for open()
            mock_file_context = Mock()
            mock_file_context.__enter__ = Mock(return_value=open(checks_path, encoding="utf-8"))
            mock_file_context.__exit__ = Mock(return_value=None)
            mock_path.open.return_value = mock_file_context
            mock_path_class.return_value = mock_path

            # Direct call
            result = cet_award_classifications_quality_check(mock_context)

        assert result.passed is False
        assert "Failed to read" in result.description

    def test_quality_check_model_missing_reason(self, mock_context, tmp_path):
        """Test quality check fails when model is missing."""
        checks_data = {
            "high_conf_rate": 0.75,
            "evidence_coverage_rate": 0.85,
            "reason": "model_missing",
        }
        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text(json.dumps(checks_data))

        with patch("src.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            # Set up context manager for open()
            mock_file_context = Mock()
            mock_file_context.__enter__ = Mock(return_value=open(checks_path, encoding="utf-8"))
            mock_file_context.__exit__ = Mock(return_value=None)
            mock_path.open.return_value = mock_file_context
            mock_path_class.return_value = mock_path

            # Direct call
            result = cet_award_classifications_quality_check(mock_context)

        assert result.passed is False
        assert "model_missing" in result.description

    def test_quality_check_model_load_failed_reason(self, mock_context, tmp_path):
        """Test quality check fails when model load fails."""
        checks_data = {
            "high_conf_rate": 0.75,
            "evidence_coverage_rate": 0.85,
            "reason": "model_load_failed",
        }
        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text(json.dumps(checks_data))

        with patch("src.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            # Set up context manager for open()
            mock_file_context = Mock()
            mock_file_context.__enter__ = Mock(return_value=open(checks_path, encoding="utf-8"))
            mock_file_context.__exit__ = Mock(return_value=None)
            mock_path.open.return_value = mock_file_context
            mock_path_class.return_value = mock_path

            # Direct call
            result = cet_award_classifications_quality_check(mock_context)

        assert result.passed is False
        assert "model_load_failed" in result.description

    def test_quality_check_missing_metrics(self, mock_context, tmp_path):
        """Test quality check fails when metrics are missing."""
        checks_data = {
            "reason": "success",
            # Missing high_conf_rate and evidence_coverage_rate
        }
        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text(json.dumps(checks_data))

        with patch("src.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            # Set up context manager for open()
            mock_file_context = Mock()
            mock_file_context.__enter__ = Mock(return_value=open(checks_path, encoding="utf-8"))
            mock_file_context.__exit__ = Mock(return_value=None)
            mock_path.open.return_value = mock_file_context
            mock_path_class.return_value = mock_path

            # Direct call
            result = cet_award_classifications_quality_check(mock_context)

        assert result.passed is False
        assert "missing quality metrics" in result.description.lower()

    @patch.dict("os.environ", {"SBIR_ETL__CET__CLASSIFICATION__HIGH_CONF_THRESHOLD": "0.80"})
    def test_quality_check_custom_thresholds(self, mock_context, tmp_path):
        """Test quality check with custom thresholds from environment."""
        checks_data = {
            "high_conf_rate": 0.75,  # Below custom 0.80 threshold
            "evidence_coverage_rate": 0.85,
            "reason": "success",
        }
        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text(json.dumps(checks_data))

        with patch("src.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            # Set up context manager for open()
            mock_file_context = Mock()
            mock_file_context.__enter__ = Mock(return_value=open(checks_path, encoding="utf-8"))
            mock_file_context.__exit__ = Mock(return_value=None)
            mock_path.open.return_value = mock_file_context
            mock_path_class.return_value = mock_path

            # Direct call
            result = cet_award_classifications_quality_check(mock_context)

        assert result.passed is False
        assert result.metadata["target_high_conf_rate"].value == 0.80


# ==================== Award Classifications Asset Tests ====================


class TestEnrichedCETAwardClassifications:
    """Tests for enriched CET award classifications asset."""

    @patch("src.assets.cet.classifications.TaxonomyLoader")
    @patch("src.assets.cet.classifications.Path")
    @patch("src.assets.cet.classifications.save_dataframe_parquet")
    @patch("builtins.open", new_callable=mock_open)
    def test_award_classifications_taxonomy_load_failure(
        self, mock_file, mock_save, mock_path_class, mock_taxonomy_loader
    ):
        """Test asset handles taxonomy load failure gracefully."""
        mock_taxonomy_loader.side_effect = Exception("Taxonomy load failed")

        # Mock Path behaviors
        mock_path = Mock()
        mock_path.exists.return_value = False
        mock_checks_path = Mock()
        mock_checks_path.parent = Mock()
        mock_checks_path.parent.mkdir = Mock()
        mock_path.with_suffix.return_value = mock_checks_path
        mock_path_class.return_value = mock_path

        enriched_cet_award_classifications()

        # Should write empty output and checks JSON indicating failure
        assert mock_save.called

    @patch("src.assets.cet.classifications.TaxonomyLoader")
    @patch("src.assets.cet.classifications.Path")
    @patch("src.assets.cet.classifications.save_dataframe_parquet")
    @patch("builtins.open", new_callable=mock_open)
    def test_award_classifications_no_input_data(
        self, mock_file, mock_save, mock_path_class, mock_taxonomy_loader, sample_taxonomy
    ):
        """Test asset handles missing input data."""
        # Mock taxonomy loader
        mock_loader = Mock()
        mock_loader.load_taxonomy.return_value = sample_taxonomy
        mock_taxonomy_loader.return_value = mock_loader

        # Mock Path to indicate no input files exist
        def path_side_effect(path_str):
            mock_path = Mock()
            mock_path.exists.return_value = False
            mock_path.with_suffix.return_value = Mock()
            return mock_path

        mock_path_class.side_effect = path_side_effect

        enriched_cet_award_classifications()

        # Should handle gracefully and write output
        assert mock_save.called

    @patch("src.assets.cet.classifications.TaxonomyLoader")
    @patch("src.assets.cet.classifications.Path")
    @patch("pandas.read_parquet")
    @patch("src.assets.cet.classifications.save_dataframe_parquet")
    @patch("builtins.open", new_callable=mock_open)
    def test_award_classifications_model_missing(
        self,
        mock_file,
        mock_save,
        mock_read_parquet,
        mock_path_class,
        mock_taxonomy_loader,
        sample_taxonomy,
        sample_awards_df,
    ):
        """Test asset handles missing ML model."""
        # Mock taxonomy loader
        mock_loader = Mock()
        mock_loader.load_taxonomy.return_value = sample_taxonomy
        mock_taxonomy_loader.return_value = mock_loader

        # Mock parquet reader
        mock_read_parquet.return_value = sample_awards_df

        # Mock Path to indicate model doesn't exist but data does
        def path_side_effect(path_str):
            mock_path = Mock()
            if "model" in str(path_str):
                mock_path.exists.return_value = False
            else:
                mock_path.exists.return_value = True
            mock_path.with_suffix.return_value = Mock()
            return mock_path

        mock_path_class.side_effect = path_side_effect

        enriched_cet_award_classifications()

        # Should write checks JSON indicating model is missing
        mock_file.assert_called()


# ==================== Patent Classifications Asset Tests ====================


class TestEnrichedCETPatentClassifications:
    """Tests for enriched CET patent classifications asset."""

    @patch("src.assets.cet.classifications.TaxonomyLoader")
    @patch("src.assets.cet.classifications.Path")
    @patch("src.assets.cet.classifications.save_dataframe_parquet")
    @patch("builtins.open", new_callable=mock_open)
    def test_patent_classifications_taxonomy_load_failure(
        self, mock_file, mock_save, mock_path_class, mock_taxonomy_loader
    ):
        """Test patent asset handles taxonomy load failure."""
        # Mock taxonomy loader to raise exception on load_taxonomy() call
        mock_loader = Mock()
        mock_loader.load_taxonomy.side_effect = Exception("Taxonomy load failed")
        mock_taxonomy_loader.return_value = mock_loader

        # Mock Path behaviors
        mock_path = Mock()
        mock_path.exists.return_value = False
        mock_checks_path = Mock()
        mock_checks_path.parent = Mock()
        mock_checks_path.parent.mkdir = Mock()
        mock_path.with_suffix.return_value = mock_checks_path
        mock_path_class.return_value = mock_path

        enriched_cet_patent_classifications()

        # Should write empty output
        assert mock_save.called

    @patch("src.assets.cet.classifications.TaxonomyLoader")
    @patch("src.assets.cet.classifications.Path")
    @patch("src.assets.cet.classifications.save_dataframe_parquet")
    @patch("builtins.open", new_callable=mock_open)
    def test_patent_classifications_no_input_data(
        self, mock_file, mock_save, mock_path_class, mock_taxonomy_loader, sample_taxonomy
    ):
        """Test patent asset handles missing input data."""
        # Mock taxonomy loader
        mock_loader = Mock()
        mock_loader.load_taxonomy.return_value = sample_taxonomy
        mock_taxonomy_loader.return_value = mock_loader

        # Mock Path to indicate no input files exist
        def path_side_effect(path_str):
            mock_path = Mock()
            mock_path.exists.return_value = False
            mock_path.with_suffix.return_value = Mock()
            return mock_path

        mock_path_class.side_effect = path_side_effect

        enriched_cet_patent_classifications()

        # Should handle gracefully
        assert mock_save.called


# ==================== Edge Cases ====================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_quality_check_empty_checks_file(self, tmp_path):
        """Test quality check handles empty checks file."""
        from dagster import build_op_context

        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text("{}")

        context = build_op_context()

        with patch("src.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            # Set up context manager for open()
            mock_file_context = Mock()
            mock_file_context.__enter__ = Mock(return_value=open(checks_path, encoding="utf-8"))
            mock_file_context.__exit__ = Mock(return_value=None)
            mock_path.open.return_value = mock_file_context
            mock_path_class.return_value = mock_path

            result = cet_award_classifications_quality_check(context)

        assert result.passed is False

    def test_quality_check_none_values(self, tmp_path):
        """Test quality check handles None values in metrics."""
        from dagster import build_op_context

        checks_data = {
            "high_conf_rate": None,
            "evidence_coverage_rate": None,
            "reason": "success",
        }
        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text(json.dumps(checks_data))

        context = build_op_context()

        with patch("src.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            # Set up context manager for open()
            mock_file_context = Mock()
            mock_file_context.__enter__ = Mock(return_value=open(checks_path, encoding="utf-8"))
            mock_file_context.__exit__ = Mock(return_value=None)
            mock_path.open.return_value = mock_file_context
            mock_path_class.return_value = mock_path

            result = cet_award_classifications_quality_check(context)

        assert result.passed is False
        assert "missing quality metrics" in result.description.lower()

    @patch("src.assets.cet.classifications.TaxonomyLoader")
    @patch("src.assets.cet.classifications.Path")
    @patch("src.assets.cet.classifications.save_dataframe_parquet")
    @patch("builtins.open", new_callable=mock_open)
    def test_award_classifications_save_failure(
        self, mock_file, mock_save, mock_path_class, mock_taxonomy_loader
    ):
        """Test asset handles save failure gracefully."""
        mock_taxonomy_loader.side_effect = Exception("Load failed")
        mock_save.side_effect = Exception("Save failed")

        # Mock Path behaviors
        mock_path = Mock()
        mock_path.exists.return_value = False
        mock_json_path = Mock()
        mock_json_path.parent = Mock()
        mock_json_path.parent.mkdir = Mock()
        mock_checks_path = Mock()
        mock_checks_path.parent = Mock()
        mock_checks_path.parent.mkdir = Mock()
        mock_path.with_suffix.side_effect = (
            lambda suffix: mock_json_path if suffix == ".json" else mock_checks_path
        )
        mock_path_class.return_value = mock_path

        # Should not raise, just log error
        enriched_cet_award_classifications()

    def test_quality_check_file_permission_error(self, tmp_path):
        """Test quality check handles file permission errors."""
        from dagster import build_op_context

        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text('{"high_conf_rate": 0.75}')
        checks_path.chmod(0o000)  # Remove all permissions

        context = build_op_context()

        with patch("src.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            mock_path.open.side_effect = PermissionError("Permission denied")
            mock_path_class.return_value = mock_path

            result = cet_award_classifications_quality_check(context)

        # Restore permissions for cleanup
        checks_path.chmod(0o644)

        assert result.passed is False
        assert "Failed to read" in result.description

    @patch.dict(
        "os.environ",
        {
            "SBIR_ETL__CET__CLASSIFICATION__HIGH_CONF_THRESHOLD": "0.90",
            "SBIR_ETL__CET__CLASSIFICATION__EVIDENCE_COVERAGE_THRESHOLD": "0.95",
        },
    )
    def test_quality_check_very_high_thresholds(self, mock_context, sample_checks_data, tmp_path):
        """Test quality check with very high custom thresholds."""
        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text(json.dumps(sample_checks_data))

        with patch("src.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            # Set up context manager for open()
            mock_file_context = Mock()
            mock_file_context.__enter__ = Mock(return_value=open(checks_path, encoding="utf-8"))
            mock_file_context.__exit__ = Mock(return_value=None)
            mock_path.open.return_value = mock_file_context
            mock_path_class.return_value = mock_path

            # Direct call
            result = cet_award_classifications_quality_check(mock_context)

        # Should fail because actual rates (0.75, 0.85) are below thresholds (0.90, 0.95)
        assert result.passed is False
        assert result.metadata["target_high_conf_rate"].value == 0.90
        assert result.metadata["target_evidence_coverage_rate"].value == 0.95

    def test_quality_check_preserves_extra_metadata(self, mock_context, tmp_path):
        """Test quality check preserves extra metadata from checks file."""
        checks_data = {
            "high_conf_rate": 0.75,
            "evidence_coverage_rate": 0.85,
            "total_classified": 1000,
            "model_version": "v1.0",
            "custom_field": "custom_value",
            "reason": "success",
        }
        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text(json.dumps(checks_data))

        with patch("src.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            # Set up context manager for open()
            mock_file_context = Mock()
            mock_file_context.__enter__ = Mock(return_value=open(checks_path, encoding="utf-8"))
            mock_file_context.__exit__ = Mock(return_value=None)
            mock_path.open.return_value = mock_file_context
            mock_path_class.return_value = mock_path

            # Direct call
            result = cet_award_classifications_quality_check(mock_context)

        # Extra fields should be preserved in metadata
        assert result.metadata["total_classified"].value == 1000
        assert result.metadata["model_version"].value == "v1.0"
        assert result.metadata["custom_field"].value == "custom_value"
