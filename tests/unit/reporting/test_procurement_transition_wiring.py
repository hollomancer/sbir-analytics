"""Pin the production composition root for fusion ranking.

`fusion_scorer` is required explicitly because None degrades the report to deadline
order with only a WARNING — a complete, plausible-looking packet that was never ranked.
Exactly one production call site binds the real scorer, so these tests pin that binding.
"""

import ast
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REPORT_SCRIPT = REPOSITORY_ROOT / "scripts/data/monthly_procurement_transition_report.py"


pytestmark = pytest.mark.fast


def _builder_call(tree: ast.Module) -> ast.Call:
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "MonthlyReportBuilder"
    ]
    assert len(calls) == 1, f"expected one MonthlyReportBuilder call, found {len(calls)}"
    return calls[0]


def test_report_script_binds_a_fusion_scorer() -> None:
    tree = ast.parse(REPORT_SCRIPT.read_text(encoding="utf-8"), filename=str(REPORT_SCRIPT))
    keywords = {kw.arg: kw.value for kw in _builder_call(tree).keywords}

    assert "fusion_scorer" in keywords, (
        "monthly_procurement_transition_report.py must pass fusion_scorer explicitly; "
        "without it the packet renders in deadline order and is never fusion-ranked"
    )
    bound = keywords["fusion_scorer"]
    assert not (isinstance(bound, ast.Constant) and bound.value is None)
    assert isinstance(bound, ast.Name) and bound.id == "score_pairs_with_fusion"


def test_report_script_imports_the_scorer_it_binds() -> None:
    tree = ast.parse(REPORT_SCRIPT.read_text(encoding="utf-8"), filename=str(REPORT_SCRIPT))
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert "score_pairs_with_fusion" in imported
