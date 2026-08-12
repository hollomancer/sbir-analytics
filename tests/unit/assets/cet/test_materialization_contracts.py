"""Failure and artifact-path contracts for CET materializations."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from sbir_analytics.assets.cet.company import transformed_cet_company_profiles
from sbir_analytics.assets.cet.training import (
    cet_award_training_dataset,
    train_cet_patent_classifier,
)

pytestmark = pytest.mark.fast


def test_patent_training_requires_source_data(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError, match="CET patent training data not found"):
        train_cet_patent_classifier()

    assert not (tmp_path / "artifacts/models/patent_classifier_v1.pkl").exists()


@patch("sbir_analytics.assets.cet.training.TaxonomyLoader")
def test_award_training_requires_source_data(mock_taxonomy_loader, monkeypatch, tmp_path):
    mock_taxonomy_loader.return_value.load_taxonomy.return_value = SimpleNamespace(version="v1")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError, match="CET award training data not found"):
        cet_award_training_dataset()

    assert not (tmp_path / "data/processed/cet_award_training.parquet").exists()


@patch("sbir_analytics.assets.cet.training.TaxonomyLoader")
def test_award_training_reports_malformed_ndjson_as_value_error(
    mock_taxonomy_loader, monkeypatch, tmp_path
):
    """A malformed line names its own defect; wrapping it as RuntimeError would hide it."""
    mock_taxonomy_loader.return_value.load_taxonomy.return_value = SimpleNamespace(version="v1")
    monkeypatch.chdir(tmp_path)
    training_input = tmp_path / "data/processed/cet_award_training.ndjson"
    training_input.parent.mkdir(parents=True, exist_ok=True)
    training_input.write_text('{"text": "ok", "labels": ["a"]}\nnot json\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON in .* at line 2"):
        cet_award_training_dataset()


@patch("sbir_analytics.assets.cet.company.save_dataframe_parquet")
def test_company_profiles_require_classification_input(mock_save, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError, match="No CET award classifications found"):
        transformed_cet_company_profiles()

    mock_save.assert_not_called()


@patch("sbir_analytics.assets.cet.training.TaxonomyLoader")
@patch("sbir_analytics.assets.cet.training.save_dataframe_parquet")
def test_award_training_returns_real_ndjson_fallback(
    mock_save_parquet,
    mock_taxonomy_loader,
    monkeypatch,
    tmp_path,
):
    mock_taxonomy_loader.return_value.load_taxonomy.return_value = SimpleNamespace(version="v1")

    def save_as_ndjson(df, path):
        actual_path = Path(path).with_suffix(".ndjson")
        actual_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_json(actual_path, orient="records", lines=True)
        return actual_path

    mock_save_parquet.side_effect = save_as_ndjson
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "data/processed/cet_award_training.ndjson"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"text": "quantum sensor", "labels": ["quantum"]}) + "\n")

    result = cet_award_training_dataset()

    assert result.value == "data/processed/cet_award_training.ndjson"
    assert (tmp_path / result.value).is_file()
    assert not (tmp_path / "data/processed/cet_award_training.parquet").exists()


@patch("sbir_etl.transformers.company_cet_aggregator.CompanyCETAggregator")
@patch("sbir_analytics.assets.cet.company.save_dataframe_parquet")
def test_company_profiles_return_real_ndjson_fallback(
    mock_save_parquet, mock_aggregator_class, monkeypatch, tmp_path
):
    mock_aggregator_class.return_value.to_dataframe.return_value = pd.DataFrame(
        [{"company_id": "ABCD1234EFGH", "company_name": "Example"}]
    )

    def save_as_ndjson(df, path):
        actual_path = Path(path).with_suffix(".ndjson")
        actual_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_json(actual_path, orient="records", lines=True)
        return actual_path

    mock_save_parquet.side_effect = save_as_ndjson
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "data/processed/cet_award_classifications.ndjson"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"award_id": "A-1", "company_uei": "ABCD1234EFGH"}) + "\n")

    result = transformed_cet_company_profiles()

    assert result.value == "data/processed/cet_company_profiles.ndjson"
    assert (tmp_path / result.value).is_file()
    assert not (tmp_path / "data/processed/cet_company_profiles.parquet").exists()


@patch("sbir_etl.transformers.company_cet_aggregator.CompanyCETAggregator")
@patch("sbir_analytics.assets.cet.company.save_dataframe_parquet")
def test_company_profiles_reject_empty_classification_input(
    mock_save_parquet, mock_aggregator_class, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "data/processed/cet_award_classifications.ndjson"
    source.parent.mkdir(parents=True)
    source.write_text("")

    with pytest.raises(ValueError, match="classification input is empty"):
        transformed_cet_company_profiles()

    mock_aggregator_class.assert_not_called()
    mock_save_parquet.assert_not_called()


@patch("sbir_etl.transformers.company_cet_aggregator.CompanyCETAggregator")
@patch("sbir_analytics.assets.cet.company.save_dataframe_parquet")
def test_company_profiles_require_usable_company_identifiers(
    mock_save_parquet, mock_aggregator_class, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "data/processed/cet_award_classifications.ndjson"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"award_id": "A-1", "primary_cet": "quantum"}) + "\n")

    with pytest.raises(ValueError, match="no usable company identifiers"):
        transformed_cet_company_profiles()

    mock_aggregator_class.assert_not_called()
    mock_save_parquet.assert_not_called()


@patch("sbir_etl.transformers.company_cet_aggregator.CompanyCETAggregator")
@patch("sbir_analytics.assets.cet.company.save_dataframe_parquet")
def test_company_profiles_reject_empty_aggregation(
    mock_save_parquet, mock_aggregator_class, monkeypatch, tmp_path
):
    mock_aggregator_class.return_value.to_dataframe.return_value = pd.DataFrame()
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "data/processed/cet_award_classifications.ndjson"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"award_id": "A-1", "company_uei": "ABCD1234EFGH"}) + "\n")

    with pytest.raises(ValueError, match="produced no company profiles"):
        transformed_cet_company_profiles()

    mock_save_parquet.assert_not_called()
