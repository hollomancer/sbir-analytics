"""Contract tests for CET Neo4j loading assets."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from dagster import build_op_context

from sbir_analytics.assets.cet import loading
from sbir_analytics.assets.cet.utils import _read_parquet_or_ndjson

pytestmark = pytest.mark.fast


def _taxonomy_context(parquet_path, json_path):
    return build_op_context(
        op_config={
            "create_constraints": False,
            "create_indexes": False,
            "taxonomy_parquet": str(parquet_path),
            "taxonomy_json": str(json_path),
            "batch_size": 10,
        }
    )


def _award_context(parquet_path, json_path):
    return build_op_context(
        op_config={
            "award_class_parquet": str(parquet_path),
            "award_class_json": str(json_path),
            "batch_size": 10,
        }
    )


def test_reader_rejects_malformed_ndjson(tmp_path):
    json_path = tmp_path / "taxonomy.json"
    json_path.write_text("not json\n")

    with pytest.raises(ValueError, match="line 1"):
        _read_parquet_or_ndjson(
            tmp_path / "taxonomy.parquet",
            json_path,
            expected_columns=("cet_id", "name"),
        )


def test_reader_rejects_missing_required_fields(tmp_path):
    json_path = tmp_path / "taxonomy.json"
    json_path.write_text(json.dumps({"cet_id": "quantum"}) + "\n")

    with pytest.raises(ValueError, match="missing required fields: name"):
        _read_parquet_or_ndjson(
            tmp_path / "taxonomy.parquet",
            json_path,
            expected_columns=("cet_id", "name"),
        )


@patch.dict("os.environ", {"SKIP_NEO4J_LOADING": "true"})
@patch("sbir_analytics.assets.cet.loading._connected_client")
def test_explicit_skip_is_the_only_successful_skip(mock_client, tmp_path):
    context = _taxonomy_context(tmp_path / "missing.parquet", tmp_path / "missing.json")

    result = loading.loaded_cet_areas(context, None)

    assert result == {"status": "skipped", "reason": "explicit_skip"}
    mock_client.assert_not_called()


@patch.dict("os.environ", {"SKIP_NEO4J_LOADING": "false"})
@patch("sbir_analytics.assets.cet.loading.CETLoader", None)
def test_missing_loader_fails_materialization(tmp_path):
    context = _taxonomy_context(tmp_path / "missing.parquet", tmp_path / "missing.json")

    with pytest.raises(RuntimeError, match="loader dependencies"):
        loading.loaded_cet_areas(context, None)


@patch.dict("os.environ", {"SKIP_NEO4J_LOADING": "false"})
@patch("sbir_analytics.assets.cet.loading._connected_client")
@patch("sbir_analytics.assets.cet.loading.CETLoader")
def test_loader_exception_propagates_and_closes_client(
    mock_loader_class, mock_connected_client, tmp_path
):
    source = tmp_path / "taxonomy.json"
    source.write_text(
        json.dumps({"cet_id": "quantum", "name": "Quantum", "taxonomy_version": "v1"}) + "\n"
    )
    client = mock_connected_client.return_value
    mock_loader_class.return_value.load_cet_areas.side_effect = RuntimeError("database rejected")
    context = _taxonomy_context(tmp_path / "taxonomy.parquet", source)

    with pytest.raises(RuntimeError, match="database rejected"):
        loading.loaded_cet_areas(context, None)

    client.close.assert_called_once_with()


@patch.dict("os.environ", {"SKIP_NEO4J_LOADING": "false"})
@patch("sbir_analytics.assets.cet.loading._write_summary")
@patch("sbir_analytics.assets.cet.loading._connected_client")
@patch("sbir_analytics.assets.cet.loading.CETLoader")
def test_summary_persistence_failure_propagates_and_closes_client(
    mock_loader_class, mock_connected_client, mock_write_summary, tmp_path
):
    source = tmp_path / "taxonomy.json"
    source.write_text(
        json.dumps({"cet_id": "quantum", "name": "Quantum", "taxonomy_version": "v1"}) + "\n"
    )
    mock_loader_class.return_value.load_cet_areas.return_value = SimpleNamespace(errors=0)
    mock_write_summary.side_effect = OSError("disk full")
    context = _taxonomy_context(tmp_path / "taxonomy.parquet", source)

    with pytest.raises(OSError, match="disk full"):
        loading.loaded_cet_areas(context, None)

    mock_connected_client.return_value.close.assert_called_once_with()


@patch.dict("os.environ", {"SKIP_NEO4J_LOADING": "false"})
@patch("sbir_analytics.assets.cet.loading._write_summary")
@patch("sbir_analytics.assets.cet.loading._connected_client")
@patch("sbir_analytics.assets.cet.loading.CETLoader")
def test_award_enrichment_calls_real_loader_api(
    mock_loader_class, mock_connected_client, mock_write_summary, tmp_path
):
    source = tmp_path / "classifications.json"
    source.write_text(
        json.dumps(
            {
                "award_id": "A-1",
                "primary_cet": "quantum",
                "primary_score": 0.91,
                "supporting_cets": [{"cet_id": "ai"}],
                "taxonomy_version": "v1",
            }
        )
        + "\n"
    )
    loader_instance = mock_loader_class.return_value
    loader_instance.upsert_award_cet_enrichment.return_value = SimpleNamespace(errors=0)
    context = _award_context(tmp_path / "classifications.parquet", source)

    result = loading.loaded_award_cet_enrichment(context, None, None)

    enrichments = loader_instance.upsert_award_cet_enrichment.call_args.args[0]
    assert enrichments == [
        {
            "award_id": "A-1",
            "cet_primary_id": "quantum",
            "cet_primary_score": 0.91,
            "cet_supporting_ids": ["ai"],
            "cet_taxonomy_version": "v1",
            "cet_classified_at": None,
            "cet_model_version": None,
        }
    ]
    assert result["status"] == "success"
    mock_write_summary.assert_called_once()
    mock_connected_client.return_value.close.assert_called_once_with()


def test_nonzero_loader_errors_fail_materialization():
    with pytest.raises(RuntimeError, match="2 loader error"):
        loading._ensure_successful_metrics(SimpleNamespace(errors=2), "test load")


def test_company_enrichment_maps_profile_schema():
    result = loading._company_enrichments(
        [
            {
                "company_id": "C-1",
                "dominant_cet": "quantum",
                "dominant_score": 0.8,
                "specialization_score": 0.6,
                "cet_scores": {"quantum": 0.8, "ai": 0.2},
                "taxonomy_version": "v1",
            }
        ]
    )

    assert result[0]["company_id"] == "C-1"
    assert result[0]["cet_dominant_id"] == "quantum"
    assert result[0]["cet_areas"] == ["quantum", "ai"]
