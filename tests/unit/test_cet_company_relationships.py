import json
from typing import Any
from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.fast


# Loader tests require neo4j driver availability in the environment (match existing project pattern)
pytest.importorskip("neo4j", reason="neo4j driver missing")

from src.loaders.neo4j import CETLoader, LoadMetrics  # type: ignore


# -----------------------------
# Helpers for asset invocation
# -----------------------------
class DummyLog:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


class DummyContext:
    def __init__(self, op_config: dict[str, Any] | None = None):
        self.op_config = op_config or {}
        self.log = DummyLog()


try:
    HAVE_BUILD_CONTEXT = True
except Exception:  # pragma: no cover
    HAVE_BUILD_CONTEXT = False


# -----------------------------
# CETLoader relationship tests
# -----------------------------
def test_create_company_cet_relationships_dominant_props():
    """
    Validate that CETLoader.create_company_cet_relationships:
    - Emits one relationship tuple for the dominant CET
    - Produces correct relationship properties
    - Updates metrics with the created relationships count
    """
    captured: dict[str, Any] = {}

    def _fake_batch_create_relationships(*, relationships, metrics):
        captured["relationships"] = relationships
        m = LoadMetrics()
        m.relationships_created = {"SPECIALIZES_IN": len(relationships)}
        return m

    mock_client = MagicMock()
    mock_client.batch_create_relationships.side_effect = _fake_batch_create_relationships

    loader = CETLoader(mock_client)

    row = {
        "uei": "UEI-001",
        "dominant_cet": "artificial_intelligence",
        "dominant_score": 82.3,
        "specialization_score": 0.64,
        "taxonomy_version": "TEST-2025Q1",
    }

    metrics = loader.create_company_cet_relationships([row])

    # Ensure batch was called with one relationship
    assert mock_client.batch_create_relationships.call_count == 1
    relationships = captured.get("relationships") or []
    assert len(relationships) == 1

    # Tuple structure: (source_label, source_key, source_value, target_label, target_key, target_value, rel_type, props)
    r = relationships[0]
    assert r[0:7] == (
        "Company",
        "uei",
        "UEI-001",
        "CETArea",
        "cet_id",
        "artificial_intelligence",
        "SPECIALIZES_IN",
    )

    props = r[7]
    assert props["primary"] is True
    assert props["role"] == "DOMINANT"
    assert pytest.approx(props["score"], rel=1e-6) == 82.3
    assert pytest.approx(props["specialization_score"], rel=1e-6) == 0.64
    assert props["taxonomy_version"] == "TEST-2025Q1"

    # Metrics reflect created relationships
    assert metrics.relationships_created.get("SPECIALIZES_IN", 0) == 1


def test_create_company_cet_relationships_alternate_field_names_and_custom_key():
    """
    Support alternate field names used by enrichment:
    - cet_dominant_id, cet_dominant_score, cet_specialization_score, cet_taxonomy_version
    Also ensure custom key_property works (company_id).
    """
    captured: dict[str, Any] = {}

    def _fake_batch_create_relationships(*, relationships, metrics):
        captured["relationships"] = relationships
        m = LoadMetrics()
        m.relationships_created = {"SPECIALIZES_IN": len(relationships)}
        return m

    mock_client = MagicMock()
    mock_client.batch_create_relationships.side_effect = _fake_batch_create_relationships

    loader = CETLoader(mock_client)

    row = {
        "company_id": "C-123",
        "cet_dominant_id": "quantum_information_science",
        "cet_dominant_score": "70.0",  # coercion to float
        "cet_specialization_score": 0.3,
        "cet_taxonomy_version": "TEST-X",
    }

    metrics = loader.create_company_cet_relationships(
        [row], key_property="company_id", rel_type="SPECIALIZES_IN"
    )

    relationships = captured.get("relationships") or []
    assert len(relationships) == 1
    r = relationships[0]
    assert r[0:7] == (
        "Company",
        "company_id",
        "C-123",
        "CETArea",
        "cet_id",
        "quantum_information_science",
        "SPECIALIZES_IN",
    )

    props = r[7]
    assert props["primary"] is True
    assert props["role"] == "DOMINANT"
    assert pytest.approx(props["score"], rel=1e-6) == 70.0
    assert pytest.approx(props["specialization_score"], rel=1e-6) == 0.3
    assert props["taxonomy_version"] == "TEST-X"
    assert metrics.relationships_created.get("SPECIALIZES_IN", 0) == 1


def test_create_company_cet_relationships_missing_key_and_missing_cet_are_skipped():
    """
    Rows missing company key or dominant CET should be skipped and counted as errors.
    """
    captured: dict[str, Any] = {}

    def _fake_batch_create_relationships(*, relationships, metrics):
        captured["relationships"] = relationships
        # Use the metrics object passed in (preserves errors already counted by loader)
        metrics.relationships_created = {"SPECIALIZES_IN": len(relationships)}
        return metrics

    mock_client = MagicMock()
    mock_client.batch_create_relationships.side_effect = _fake_batch_create_relationships

    loader = CETLoader(mock_client)

    rows = [
        {
            # missing uei
            "dominant_cet": "ai",
            "dominant_score": 50.0,
        },
        {
            "uei": "UEI-OK",
            # missing dominant_cet
            "dominant_score": 66.6,
        },
        {
            # valid row to ensure we still create relationships
            "uei": "UEI-OK2",
            "dominant_cet": "ai",
            "dominant_score": 90.0,
        },
    ]

    metrics = loader.create_company_cet_relationships(rows)

    # One valid relationship created
    relationships = captured.get("relationships") or []
    assert len(relationships) == 1
    assert metrics.relationships_created.get("SPECIALIZES_IN", 0) == 1
    # Two errors for the two invalid inputs
    assert metrics.errors == 2


