from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.fast


# Skip if neo4j driver isn't available, consistent with existing unit test patterns
pytest.importorskip("neo4j", reason="neo4j driver missing")

from src.loaders.cet_loader import CETLoader, CETLoaderConfig  # type: ignore
from src.loaders.neo4j_client import LoadMetrics  # type: ignore


def _make_mock_client_with_capture():
    """
    Create a mock Neo4jClient with:
    - a .config object exposing batch_size
    - a batch_upsert_nodes side effect capturing arguments
    Returns (mock_client, captured_dict)
    """

    class _Cfg:
        batch_size = 0

    captured: dict[str, Any] = {}

    mock_client = MagicMock()
    mock_client.config = _Cfg()

    def _fake_batch_upsert_nodes(
        label: str, key_property: str, nodes: list[dict[str, Any]], metrics=None
    ):
        captured["label"] = label
        captured["key_property"] = key_property
        captured["nodes"] = nodes
        m = metrics or LoadMetrics()
        m.nodes_created[label] = m.nodes_created.get(label, 0) + len(nodes)
        return m

    mock_client.batch_upsert_nodes.side_effect = _fake_batch_upsert_nodes
    return mock_client, captured


class TestCETLoaderLoadAreas:
    def test_load_cet_areas_normalization_and_required_filtering(self):
        mock_client, captured = _make_mock_client_with_capture()
        loader = CETLoader(mock_client, CETLoaderConfig(batch_size=123))

        areas = [
            {
                "cet_id": "AI",
                "name": "Artificial Intelligence",
                "definition": None,  # should be omitted
                "keywords": ["ML", "ml", "Neural "],
                "taxonomy_version": "V1",
            },
            {
                # missing cet_id -> should be skipped and count as error
                "name": "Missing ID",
                "taxonomy_version": "V1",
                "keywords": ["x"],
            },
            {
                "cet_id": "QIS",
                "name": " Quantum ",
                "definition": "  Quantum computing  ",
                "keywords": [],
                "taxonomy_version": "V1",
            },
        ]

        metrics = loader.load_cet_areas(areas)

        # Client batch size should be applied from loader config
        assert mock_client.config.batch_size == 123

        # Ensure batch_upsert_nodes called correctly
        assert captured["label"] == "CETArea"
        assert captured["key_property"] == "cet_id"
        nodes = captured["nodes"]
        assert len(nodes) == 2  # one entry skipped for missing cet_id
        assert isinstance(metrics, LoadMetrics)
        assert metrics.errors == 1

        # Validate normalization for first node
        ai = next(n for n in nodes if n["cet_id"] == "AI")
        assert ai["name"] == "Artificial Intelligence"
        assert ai["taxonomy_version"] == "V1"
        # keywords lowered and deduplicated
        assert sorted(ai.get("keywords", [])) == ["ml", "neural"]
        # definition omitted when None
        assert "definition" not in ai

        # Validate trimming for second node
        qis = next(n for n in nodes if n["cet_id"] == "QIS")
        assert qis["name"] == "Quantum"  # stripped
        assert qis["definition"] == "Quantum computing"  # stripped
        # empty keyword list is allowed
        assert isinstance(qis.get("keywords", []), list)


