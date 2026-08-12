"""Contract tests for CET Neo4j loading assets."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from dagster import build_op_context

from sbir_analytics.assets.cet import company, loading
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


def _company_context(parquet_path, json_path):
    return build_op_context(
        op_config={
            "company_profiles_parquet": str(parquet_path),
            "company_profiles_json": str(json_path),
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


def test_reader_rejects_empty_ndjson(tmp_path):
    json_path = tmp_path / "taxonomy.json"
    json_path.write_text("\n")

    with pytest.raises(ValueError, match="contains no records"):
        _read_parquet_or_ndjson(
            tmp_path / "taxonomy.parquet",
            json_path,
            expected_columns=("cet_id", "name"),
        )


def test_reader_allows_empty_only_when_explicitly_requested(tmp_path):
    json_path = tmp_path / "taxonomy.json"
    json_path.write_text("")

    assert (
        _read_parquet_or_ndjson(
            tmp_path / "taxonomy.parquet",
            json_path,
            expected_columns=("cet_id", "name"),
            allow_empty=True,
        )
        == []
    )


def test_reader_rejects_empty_parquet(tmp_path):
    parquet_path = tmp_path / "taxonomy.parquet"
    pytest.importorskip("pyarrow")
    import pandas as pd

    pd.DataFrame(columns=["cet_id", "name"]).to_parquet(parquet_path)

    with pytest.raises(ValueError, match="contains no records"):
        _read_parquet_or_ndjson(
            parquet_path,
            tmp_path / "taxonomy.json",
            expected_columns=("cet_id", "name"),
        )


@patch.dict("os.environ", {"SKIP_NEO4J_LOADING": "true"})
@patch("sbir_analytics.assets.cet.loading._connected_client")
def test_explicit_skip_is_the_only_successful_skip(mock_client, tmp_path):
    context = _taxonomy_context(tmp_path / "missing.parquet", tmp_path / "missing.json")

    result = loading.loaded_cet_areas(context, None)

    assert result == {"status": "skipped", "reason": "explicit_skip"}
    mock_client.assert_not_called()


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes"])
def test_skip_gate_and_client_factory_accept_the_same_values(value, tmp_path):
    """The skip gate must never disagree with the client factory.

    If one accepted a value the other rejected, the asset would decline to skip and
    then demand a connection the factory had already given up on.
    """
    context = _taxonomy_context(tmp_path / "missing.parquet", tmp_path / "missing.json")

    with patch.dict("os.environ", {"SKIP_NEO4J_LOADING": value}):
        assert loading._skip_requested(context, "CETArea loading") is True
        with patch.object(company, "Neo4jClient", None), patch.object(company, "Neo4jConfig", None):
            assert company._get_neo4j_client() is None


@pytest.mark.parametrize("value", ["false", "no", "0", ""])
def test_skip_gate_and_client_factory_reject_the_same_values(value, tmp_path):
    context = _taxonomy_context(tmp_path / "missing.parquet", tmp_path / "missing.json")

    with patch.dict("os.environ", {"SKIP_NEO4J_LOADING": value}):
        assert loading._skip_requested(context, "CETArea loading") is False
        with (
            patch.object(company, "Neo4jClient", None),
            patch.object(company, "Neo4jConfig", None),
            pytest.raises(RuntimeError, match="not skipped"),
        ):
            company._get_neo4j_client()


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
    loader_instance.upsert_award_cet_enrichment.return_value = SimpleNamespace(
        errors=0, nodes_updated={"FinancialTransaction": 1}
    )
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


@patch.dict("os.environ", {"SKIP_NEO4J_LOADING": "false"})
@patch("sbir_analytics.assets.cet.loading._write_summary")
@patch("sbir_analytics.assets.cet.loading._connected_client")
@patch("sbir_analytics.assets.cet.loading.CETLoader")
def test_nonzero_loader_errors_fail_asset_and_persist_summary(
    mock_loader_class, mock_connected_client, mock_write_summary, tmp_path
):
    source = tmp_path / "classifications.json"
    source.write_text(json.dumps({"award_id": "A-1", "primary_cet": "quantum"}) + "\n")
    mock_loader_class.return_value.upsert_award_cet_enrichment.return_value = SimpleNamespace(
        errors=2, nodes_updated={"FinancialTransaction": 1}
    )
    context = _award_context(tmp_path / "classifications.parquet", source)

    with pytest.raises(RuntimeError, match="2 loader error"):
        loading.loaded_award_cet_enrichment(context, None, None)

    summary = mock_write_summary.call_args.args[1]
    assert summary["status"] == "error"
    assert summary["errors"] == 2
    mock_connected_client.return_value.close.assert_called_once_with()


@patch("sbir_analytics.assets.cet.loading._write_summary")
def test_zero_progress_fails_after_persisting_failure_summary(mock_write_summary):
    metrics = SimpleNamespace(errors=0, nodes_updated={"Organization": 0})

    with pytest.raises(RuntimeError, match="processed 0/2"):
        loading._complete_load(
            filename="company.json",
            operation="Company CET enrichment",
            count_field="companies",
            submitted=2,
            processed=loading._metric_count(metrics, "nodes_updated", "Organization"),
            metrics=metrics,
        )

    summary = mock_write_summary.call_args.args[1]
    assert summary["status"] == "error"
    assert summary["submitted"] == 2
    assert summary["processed"] == 0
    assert summary["match_rate"] == 0.0


@patch.dict("os.environ", {"SKIP_NEO4J_LOADING": "false"})
@patch("sbir_analytics.assets.cet.loading._write_summary")
@patch("sbir_analytics.assets.cet.loading._connected_client")
@patch("sbir_analytics.assets.cet.loading.CETLoader")
def test_company_enrichment_fails_when_no_organizations_match(
    mock_loader_class, mock_connected_client, mock_write_summary, tmp_path
):
    source = tmp_path / "profiles.json"
    source.write_text(
        json.dumps(
            {
                "company_uei": "ABCD1234EFGH",
                "dominant_cet": "quantum",
                "specialization_score": 0.8,
            }
        )
        + "\n"
    )
    mock_loader_class.return_value.upsert_company_cet_enrichment.return_value = SimpleNamespace(
        errors=0, nodes_updated={"Organization": 0}
    )
    context = _company_context(tmp_path / "profiles.parquet", source)

    with pytest.raises(RuntimeError, match="processed 0/1"):
        loading.loaded_company_cet_enrichment(context, None, None)

    summary = mock_write_summary.call_args.args[1]
    assert summary["status"] == "error"
    assert summary["match_rate"] == 0.0
    loader_call = mock_loader_class.return_value.upsert_company_cet_enrichment.call_args
    assert loader_call.kwargs["key_property"] == "uei"
    assert loader_call.args[0][0]["uei"] == "ABCD1234EFGH"
    mock_connected_client.return_value.close.assert_called_once_with()


@patch.dict("os.environ", {"SKIP_NEO4J_LOADING": "false"})
@patch("sbir_analytics.assets.cet.company.Neo4jClient")
@patch("sbir_analytics.assets.cet.company.Neo4jConfig")
def test_neo4j_client_factory_uses_username_contract(mock_config, mock_client):
    client = mock_client.return_value
    client.session.return_value.__enter__.return_value.run.return_value = None

    assert company._get_neo4j_client() is client

    kwargs = mock_config.call_args.kwargs
    assert kwargs["username"] == company.DEFAULT_NEO4J_USER
    assert "user" not in kwargs


def test_company_enrichment_maps_profile_schema():
    result = loading._company_enrichments(
        [
            {
                "company_uei": "ABCD1234EFGH",
                "dominant_cet": "quantum",
                "dominant_score": 0.8,
                "specialization_score": 0.6,
                "cet_scores": {"quantum": 0.8, "ai": 0.2},
                "taxonomy_version": "v1",
            }
        ]
    )

    assert result[0]["uei"] == "ABCD1234EFGH"
    assert result[0]["cet_dominant_id"] == "quantum"
    assert result[0]["cet_areas"] == ["quantum", "ai"]
