from pathlib import Path

import pandas as pd

from sbir_analytics.assets.follow_on_multiplier.analysis import calculate_follow_on_multipliers
from sbir_analytics.assets.follow_on_multiplier.integration import build_canonical_obligations
from sbir_analytics.assets.follow_on_multiplier.reconcile import (
    reconcile_nasem,
    reconciliation_markdown,
)

FIXTURES = Path("tests/fixtures/follow_on_multiplier")


def test_production_shaped_inputs_to_reconciliation_report():
    canonical = build_canonical_obligations(
        pd.read_csv(FIXTURES / "sbir_awards.csv"),
        pd.read_csv(FIXTURES / "entity_matches.csv"),
        pd.read_csv(FIXTURES / "usaspending_transactions.csv"),
    )
    assert {"federal_action_obligation", "action_date_fiscal_year"}.issubset(
        pd.read_csv(FIXTURES / "usaspending_transactions.csv").columns
    )
    result = calculate_follow_on_multipliers(canonical)
    report = reconcile_nasem(result.agency, methodology="deterministic fixture")
    assert (
        report["observed"] == result.agency.query("agency == 'DOD'").iloc[0]["follow_on_multiplier"]
    )
    assert report["implementation_error"] is False
    assert "methodological" in reconciliation_markdown(report).lower()
