"""Safety gates for SBIR award graph loading."""

import pytest

from sbir_analytics.assets.sbir_neo4j_loading import (
    _ensure_unique_award_transaction_ids,
    _updated_since,
)


class _Metrics:
    def __init__(self, nodes_updated: dict[str, int]):
        self.nodes_updated = nodes_updated


def test_updated_since_reports_canonical_label_delta():
    metrics = _Metrics({"FinancialTransaction": 7, "Organization": 11, "Individual": 3})

    assert _updated_since(metrics, "FinancialTransaction") == (7, 7)
    assert _updated_since(metrics, "Organization", previous=5) == (6, 11)
    assert _updated_since(metrics, "Individual") == (3, 3)
    assert _updated_since(metrics, "Award") == (0, 0)


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
