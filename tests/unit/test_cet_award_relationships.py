import json
from typing import Any
from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.fast


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
def test_create_award_cet_relationships_builds_primary_and_supporting(neo4j_available):
    from src.loaders.neo4j import CETLoader, LoadMetrics

    # Arrange: mock client with capture of relationships
    captured: dict[str, Any] = {}

    def _fake_batch_create_relationships(*, relationships, metrics):
        captured["relationships"] = relationships
        m = LoadMetrics()
        m.relationships_created = {"APPLICABLE_TO": len(relationships)}
        return m

    mock_client = MagicMock()
    mock_client.batch_create_relationships.side_effect = _fake_batch_create_relationships

    loader = CETLoader(mock_client)

    row = {
        "award_id": "AWD-001",
        "primary_cet": "artificial_intelligence",
        "primary_score": 85.5,
        "supporting_cets": [
            {"cet_id": "machine_learning", "score": 64.2},
            {"cet_id": None, "score": 10.0},  # should be ignored
        ],
        "classified_at": "2025-01-02T03:04:05Z",
        "taxonomy_version": "TEST-2025Q1",
        "evidence": [{"rationale": "KEYWORD_MATCH", "excerpt": "text", "source": "title"}],
    }

    # Act
    metrics = loader.create_award_cet_relationships([row])

    # Assert: batch called once with expected tuples
    assert mock_client.batch_create_relationships.call_count == 1
    relationships = captured.get("relationships") or []
    # Expect 1 primary + 1 supporting (second supporting missing cet_id is ignored)
    assert len(relationships) == 2

    # Validate tuple structure and properties
    # (source_label, source_key, source_value, target_label, target_key, target_value, rel_type, props)
    primary = next(
        r for r in relationships if r[5] == "artificial_intelligence"
    )  # target_value is index 5
    assert primary[0:7] == (
        "Award",
        "award_id",
        "AWD-001",
        "CETArea",
        "cet_id",
        "artificial_intelligence",
        "APPLICABLE_TO",
    )
    pprops = primary[7]
    assert pprops["primary"] is True
    assert pprops["role"] == "PRIMARY"
    assert pytest.approx(pprops["score"], rel=1e-6) == 85.5
    assert pprops["rationale"] == "KEYWORD_MATCH"
    assert pprops["classified_at"] == "2025-01-02T03:04:05Z"
    assert pprops["taxonomy_version"] == "TEST-2025Q1"

    supporting = next(r for r in relationships if r[5] == "machine_learning")
    sprops = supporting[7]
    assert sprops["primary"] is False
    assert sprops["role"] == "SUPPORTING"
    assert pytest.approx(sprops["score"], rel=1e-6) == 64.2
    assert sprops["rationale"] == "KEYWORD_MATCH"

    # Metrics from fake batch reflect number of created relationships
    assert metrics.relationships_created.get("APPLICABLE_TO", 0) == 2


def test_create_award_cet_relationships_missing_award_id_skips_and_errors(neo4j_available):
    from src.loaders.neo4j import CETLoader

    mock_client = MagicMock()
    loader = CETLoader(mock_client)

    bad_row = {
        # "award_id" missing
        "primary_cet": "artificial_intelligence",
        "primary_score": 80.0,
    }

    metrics = loader.create_award_cet_relationships([bad_row])

    # Should not attempt to create relationships when award_id missing
    mock_client.batch_create_relationships.assert_not_called()
    assert metrics.errors == 1


# -----------------------------
# Asset tests (no neo4j needed)
# -----------------------------
def test_asset_neo4j_award_cet_relationships_invokes_loader(monkeypatch, tmp_path):
    """
    Validate that the Dagster asset:
    - Reads classification rows via helper
    - Invokes CETLoader.load_award_cet_relationships with those rows
    - Returns a serialized metrics dict
    """
    monkeypatch.chdir(tmp_path)

    # Prepare fake input rows
    rows = [
        {
            "award_id": "A1",
            "primary_cet": "artificial_intelligence",
            "primary_score": 90.0,
            "supporting_cets": [{"cet_id": "machine_learning", "score": 55.0}],
            "classified_at": "2025-01-01T00:00:00Z",
            "taxonomy_version": "TEST-2025Q1",
            "evidence": [{"rationale": "KEYWORD_MATCH"}],
        }
    ]

    # Count relationships produced by rows: 1 primary + 1 supporting = 2
    expected_rels = 2

    # Fake Loader and Config
    class FakeMetrics:
        def __init__(self, count: int):
            self.nodes_created = {}
            self.nodes_updated = {}
            self.relationships_created = {"APPLICABLE_TO": count}
            self.errors = 0

    class FakeLoader:
        def __init__(self, client, config):
            self.client = client
            self.config = config
            self.rows_received = None

        def load_award_cet_relationships(self, rows_in):
            """Match the actual method name in CETLoader."""
            self.rows_received = list(rows_in)
            # emulate counting relationships from rows
            count = 0
            for r in self.rows_received:
                if r.get("primary_cet"):
                    count += 1
                supp = r.get("supporting_cets") or []
                for s in supp:
                    if (s or {}).get("cet_id"):
                        count += 1
            return FakeMetrics(count)

        def close(self):
            pass

    # Patch asset internals in the loading module where they're used
    monkeypatch.setattr("src.assets.cet.loading._get_neo4j_client", lambda: FakeLoader(None, None))
    monkeypatch.setattr(
        "src.assets.cet.loading._read_parquet_or_ndjson", lambda *args, **kwargs: rows
    )
    monkeypatch.setattr("src.assets.cet.loading.CETLoader", FakeLoader)
    monkeypatch.setattr(
        "src.assets.cet.loading.CETLoaderConfig", lambda batch_size: {"batch_size": batch_size}
    )

    # Execute asset using Dagster's materialization with mocked dependencies
    from dagster import build_op_context

    # Build context with config
    ctx = build_op_context(
        config={
            "award_class_parquet": "fake.parquet",
            "award_class_json": "fake.json",
            "batch_size": 100,
        }
    )

    # Import the asset
    from src.assets.cet.loading import loaded_award_cet_relationships as asset_fn

    # Call with proper context and dummy asset dependencies
    result = asset_fn(ctx, None, None, None)

    assert result["status"] == "success"
    assert result["awards"] == len(rows)
    assert result["metrics"]["relationships_created"]["APPLICABLE_TO"] == expected_rels

    # The asset attempts to write a checks JSON; it tolerates missing dirs.
    # If created, validate structure; otherwise, just ensure no exception occurred.
    checks_path = (
        tmp_path / "data" / "loaded" / "neo4j" / "neo4j_award_cet_relationships.checks.json"
    )
    if checks_path.exists():
        with checks_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        assert payload.get("status") == "success"
        assert payload.get("awards") == len(rows)