class TestCETLoaderCompanyEnrichment:
    def test_upsert_company_cet_enrichment_fields_and_autotimestamp(self):
        mock_client, captured = _make_mock_client_with_capture()
        loader = CETLoader(mock_client, CETLoaderConfig(batch_size=256))

        enrichments = [
            {
                "uei": "UEI123",
                "cet_dominant_id": " AI ",
                "cet_dominant_score": "85.2",
                "cet_specialization_score": 0.75,
                "cet_areas": ["AI", "AI", "QIS", ""],
                "cet_taxonomy_version": "V-TAX",
                # omit cet_profile_updated_at to trigger auto timestamp
            },
            {
                # missing uei -> should be skipped and count as error
                "cet_dominant_id": "QIS",
                "cet_dominant_score": 65.0,
            },
        ]

        metrics = loader.upsert_company_cet_enrichment(enrichments, key_property="uei")

        # Client batch size applied
        assert mock_client.config.batch_size == 256

        # Only one node should be upserted (second skipped)
        nodes = captured["nodes"]
        assert len(nodes) == 1
        node = nodes[0]

        # Validate key and fields
        assert node["uei"] == "UEI123"
        assert node["cet_dominant_id"] == "AI"  # trimmed
        assert node["cet_dominant_score"] == 85.2  # coerced to float
        assert node["cet_specialization_score"] == 0.75
        # cet_areas are unique and sorted, no lowercasing enforced for areas
        assert node["cet_areas"] == ["AI", "QIS"]
        assert node["cet_taxonomy_version"] == "V-TAX"

        # Auto-updated timestamp exists and is ISO-like
        ts = node.get("cet_profile_updated_at")
        assert isinstance(ts, str) and len(ts) >= 10
        # Try permissive parse
        try:
            # fromisoformat accepts many ISO forms (without Z)
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            pytest.fail(f"cet_profile_updated_at is not ISO-parsable: {ts}")

        # Metrics reflect one skipped row
        assert isinstance(metrics, LoadMetrics)
        assert metrics.errors == 1

        # Called with correct label/key
        assert captured["label"] == "Company"
        assert captured["key_property"] == "uei"

    def test_upsert_company_cet_enrichment_custom_key_property(self):
        mock_client, captured = _make_mock_client_with_capture()
        loader = CETLoader(mock_client)

        enrichments = [
            {
                "company_id": "C-001",
                "cet_dominant_id": "QIS",
                "cet_dominant_score": 60.1,
                "cet_specialization_score": 0.25,
                "cet_areas": ["QIS"],
            }
        ]

        loader.upsert_company_cet_enrichment(enrichments, key_property="company_id")

        nodes = captured["nodes"]
        assert len(nodes) == 1
        assert nodes[0]["company_id"] == "C-001"
        assert captured["label"] == "Company"
        assert captured["key_property"] == "company_id"


class TestCETLoaderAwardEnrichment:
    def test_upsert_award_cet_enrichment_supporting_ids_and_autotimestamp(self):
        mock_client, captured = _make_mock_client_with_capture()
        loader = CETLoader(mock_client, CETLoaderConfig(batch_size=64))

        rows = [
            {
                "award_id": "A-001",
                "cet_primary_id": "QIS",
                "cet_primary_score": "77",  # should coerce to float
                "cet_supporting_ids": ["AI", "AI", "ML", ""],  # should dedup/sort and drop blank
                "cet_taxonomy_version": "V1",
                # omit cet_classified_at to trigger auto timestamp
                "cet_model_version": "vtest",
            },
            {
                # Missing award_id -> error and skip
                "cet_primary_id": "AI",
                "cet_primary_score": 80.0,
            },
        ]

        metrics = loader.upsert_award_cet_enrichment(rows, key_property="award_id")

        # Client batch size applied
        assert mock_client.config.batch_size == 64

        nodes = captured["nodes"]
        assert len(nodes) == 1
        node = nodes[0]
        assert node["award_id"] == "A-001"
        assert node["cet_primary_id"] == "QIS"
        assert node["cet_primary_score"] == 77.0
        # supporting_ids: unique, sorted
        assert node["cet_supporting_ids"] == ["AI", "ML"]
        assert node["cet_taxonomy_version"] == "V1"
        assert node["cet_model_version"] == "vtest"

        # classified_at auto-added and ISO-like
        ts = node.get("cet_classified_at")
        assert isinstance(ts, str) and len(ts) >= 10
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            pytest.fail(f"cet_classified_at is not ISO-parsable: {ts}")

        assert isinstance(metrics, LoadMetrics)
        assert metrics.errors == 1

        assert captured["label"] == "Award"
        assert captured["key_property"] == "award_id"
