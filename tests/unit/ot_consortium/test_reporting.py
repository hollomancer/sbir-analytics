import pandas as pd

from sbir_analytics.assets.ot_consortium.reporting import (
    aggregate_assignment_frame,
    non_attributable_external_totals,
)


def test_non_attributable_external_rows_are_preserved_in_report_bucket():
    frame = pd.DataFrame(
        [
            {"tier": "T1", "recipient_uei": "ABC", "transition_amount_usd": 100.0},
            {"tier": "T2", "recipient_uei": "DEF", "transition_amount_usd": 25.0},
            {"tier": "T4", "recipient_uei": "GHI", "transition_amount_usd": 5.0},
            {
                "source": "external_consortium",
                "aggregate_only": True,
                "transition_count": 3,
                "transition_amount_usd": 250.0,
            },
        ]
    )

    report = aggregate_assignment_frame(frame)
    buckets = report.set_index("assignment_bucket")

    assert buckets.loc["t1_verified_firm_attributed", "transition_count"] == 1
    assert buckets.loc["t1_verified_firm_attributed", "transition_usd"] == 100.0
    assert buckets.loc["t2_t4_unresolved_unverifiable", "transition_count"] == 2
    assert buckets.loc["t2_t4_unresolved_unverifiable", "transition_usd"] == 30.0
    assert buckets.loc["non_attributable_external", "transition_count"] == 3
    assert buckets.loc["non_attributable_external", "transition_usd"] == 250.0


def test_external_rows_without_firm_identifier_are_non_attributable():
    frame = pd.DataFrame(
        [
            {"source": "external", "recipient_uei": "", "amount_usd": 12.5},
            {"source": "external", "recipient_uei": "UEI", "amount_usd": 99.0},
        ]
    )

    assert non_attributable_external_totals(frame) == {
        "non_attributable_external_count": 1,
        "non_attributable_external_usd": 12.5,
    }
