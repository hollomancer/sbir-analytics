from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from sbir_etl.exceptions import ConfigurationError
from scripts.data.allocation_transaction_costs import (
    SHOCK_TARGETS,
    MechanismYear,
    _shock_factors,
    applicant_hours_from_source,
    breakeven_reviewer_hours,
    breakeven_sbir_hours,
    breakeven_sbir_hours_total,
    break_even_table,
    load_all_duration_rows,
    load_assumptions,
    load_mechanism_years,
    load_sources,
    metrics_table,
    ranking_flip_summary,
    run,
    sensitivity_grid,
    success_rate,
    transaction_cost,
)

REPO = Path(__file__).resolve().parents[3]
CALCULATOR = REPO / "scripts/data/allocation_transaction_costs.py"
STUDY = REPO / "studies/allocation-transaction-costs"
ALLOWED_LITERALS = {0, 1}


def _row(**overrides: object) -> MechanismYear:
    base = {
        "agency": "NIH",
        "mechanism": "nih_sbir_phase_i",
        "program": "SBIR",
        "phase": "I",
        "fiscal_year": 2020,
        "applications": 100,
        "awards": 10,
        "success_rate": 0.1,
        "dollars_awarded": 3_000_000,
        "mean_award_size": 300_000,
        "award_size_basis": "competing_year_total_funding",
        "source_id": "test",
        "evidence_class": "administrative_count",
        "duration_convention": "annual_award_size",
    }
    base.update(overrides)
    return MechanismYear(**base)  # type: ignore[arg-type]


def test_break_even_identity_matches_tc_per_dollar() -> None:
    h_r01 = 160.0
    s_sbir, d_sbir = 0.12, 300_000.0
    s_r01, d_r01 = 0.20, 600_000.0
    wage = 50.0
    h_star = breakeven_sbir_hours(h_r01, s_sbir, d_sbir, s_r01, d_r01)
    sbir = transaction_cost(
        applications=1000,
        awards=120,
        mean_award_size=d_sbir,
        hours_per_application=h_star,
        wage=wage,
        reviewers_per_application=0,
        reviewer_hours=0,
        reviewer_wage=wage,
        agency_cost=None,
        per_million_dollars=1_000_000,
    )
    r01 = transaction_cost(
        applications=1000,
        awards=200,
        mean_award_size=d_r01,
        hours_per_application=h_r01,
        wage=wage,
        reviewers_per_application=0,
        reviewer_hours=0,
        reviewer_wage=wage,
        agency_cost=None,
        per_million_dollars=1_000_000,
    )
    assert sbir.dollars_per_award_dollar == pytest.approx(r01.dollars_per_award_dollar)
    assert sbir.dollars_per_award != pytest.approx(r01.dollars_per_award)
    assert sbir.hours_per_award != pytest.approx(r01.hours_per_award)


def test_three_outcomes_remain_distinct() -> None:
    cost = transaction_cost(
        applications=80,
        awards=10,
        mean_award_size=250_000,
        hours_per_application=40,
        wage=50,
        reviewers_per_application=3,
        reviewer_hours=4,
        reviewer_wage=50,
        agency_cost=None,
        per_million_dollars=1_000_000,
    )
    values = {cost.hours_per_award, cost.dollars_per_award, cost.dollars_per_award_dollar}
    assert len(values) == 3
    assert cost.gc_included is False


def test_missing_gc_is_not_zero() -> None:
    with_gc = transaction_cost(
        applications=80,
        awards=10,
        mean_award_size=250_000,
        hours_per_application=40,
        wage=50,
        reviewers_per_application=3,
        reviewer_hours=4,
        reviewer_wage=50,
        agency_cost=0.0,
        per_million_dollars=1_000_000,
    )
    missing = transaction_cost(
        applications=80,
        awards=10,
        mean_award_size=250_000,
        hours_per_application=40,
        wage=50,
        reviewers_per_application=3,
        reviewer_hours=4,
        reviewer_wage=50,
        agency_cost=None,
        per_million_dollars=1_000_000,
    )
    assert missing.gc_included is False
    assert with_gc.gc_included is True
    assert missing.dollars_per_award == pytest.approx(with_gc.dollars_per_award)


def test_pra_and_fa_hours_are_refused() -> None:
    with pytest.raises(ConfigurationError, match="pra_estimate"):
        applicant_hours_from_source(12.0, "pra_estimate")
    with pytest.raises(ConfigurationError, match="fa_rate"):
        applicant_hours_from_source(0.56, "fa_rate")
    assert applicant_hours_from_source(40.0, "assumption_grid") == 40.0


