"""Safety gates for SBIR award graph loading."""

import pytest

from sbir_analytics.assets.sbir_neo4j_loading import _ensure_unique_award_transaction_ids


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