# -----------------------------
# Asset tests (no neo4j needed)
# -----------------------------
def test_asset_neo4j_company_cet_relationships_invokes_loader(monkeypatch, tmp_path):
    """
    Validate that the Dagster asset:
    - Reads input rows via helper
    - Invokes CETLoader.load_company_cet_relationships with those rows and returns serialized metrics
    """
    import importlib

    monkeypatch.chdir(tmp_path)
    mod = importlib.import_module("src.assets.cet_assets")

    # Prepare fake input rows (using company_uei as expected by the asset)
    rows = [
        {
            "company_uei": "UEI-1",
            "dominant_cet": "artificial_intelligence",
            "specialization_score": 0.5,
            "award_count": 10,
            "total_funding": 1000000,
        },
        {
            "company_uei": "UEI-2",
            "dominant_cet": "quantum_information_science",
            "specialization_score": 0.3,
            "award_count": 5,
            "total_funding": 500000,
        },
    ]

    expected_rels = 2  # one per row

    # Fake Metrics and Loader
    class FakeMetrics:
        def __init__(self, count: int):
            self.nodes_created = {}
            self.nodes_updated = {}
            self.relationships_created = {"SPECIALIZES_IN": count}
            self.errors = 0

    class FakeLoader:
        def __init__(self, client, config):
            self.client = client
            self.config = config
            self.rows_received = None

        def load_company_cet_relationships(self, rows_in):
            """Match the actual method name in CETLoader."""
            self.rows_received = list(rows_in)
            # Count relationships as the number of rows with dominant CET present
            count = sum(1 for r in self.rows_received if r.get("dominant_cet"))
            return FakeMetrics(count)

        def close(self):
            pass

    # Patch asset internals to avoid real IO/Neo4j
    monkeypatch.setattr("src.assets.cet.loading._get_neo4j_client", lambda: FakeLoader(None, None))
    monkeypatch.setattr("src.assets.cet.loading._read_parquet_or_ndjson", lambda *args, **kwargs: rows)
    monkeypatch.setattr("src.assets.cet.loading.CETLoader", FakeLoader)
    monkeypatch.setattr("src.assets.cet.loading.CETLoaderConfig", lambda batch_size: {"batch_size": batch_size})

    # Execute asset using Dagster's proper context
    from dagster import build_op_context

    ctx = build_op_context(
        config={
            "company_profiles_parquet": "fake.parquet",
            "company_profiles_json": "fake.json",
            "batch_size": 100,
        }
    )

    from src.assets.cet.loading import loaded_company_cet_relationships as asset_fn

    result = asset_fn(ctx, None, None, None)

    assert result["status"] == "success"
    assert result["companies"] == len(rows)
    assert result["metrics"]["relationships_created"]["SPECIALIZES_IN"] == expected_rels

    # If the asset created a checks file, validate JSON structure (best-effort)
    checks_path = (
        tmp_path / "data" / "loaded" / "neo4j" / "neo4j_company_cet_relationships.checks.json"
    )
    if checks_path.exists():
        with checks_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        assert payload.get("status") == "success"
        assert payload.get("companies") == len(rows)


@pytest.mark.skip(reason="Fallback key_property behavior no longer exists in current implementation")
def test_asset_neo4j_company_cet_relationships_fallback_key_property(monkeypatch, tmp_path):
    """
    DEPRECATED: This test verified fallback behavior that no longer exists.
    The current implementation uses company_uei directly without fallback logic.
    """
    import importlib

    monkeypatch.chdir(tmp_path)
    mod = importlib.import_module("src.assets.cet_assets")

    # Rows with no 'uei' field populated; only 'company_id' present
    rows = [
        {
            "company_id": "C-1",
            "dominant_cet": "artificial_intelligence",
            "dominant_score": 80.0,
            "specialization_score": 0.5,
            "taxonomy_version": "TEST-2025Q1",
        }
    ]

    class FakeMetrics:
        def __init__(self, count: int, rel_type: str):
            self.nodes_created = {}
            self.nodes_updated = {}
            self.relationships_created = {rel_type: count}
            self.errors = 0

    class FakeLoader:
        def __init__(self, client, config):
            self.client = client
            self.config = config
            self.last_key_property = None

        def create_company_cet_relationships(
            self, rows_in, *, rel_type="SPECIALIZES_IN", key_property="uei"
        ):
            self.last_key_property = key_property
            # Return 1 relationship for the single row
            return FakeMetrics(1, rel_type)

    monkeypatch.setattr(mod, "_get_neo4j_client", lambda: object())
    monkeypatch.setattr(mod, "_read_parquet_or_ndjson", lambda *args, **kwargs: rows)
    monkeypatch.setattr(mod, "CETLoader", FakeLoader)
    monkeypatch.setattr(mod, "CETLoaderConfig", lambda batch_size: {"batch_size": batch_size})

    # Force initial key_property to 'uei' to test fallback behavior
    # Access the underlying op from the AssetsDefinition
    asset_def = mod.loaded_company_cet_relationships
    op_def = asset_def.op
    compute_fn = op_def.compute_fn

    ctx = mod.AssetExecutionContext(op_config={"key_property": "uei"})
    result = compute_fn(ctx, None, None, None)

    assert result["status"] == "success"
    # Asset should report fallback key in result
    assert result["key_property"] == "company_id"
    assert result["metrics"]["relationships_created"]["SPECIALIZES_IN"] == 1
