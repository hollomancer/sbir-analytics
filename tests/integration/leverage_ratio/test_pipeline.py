from pathlib import Path

import pandas as pd

from sbir_analytics.assets.leverage_ratio.analysis import calculate_leverage_ratios
from sbir_analytics.assets.leverage_ratio.integration import build_canonical_obligations
from sbir_analytics.assets.leverage_ratio.reconcile import reconcile_nasem, reconciliation_markdown

FIXTURES = Path("tests/fixtures/leverage_ratio")


def test_production_shaped_inputs_to_reconciliation_report():
    canonical = build_canonical_obligations(
        pd.read_csv(FIXTURES / "sbir_awards.csv"),
        pd.read_csv(FIXTURES / "entity_matches.csv"),
        pd.read_csv(FIXTURES / "usaspending_transactions.csv"),
    )
    assert {"federal_action_obligation", "action_date_fiscal_year"}.issubset(
        pd.read_csv(FIXTURES / "usaspending_transactions.csv").columns
    )
    result = calculate_leverage_ratios(canonical)
    report = reconcile_nasem(result.agency, methodology="deterministic fixture")
    assert report["observed"] == result.agency.query("agency == 'DOD'").iloc[0]["leverage_ratio"]
    assert report["implementation_error"] is False
    assert "methodological" in reconciliation_markdown(report).lower()