def test_sbir_and_sttr_are_not_combined() -> None:
    sources = load_sources(STUDY / "sources.yaml")
    assumptions = load_assumptions(STUDY / "assumptions.yaml")
    rows = load_all_duration_rows(sources, assumptions, repository_root=REPO)
    keys = {(row.program, row.phase, row.mechanism) for row in rows}
    assert ("SBIR", "I", "nih_sbir_phase_i") in keys
    assert ("STTR", "I", "nih_sttr_phase_i") in keys
    assert ("SBIR", "II", "nih_sbir_phase_ii") in keys
    assert ("STTR", "II", "nih_sttr_phase_ii") in keys
    assert all(row.program in {"SBIR", "STTR", "R01-equivalent"} for row in rows)

    sbir_i = next(
        row
        for row in rows
        if row.mechanism == "nih_sbir_phase_i" and row.duration_convention == "annual_award_size"
    )
    sttr_i = next(
        row
        for row in rows
        if row.mechanism == "nih_sttr_phase_i"
        and row.fiscal_year == sbir_i.fiscal_year
        and row.duration_convention == "annual_award_size"
    )
    combined_success = success_rate(
        sbir_i.applications + sttr_i.applications, sbir_i.awards + sttr_i.awards
    )
    assert sbir_i.success_rate is not None
    assert combined_success != pytest.approx(sbir_i.success_rate)

    metric_keys = {
        (row["program"], row["phase"], row["mechanism"]) for row in metrics_table(rows, assumptions)
    }
    assert ("SBIR", "I", "nih_sbir_phase_i") in metric_keys
    assert ("STTR", "I", "nih_sttr_phase_i") in metric_keys
    assert ("SBIR", "II", "nih_sbir_phase_ii") in metric_keys
    assert ("STTR", "II", "nih_sttr_phase_ii") in metric_keys


def test_loader_refuses_sha_mismatch(tmp_path: Path) -> None:
    csv_path = tmp_path / "table.csv"
    csv_path.write_text(
        "agency,mechanism,program,phase,fiscal_year,applications,awards,"
        "success_rate,dollars_awarded,mean_award_size,award_size_basis,source_id\n"
        "NIH,nih_sbir_phase_i,SBIR,I,2020,100,10,0.1,3000000,300000,"
        "competing_year_total_funding,test\n",
        encoding="utf-8",
    )
    sources = {
        "tables": [
            {
                "path": csv_path.name,
                "sha256": "0" * 64,
                "evidence_class": "administrative_count",
            }
        ]
    }
    with pytest.raises(ConfigurationError, match="SHA-256 mismatch"):
        load_mechanism_years(
            sources,
            repository_root=tmp_path,
            duration_convention="annual_award_size",
            r01_project_years=4,
            control_mechanism="nih_r01_equivalent",
        )


def test_loader_accepts_matching_sha(tmp_path: Path) -> None:
    csv_path = tmp_path / "table.csv"
    csv_path.write_text(
        "agency,mechanism,program,phase,fiscal_year,applications,awards,"
        "success_rate,dollars_awarded,mean_award_size,award_size_basis,source_id\n"
        "NIH,nih_r01_equivalent,R01-equivalent,,2020,1000,200,0.2,120000000,600000,"
        "annual_average_size,test\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    sources = {
        "tables": [
            {
                "path": csv_path.name,
                "sha256": digest,
                "evidence_class": "administrative_count",
            }
        ]
    }
    rows = load_mechanism_years(
        sources,
        repository_root=tmp_path,
        duration_convention="project_total",
        r01_project_years=4,
        control_mechanism="nih_r01_equivalent",
    )
    assert len(rows) == 1
    assert rows[0].mean_award_size == pytest.approx(2_400_000)
    assert rows[0].duration_convention == "project_total"


def test_core_functions_have_no_unexplained_numeric_literals() -> None:
    tree = ast.parse(CALCULATOR.read_text(encoding="utf-8"))
    watched = {
        "breakeven_sbir_hours",
        "breakeven_sbir_hours_total",
        "breakeven_reviewer_hours",
        "success_rate",
        "award_dollars_per_application",
        "transaction_cost",
        "applicant_hours_from_source",
    }
    found: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in watched:
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, (int, float)):
                if child.value not in ALLOWED_LITERALS:
                    found.append(f"{node.name}:{child.value}")
    assert found == []


