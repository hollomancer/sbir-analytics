"""Safety gates for SBIR award graph loading."""

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest
from dagster import build_asset_context

from sbir_analytics.assets import sbir_neo4j_loading as loading
from sbir_analytics.assets.sbir_neo4j_loading import (
    _created_since,
    _ensure_unique_award_transaction_ids,
    _updated_since,
)
from sbir_etl.models.award import Award


class _Metrics:
    def __init__(
        self,
        nodes_updated: dict[str, int],
        nodes_created: dict[str, int] | None = None,
    ):
        self.nodes_updated = nodes_updated
        self.nodes_created = nodes_created or {}


def test_updated_since_reports_canonical_label_delta():
    metrics = _Metrics({"FinancialTransaction": 7, "Organization": 11, "Individual": 3})

    assert _updated_since(metrics, "FinancialTransaction") == (7, 7)
    assert _updated_since(metrics, "Organization", previous=5) == (6, 11)
    assert _updated_since(metrics, "Individual") == (3, 3)
    assert _updated_since(metrics, "Award") == (0, 0)


def test_counter_deltas_never_go_negative_after_metrics_rebind():
    metrics = _Metrics({"Organization": 0}, {"Organization": 0})

    assert _updated_since(metrics, "Organization", previous=40) == (0, 0)
    assert _created_since(metrics, "Organization", previous=12) == (0, 0)


def test_unique_award_transaction_ids_pass():
    _ensure_unique_award_transaction_ids(
        [
            {"transaction_id": "txn_award_A"},
            {"transaction_id": "txn_award_B"},
        ]
    )


def test_duplicate_award_transaction_ids_fail_before_load():
    nodes = [
        {"transaction_id": "txn_award_SHARED", "phase": "I"},
        {"transaction_id": "txn_award_SHARED", "phase": "II"},
    ]

    with pytest.raises(ValueError, match=r"2 rows map to 1 transaction IDs \(1 collisions\)"):
        _ensure_unique_award_transaction_ids(nodes)


def test_asset_reports_canonical_stage_deltas(monkeypatch, tmp_path):
    award = Award(
        award_id="A-1",
        company_name="Example Corp",
        company_uei="ABCDEF123456",
        award_amount=100_000,
        award_date=date(2020, 1, 1),
        program="SBIR",
        phase="I",
        agency="DOD",
        principal_investigator="Jane Researcher",
        pi_email="jane@example.com",
        research_institution="Example University",
    )

    class FakeMetrics:
        def __init__(self):
            self.nodes_created = {}
            self.nodes_updated = {}
            self.relationships_created = {}
            self.errors = 0

    class FakeClient:
        def __init__(self):
            self.closed = False

        def create_constraints(self):
            return None

        def create_indexes(self):
            return None

        def batch_upsert_organizations_with_multi_key(self, *, metrics, **kwargs):
            metrics.nodes_updated["Organization"] = 1
            return metrics

        def batch_upsert_nodes(self, *, label, metrics, **kwargs):
            metrics.nodes_updated[label] = metrics.nodes_updated.get(label, 0) + 1
            return metrics

        def batch_create_relationships(self, relationships, *, metrics):
            for relationship in relationships:
                rel_type = relationship[6]
                metrics.relationships_created[rel_type] = (
                    metrics.relationships_created.get(rel_type, 0) + 1
                )
            return metrics

        def close(self):
            self.closed = True

    client = FakeClient()
    config = SimpleNamespace(
        transformation=SimpleNamespace(
            company_deduplication={
                "merge_on_uei": True,
                "merge_on_duns": True,
                "track_merge_history": True,
            }
        )
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(loading, "_get_neo4j_client", lambda: client)
    monkeypatch.setattr(loading, "LoadMetrics", FakeMetrics)
    monkeypatch.setattr(loading, "get_config", lambda: config)
    monkeypatch.setattr(loading, "build_canonical_company_map", lambda *args, **kwargs: {})
    monkeypatch.setattr(loading, "_try_create_award", lambda row: (award, "ok"))

    output = loading.neo4j_sbir_awards(
        build_asset_context(), pd.DataFrame([{"Company": "Example Corp"}])
    )
    result = output.value

    assert result["awards_submitted"] == 1
    assert result["awards_loaded"] == 1
    assert result["awards_updated"] == 1
    assert result["companies_loaded"] == 1
    assert result["companies_updated"] == 1
    assert result["researchers_loaded"] == 1
    assert result["researchers_updated"] == 1
    assert result["institutions_loaded"] == 1
    assert result["institutions_updated"] == 1
    assert result["metrics"]["nodes_updated"] == {
        "Organization": 3,
        "FinancialTransaction": 1,
        "Individual": 1,
    }
    assert client.closed is True


def test_load_check_accepts_idempotent_no_change_run():
    check = loading.neo4j_sbir_awards_load_check(
        {
            "status": "success",
            "errors": 0,
            "awards_submitted": 3,
            "awards_loaded": 0,
            "total_rows_processed": 3,
        }
    )

    assert check.passed is True
    assert "0/3 awards written" in check.description
