"""Tests for CET classification assets."""

import json
from unittest.mock import Mock, patch

import pytest

from sbir_analytics.assets.cet.classifications import (
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


# ==================== Quality Check Tests ====================


class TestCETAwardClassificationsQualityCheck:
    """Tests for CET award classifications quality check."""

    def test_quality_check_passes(self, mock_context, sample_checks_data, tmp_path):
        """Test quality check passes with good metrics."""
        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text(json.dumps(sample_checks_data))

        with patch("sbir_analytics.assets.cet.classifications.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            # Set up context manager for open()
            mock_file_context = Mock()
            mock_file_context.__enter__ = Mock(return_value=open(checks_path, encoding="utf-8"))
            mock_file_context.__exit__ = Mock(return_value=None)
            mock_path.open.return_value = mock_file_context
            mock_path_class.return_value = mock_path

            # Call the check function directly (it's decorated but still callable)
            from sbir_analytics.assets.cet.classifications import (
                cet_award_classifications_quality_check,
            )

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

        with patch("sbir_analytics.assets.cet.classifications.Path") as mock_path_class:
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

        with patch("sbir_analytics.assets.cet.classifications.Path") as mock_path_class:
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
        with patch("sbir_analytics.assets.cet.classifications.Path") as mock_path_class:
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

        with patch("sbir_analytics.assets.cet.classifications.Path") as mock_path_class:
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

        with patch("sbir_analytics.assets.cet.classifications.Path") as mock_path_class:
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

        with patch("sbir_analytics.assets.cet.classifications.Path") as mock_path_class:
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

        with patch("sbir_analytics.assets.cet.classifications.Path") as mock_path_class:
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

        with patch("sbir_analytics.assets.cet.classifications.Path") as mock_path_class:
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

    @patch("sbir_analytics.assets.cet.classifications.TaxonomyLoader")
    @patch("sbir_analytics.assets.cet.classifications.save_dataframe_parquet")
    def test_award_classifications_taxonomy_load_failure(self, mock_save, mock_taxonomy_loader):
        """A taxonomy failure fails the materialization without publishing output."""
        mock_taxonomy_loader.side_effect = Exception("Taxonomy load failed")

        with pytest.raises(RuntimeError, match="taxonomy and classification config"):
            enriched_cet_award_classifications()

        mock_save.assert_not_called()

    @patch("sbir_analytics.assets.cet.classifications.TaxonomyLoader")
    def test_award_classifications_no_input_data(self, mock_taxonomy_loader, monkeypatch, tmp_path):
        """Missing source data fails instead of classifying built-in samples."""
        mock_loader = Mock()
        mock_loader.load_taxonomy.return_value = Mock(cet_areas=[])
        mock_loader.load_classification_config.return_value = {}
        mock_taxonomy_loader.return_value = mock_loader
        monkeypatch.chdir(tmp_path)

        with pytest.raises(FileNotFoundError, match="No enriched award input"):
            enriched_cet_award_classifications()

    @patch("sbir_analytics.assets.cet.classifications.TaxonomyLoader")
    def test_award_classifications_reject_empty_input(
        self, mock_taxonomy_loader, monkeypatch, tmp_path
    ):
        mock_loader = Mock()
        mock_loader.load_taxonomy.return_value = Mock(cet_areas=[])
        mock_loader.load_classification_config.return_value = {}
        mock_taxonomy_loader.return_value = mock_loader
        monkeypatch.chdir(tmp_path)
        input_path = tmp_path / "data/processed/enriched_sbir_awards.ndjson"
        input_path.parent.mkdir(parents=True)
        input_path.write_text("")

        with pytest.raises(ValueError, match="Enriched award input is empty"):
            enriched_cet_award_classifications()

    @patch("sbir_analytics.assets.cet.classifications.TaxonomyLoader")
    @patch("sbir_analytics.assets.cet.classifications.save_dataframe_parquet")
    def test_award_classifications_model_missing(
        self,
        mock_save,
        mock_taxonomy_loader,
        monkeypatch,
        tmp_path,
    ):
        """Missing model fails without writing a schema-only artifact."""
        mock_loader = Mock()
        mock_loader.load_taxonomy.return_value = Mock(cet_areas=[])
        mock_loader.load_classification_config.return_value = {}
        mock_taxonomy_loader.return_value = mock_loader
        monkeypatch.chdir(tmp_path)
        input_path = tmp_path / "data/processed/enriched_sbir_awards.ndjson"
        input_path.parent.mkdir(parents=True)
        input_path.write_text(json.dumps({"award_id": "AWD-1", "title": "Quantum sensor"}) + "\n")

        with pytest.raises(FileNotFoundError, match="Trained CET award model not found"):
            enriched_cet_award_classifications()

        mock_save.assert_not_called()

    @patch("sbir_ml.ml.features.evidence_extractor.EvidenceExtractor")
    @patch("sbir_ml.ml.models.cet_classifier.ApplicabilityModel.load")
    @patch("sbir_analytics.assets.cet.classifications.TaxonomyLoader")
    @patch("sbir_analytics.assets.cet.classifications.save_dataframe_parquet")
    def test_award_classifications_reject_short_classifier_results(
        self,
        mock_save,
        mock_taxonomy_loader,
        mock_model_load,
        mock_extractor,
        monkeypatch,
        tmp_path,
    ):
        mock_loader = Mock()
        mock_loader.load_taxonomy.return_value = Mock(cet_areas=[], version="v1")
        mock_loader.load_classification_config.return_value = {}
        mock_taxonomy_loader.return_value = mock_loader
        model = Mock(taxonomy_version="v1")
        model.classify_batch.return_value = [[]]
        mock_model_load.return_value = model
        monkeypatch.chdir(tmp_path)
        input_path = tmp_path / "data/processed/enriched_sbir_awards.ndjson"
        input_path.parent.mkdir(parents=True)
        input_path.write_text(
            "\n".join(
                json.dumps({"award_id": award_id, "title": "Quantum sensor", "keywords": []})
                for award_id in ("A-1", "A-2")
            )
            + "\n"
        )
        model_path = tmp_path / "artifacts/models/cet_classifier_v1.pkl"
        model_path.parent.mkdir(parents=True)
        model_path.touch()

        with pytest.raises(ValueError, match="classifier returned 1 results for 2 source rows"):
            enriched_cet_award_classifications()

        mock_extractor.return_value.extract_batch_evidence.assert_not_called()
        mock_save.assert_not_called()

    @patch("sbir_ml.ml.features.evidence_extractor.EvidenceExtractor")
    @patch("sbir_ml.ml.models.cet_classifier.ApplicabilityModel.load")
    @patch("sbir_analytics.assets.cet.classifications.TaxonomyLoader")
    @patch("sbir_analytics.assets.cet.classifications.save_dataframe_parquet")
    def test_award_classifications_reject_short_evidence_results(
        self,
        mock_save,
        mock_taxonomy_loader,
        mock_model_load,
        mock_extractor_class,
        monkeypatch,
        tmp_path,
    ):
        mock_loader = Mock()
        mock_loader.load_taxonomy.return_value = Mock(cet_areas=[], version="v1")
        mock_loader.load_classification_config.return_value = {}
        mock_taxonomy_loader.return_value = mock_loader
        model = Mock(taxonomy_version="v1")
        model.classify_batch.return_value = [[], []]
        mock_model_load.return_value = model
        mock_extractor_class.return_value.extract_batch_evidence.return_value = [[]]
        monkeypatch.chdir(tmp_path)
        input_path = tmp_path / "data/processed/enriched_sbir_awards.ndjson"
        input_path.parent.mkdir(parents=True)
        input_path.write_text(
            "\n".join(
                json.dumps({"award_id": award_id, "title": "Quantum sensor", "keywords": []})
                for award_id in ("A-1", "A-2")
            )
            + "\n"
        )
        model_path = tmp_path / "artifacts/models/cet_classifier_v1.pkl"
        model_path.parent.mkdir(parents=True)
        model_path.touch()

        with pytest.raises(
            ValueError, match="evidence extractor returned 1 results for 2 source rows"
        ):
            enriched_cet_award_classifications()

        mock_save.assert_not_called()


# ==================== Patent Classifications Asset Tests ====================


class TestEnrichedCETPatentClassifications:
    """Tests for enriched CET patent classifications asset."""

    @patch("sbir_analytics.assets.cet.classifications.TaxonomyLoader")
    @patch("sbir_analytics.assets.cet.classifications.save_dataframe_parquet")
    def test_patent_classifications_taxonomy_load_failure(self, mock_save, mock_taxonomy_loader):
        """A taxonomy failure fails the patent materialization without output."""
        mock_loader = Mock()
        mock_loader.load_taxonomy.side_effect = Exception("Taxonomy load failed")
        mock_taxonomy_loader.return_value = mock_loader

        with pytest.raises(RuntimeError, match="taxonomy and classification config"):
            enriched_cet_patent_classifications()

        mock_save.assert_not_called()

    @patch("sbir_analytics.assets.cet.classifications.TaxonomyLoader")
    def test_patent_classifications_no_input_data(
        self, mock_taxonomy_loader, monkeypatch, tmp_path
    ):
        """Missing patent input fails instead of classifying built-in samples."""
        mock_loader = Mock()
        mock_loader.load_taxonomy.return_value = Mock()
        mock_loader.load_classification_config.return_value = {}
        mock_taxonomy_loader.return_value = mock_loader
        monkeypatch.chdir(tmp_path)

        with pytest.raises(FileNotFoundError, match="No transformed patent input"):
            enriched_cet_patent_classifications()

    @patch("sbir_analytics.assets.cet.classifications.TaxonomyLoader")
    def test_patent_classifications_reject_empty_input(
        self, mock_taxonomy_loader, monkeypatch, tmp_path
    ):
        mock_loader = Mock()
        mock_loader.load_taxonomy.return_value = Mock()
        mock_loader.load_classification_config.return_value = {}
        mock_taxonomy_loader.return_value = mock_loader
        monkeypatch.chdir(tmp_path)
        input_path = tmp_path / "data/processed/transformed_patents.ndjson"
        input_path.parent.mkdir(parents=True)
        input_path.write_text("")

        with pytest.raises(ValueError, match="Transformed patent input is empty"):
            enriched_cet_patent_classifications()

    @patch("sbir_ml.ml.models.patent_classifier.PatentFeatureExtractor")
    @patch("sbir_ml.ml.models.patent_classifier.PatentCETClassifier.load")
    @patch("sbir_analytics.assets.cet.classifications.TaxonomyLoader")
    @patch("sbir_analytics.assets.cet.classifications.save_dataframe_parquet")
    def test_patent_classifications_reject_short_feature_results(
        self,
        mock_save,
        mock_taxonomy_loader,
        mock_model_load,
        mock_extractor_class,
        monkeypatch,
        tmp_path,
    ):
        mock_loader = Mock()
        mock_loader.load_taxonomy.return_value = Mock(version="v1")
        mock_loader.load_classification_config.return_value = {}
        mock_taxonomy_loader.return_value = mock_loader
        mock_extractor_class.return_value.transform.return_value = [{"normalized_title": "one"}]
        monkeypatch.chdir(tmp_path)
        input_path = tmp_path / "data/processed/transformed_patents.ndjson"
        input_path.parent.mkdir(parents=True)
        input_path.write_text(
            "\n".join(
                json.dumps({"patent_id": patent_id, "title": "Quantum sensor"})
                for patent_id in ("P-1", "P-2")
            )
            + "\n"
        )
        model_path = tmp_path / "artifacts/models/patent_classifier_v1.pkl"
        model_path.parent.mkdir(parents=True)
        model_path.touch()

        with pytest.raises(
            ValueError, match="feature extractor returned 1 results for 2 source rows"
        ):
            enriched_cet_patent_classifications()

        mock_model_load.return_value.classify_batch.assert_not_called()
        mock_save.assert_not_called()

    @patch("sbir_ml.ml.models.patent_classifier.PatentFeatureExtractor")
    @patch("sbir_ml.ml.models.patent_classifier.PatentCETClassifier.load")
    @patch("sbir_analytics.assets.cet.classifications.TaxonomyLoader")
    @patch("sbir_analytics.assets.cet.classifications.save_dataframe_parquet")
    def test_patent_classifications_reject_short_classifier_results(
        self,
        mock_save,
        mock_taxonomy_loader,
        mock_model_load,
        mock_extractor_class,
        monkeypatch,
        tmp_path,
    ):
        mock_loader = Mock()
        mock_loader.load_taxonomy.return_value = Mock(version="v1")
        mock_loader.load_classification_config.return_value = {}
        mock_taxonomy_loader.return_value = mock_loader
        mock_extractor_class.return_value.transform.return_value = [
            {"normalized_title": "one"},
            {"normalized_title": "two"},
        ]
        classifier = Mock(taxonomy_version="v1")
        classifier.classify_batch.return_value = [[]]
        mock_model_load.return_value = classifier
        monkeypatch.chdir(tmp_path)
        input_path = tmp_path / "data/processed/transformed_patents.ndjson"
        input_path.parent.mkdir(parents=True)
        input_path.write_text(
            "\n".join(
                json.dumps({"patent_id": patent_id, "title": "Quantum sensor"})
                for patent_id in ("P-1", "P-2")
            )
            + "\n"
        )
        model_path = tmp_path / "artifacts/models/patent_classifier_v1.pkl"
        model_path.parent.mkdir(parents=True)
        model_path.touch()

        with pytest.raises(ValueError, match="classifier returned 1 results for 2 source rows"):
            enriched_cet_patent_classifications()

        mock_save.assert_not_called()


# ==================== Edge Cases ====================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_quality_check_empty_checks_file(self, tmp_path):
        """Test quality check handles empty checks file."""
        from dagster import build_op_context

        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text("{}")

        context = build_op_context()

        with patch("sbir_analytics.assets.cet.classifications.Path") as mock_path_class:
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

        with patch("sbir_analytics.assets.cet.classifications.Path") as mock_path_class:
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

    def test_quality_check_file_permission_error(self, tmp_path):
        """Test quality check handles file permission errors."""
        from dagster import build_op_context

        checks_path = tmp_path / "cet_award_classifications.checks.json"
        checks_path.write_text('{"high_conf_rate": 0.75}')
        checks_path.chmod(0o000)  # Remove all permissions

        context = build_op_context()

        with patch("sbir_analytics.assets.cet.classifications.Path") as mock_path_class:
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

        with patch("sbir_analytics.assets.cet.classifications.Path") as mock_path_class:
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

        with patch("sbir_analytics.assets.cet.classifications.Path") as mock_path_class:
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