def test_committed_study_run(tmp_path: Path) -> None:
    summary = run(
        sources_path=STUDY / "sources.yaml",
        assumptions_path=STUDY / "assumptions.yaml",
        complexity_path=STUDY / "complexity/nih_foa_rules.yaml",
        out_dir=tmp_path,
        repository_root=REPO,
    )
    assert summary["breakeven_rows"] > 0
    breakeven = (tmp_path / "breakeven.csv").read_text(encoding="utf-8")
    assert "annual_award_size" in breakeven
    assert "project_total" in breakeven
    mechanism_year = (tmp_path / "mechanism_year.csv").read_text(encoding="utf-8")
    assert "nih_sbir_phase_i" in mechanism_year
    assert "nih_sttr_phase_i" in mechanism_year
    assert "nih_r01_equivalent" in mechanism_year
    assert "Total Phase II" not in mechanism_year
    assumptions = load_assumptions(STUDY / "assumptions.yaml")
    assert assumptions["agency_cost"]["mode"] == "missing"


def test_reviewer_break_even_scales_with_reviewer_count() -> None:
    one = breakeven_reviewer_hours(4, 3, 3, 0.1, 300_000, 0.2, 600_000)
    two = breakeven_reviewer_hours(4, 6, 3, 0.1, 300_000, 0.2, 600_000)
    assert two == pytest.approx(one / 2)


@pytest.fixture(scope="module")
def committed_sensitivity() -> list[dict[str, object]]:
    """The sensitivity grid over the committed tables, built once."""

    assumptions = load_assumptions(STUDY / "assumptions.yaml")
    sources = load_sources(STUDY / "sources.yaml")
    rows = load_all_duration_rows(sources, assumptions, repository_root=REPO)
    return sensitivity_grid(rows, assumptions)


def _cells(grid, target):
    """Group ratios by scenario cell, holding everything but the shock fixed."""

    cells: dict[tuple[object, ...], list[float]] = {}
    for row in grid:
        if row["shock_target"] != target:
            continue
        key = (
            row["fiscal_year"],
            row["duration_convention"],
            row["h_treatment"],
            row["h_control"],
            row["reviewer_hours"],
        )
        ratio = row["treatment_tc_per_dollar"] / row["control_tc_per_dollar"]
        cells.setdefault(key, []).append(ratio)
    return cells


def test_shock_factors_apply_to_the_named_side_only() -> None:
    assert _shock_factors("both", 0.25) == (1.25, 1.25)
    assert _shock_factors("treatment", 0.25) == (1.25, 1.0)
    assert _shock_factors("control", 0.25) == (1.0, 1.25)
    with pytest.raises(ConfigurationError):
        _shock_factors("applicant", 0.25)


def test_common_shocks_cannot_change_the_ranking(committed_sensitivity) -> None:
    """A shock applied to both sides divides out of cost per awarded dollar.

    This is a property of the cost function, not a finding. `both` rows are kept
    in the grid as this check; the one-sided targets are what test the relative
    assumption.
    """

    cells = _cells(committed_sensitivity, "both")
    assert cells
    for key, ratios in cells.items():
        spread = (max(ratios) - min(ratios)) / min(ratios)
        assert spread < 1e-12, f"{key} ratio moved by {spread:.3e} under a common shock"

    flags: dict[tuple[object, ...], set[bool]] = {}
    for row in committed_sensitivity:
        if row["shock_target"] != "both":
            continue
        key = (
            row["fiscal_year"],
            row["duration_convention"],
            row["h_treatment"],
            row["h_control"],
            row["reviewer_hours"],
        )
        flags.setdefault(key, set()).add(bool(row["treatment_cheaper_per_dollar"]))
    assert all(len(v) == 1 for v in flags.values())


def test_one_sided_shocks_do_move_the_ranking_ratio(committed_sensitivity) -> None:
    cells = _cells(committed_sensitivity, "treatment")
    assert cells
    moved = sum(1 for ratios in cells.values() if max(ratios) - min(ratios) > 0)
    assert moved == len(cells)


def test_sensitivity_grid_sweeps_the_declared_reviewer_hours(committed_sensitivity) -> None:
    """Reviewer hours are a swept scenario, not a pinned constant."""

    assumptions = load_assumptions(STUDY / "assumptions.yaml")
    declared = {float(h) for h in assumptions["review"]["reviewer_hours"]}
    assert {row["reviewer_hours"] for row in committed_sensitivity} == declared
    assert {row["shock_target"] for row in committed_sensitivity} == set(SHOCK_TARGETS)


