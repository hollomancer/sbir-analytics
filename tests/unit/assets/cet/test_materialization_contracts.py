"""Failure and artifact-path contracts for CET materializations."""

import json
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
    mock_save_parquet.side_effect = RuntimeError("parquet unavailable")
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
def test_company_profiles_return_real_json_fallback(
    mock_save_parquet, mock_aggregator_class, monkeypatch, tmp_path
):
    mock_aggregator_class.return_value.to_dataframe.return_value = pd.DataFrame(
        [{"company_id": "C-1", "company_name": "Example"}]
    )
    mock_save_parquet.side_effect = RuntimeError("parquet unavailable")
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "data/processed/cet_award_classifications.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"award_id": "A-1", "company_id": "C-1"}) + "\n")

    result = transformed_cet_company_profiles()

    assert result.value == "data/processed/cet_company_profiles.json"
    assert (tmp_path / result.value).is_file()
    assert not (tmp_path / "data/processed/cet_company_profiles.parquet").exists()
