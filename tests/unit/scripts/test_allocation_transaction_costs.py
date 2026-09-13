from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from sbir_etl.exceptions import ConfigurationError
from scripts.data.allocation_transaction_costs import (
    MechanismYear,
    applicant_hours_from_source,
    breakeven_reviewer_hours,
    breakeven_sbir_hours,
    load_assumptions,
    load_mechanism_years,
    run,
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
    rows = [
        _row(mechanism="nih_sbir_phase_i", program="SBIR", applications=100, awards=10),
        _row(
            mechanism="nih_sttr_phase_i",
            program="STTR",
            applications=50,
            awards=8,
            dollars_awarded=1_600_000,
            mean_award_size=200_000,
        ),
        _row(
            mechanism="nih_sbir_phase_ii",
            program="SBIR",
            phase="II",
            applications=20,
            awards=8,
            dollars_awarded=8_000_000,
            mean_award_size=1_000_000,
        ),
    ]
    keys = {(row.program, row.phase, row.mechanism) for row in rows}
    assert ("SBIR", "I", "nih_sbir_phase_i") in keys
    assert ("STTR", "I", "nih_sttr_phase_i") in keys
    assert len(keys) == 3
    combined_success = success_rate(150, 18)
    sbir_only = success_rate(100, 10)
    assert combined_success != pytest.approx(sbir_only)


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