def test_reviewer_hours_change_the_ranking_when_scale_differs() -> None:
    """Equal reviewer counts do not make reviewer cost cancel.

    Review cost enters cost per awarded dollar as R x rh x rw / (s x d). When the
    two mechanisms differ in s x d, raising reviewer hours raises the smaller-scale
    side faster, so the ranking flips on reviewer hours alone. Here both sides draw
    10 applications per award at a $50 wage with 3 reviewers, the treatment award is
    half the control award, and the treatment proposal is 33 hours against 80. The
    algebraic crossover is at 3 x rh x 50 = $700 of review cost, so rh = 2 lands
    below it and rh = 8 above.
    """

    def per_dollar(hours: float, mean_award_size: float, reviewer_hours: float) -> float:
        return transaction_cost(
            applications=1_000,
            awards=100,
            mean_award_size=mean_award_size,
            hours_per_application=hours,
            wage=50.0,
            reviewers_per_application=3,
            reviewer_hours=reviewer_hours,
            reviewer_wage=50.0,
            agency_cost=None,
            per_million_dollars=1_000_000,
        ).dollars_per_award_dollar

    assert per_dollar(33.0, 300_000, 2.0) < per_dollar(80.0, 600_000, 2.0)
    assert per_dollar(33.0, 300_000, 8.0) > per_dollar(80.0, 600_000, 8.0)


def test_ranking_flip_summary_separates_reviewer_hours_and_shock_target(
    committed_sensitivity,
) -> None:
    """Grouping must not average over the two dimensions that move the result."""

    summary = ranking_flip_summary(committed_sensitivity)
    assert summary
    assert {row["shock_target"] for row in summary} == set(SHOCK_TARGETS)
    assert len({row["reviewer_hours"] for row in summary}) > 1


def test_total_breakeven_is_below_applicant_only_and_may_go_negative() -> None:
    """The review term both sides carry lowers the threshold, sometimes past zero."""

    common = {
        "success_treatment": 0.0781,
        "dollars_treatment": 352_780.0,
        "success_control": 0.1302,
        "dollars_control": 2_656_020.0,
    }
    applicant_only = breakeven_sbir_hours(160.0, **common)
    total = breakeven_sbir_hours_total(
        160.0,
        **common,
        wage=53.99,
        reviewers_treatment=3,
        reviewers_control=3,
        reviewer_hours=8.0,
        reviewer_wage=53.99,
    )
    assert total < applicant_only
    assert total < 0, "this scenario has no feasible applicant-hour count"


def test_total_breakeven_equals_applicant_only_without_review_cost() -> None:
    """With no review hours the two thresholds must coincide."""

    common = {
        "success_treatment": 0.1,
        "dollars_treatment": 300_000.0,
        "success_control": 0.2,
        "dollars_control": 600_000.0,
    }
    assert breakeven_sbir_hours_total(
        160.0,
        **common,
        wage=50.0,
        reviewers_treatment=3,
        reviewers_control=3,
        reviewer_hours=0.0,
        reviewer_wage=50.0,
    ) == pytest.approx(breakeven_sbir_hours(160.0, **common))


def test_total_breakeven_rejects_a_non_positive_wage() -> None:
    with pytest.raises(ConfigurationError):
        breakeven_sbir_hours_total(
            160.0,
            success_treatment=0.1,
            dollars_treatment=300_000.0,
            success_control=0.2,
            dollars_control=600_000.0,
            wage=0.0,
            reviewers_treatment=3,
            reviewers_control=3,
            reviewer_hours=4.0,
            reviewer_wage=50.0,
        )


def test_break_even_table_reports_both_thresholds_and_flags_infeasible() -> None:
    """Negative thresholds are reported, not clipped."""

    assumptions = load_assumptions(STUDY / "assumptions.yaml")
    sources = load_sources(STUDY / "sources.yaml")
    rows = load_all_duration_rows(sources, assumptions, repository_root=REPO)
    table = break_even_table(rows, assumptions)
    assert table
    required = {
        "h_treatment_breakeven_applicant_only",
        "h_treatment_breakeven_total",
        "no_feasible_hour_count",
        "reviewer_hours",
    }
    assert required <= set(table[0])
    assert "h_treatment_breakeven" not in table[0]
    for row in table:
        assert row["h_treatment_breakeven_total"] <= row["h_treatment_breakeven_applicant_only"]
        assert row["no_feasible_hour_count"] == (row["h_treatment_breakeven_total"] < 0)
    assert any(row["no_feasible_hour_count"] for row in table)
    assert not all(row["no_feasible_hour_count"] for row in table)
