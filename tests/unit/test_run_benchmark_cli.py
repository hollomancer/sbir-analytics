"""CLI smoke tests for scripts/run_benchmark.py."""

from __future__ import annotations

import json
import sys

import pytest

from scripts import run_benchmark


def _write_demo_awards(path) -> None:
    path.write_text(
        "Company,UEI,phase,fiscal_year\nAcme Labs,ACME123,I,2021\nAcme Labs,ACME123,II,2022\n",
        encoding="utf-8",
    )


def _write_demo_commercialization(path) -> None:
    path.write_text(
        "company_id,total_sales_and_investment,patent_count\nuei:ACME123,250000,1\n",
        encoding="utf-8",
    )


def test_evaluate_report_uses_required_fy(tmp_path, monkeypatch, capsys):
    awards = tmp_path / "awards.csv"
    _write_demo_awards(awards)

    monkeypatch.setattr(
        sys,
        "argv",
        ["run_benchmark.py", "evaluate", str(awards), "--fy", "2025", "--report"],
    )

    run_benchmark.main()

    out = capsys.readouterr().out
    assert "# SBIR/STTR Benchmark Eligibility Report" in out
    assert "**Evaluation Fiscal Year:** 2025" in out
    assert "- Total companies evaluated: **1**" in out


def test_evaluate_requires_fy(tmp_path, monkeypatch):
    awards = tmp_path / "awards.csv"
    _write_demo_awards(awards)

    monkeypatch.setattr(sys, "argv", ["run_benchmark.py", "evaluate", str(awards)])

    with pytest.raises(SystemExit) as exc:
        run_benchmark.main()

    assert exc.value.code == 2


def test_report_marks_commercialization_not_evaluable_without_data(tmp_path, monkeypatch, capsys):
    """Without --commercialization, subject companies must not be reported as failing."""
    awards = tmp_path / "awards.csv"
    # 16 Phase II awards inside the FY2025 commercialization window (FY2013-2022)
    rows = "".join(f"Subject Co,SUBJ789,II,{2013 + (i % 10)}\n" for i in range(16))
    awards.write_text(f"Company,UEI,phase,fiscal_year\n{rows}", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        ["run_benchmark.py", "evaluate", str(awards), "--fy", "2025", "--report"],
    )

    run_benchmark.main()

    out = capsys.readouterr().out
    assert "- Failing commercialization benchmark: **0**" in out
    assert "no commercialization data was supplied" in out
    assert "Not Evaluable" in out
    assert "Subject Co" in out


def test_evaluate_rejects_awards_missing_phase_column(tmp_path, monkeypatch, capsys):
    """A file the evaluator can't resolve must fail loudly, not report 0 companies.

    Regression test: tests/fixtures/follow_on_multiplier/sbir_awards.csv has no Phase
    column, and the evaluator silently returned an empty summary for it.
    """
    awards = tmp_path / "awards.csv"
    awards.write_text(
        "company_id,recipient_uei,award_id,fiscal_year\nAlpha,UEI-ALPHA,S-A1,2020\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["run_benchmark.py", "evaluate", str(awards), "--fy", "2025", "--report"],
    )

    with pytest.raises(SystemExit) as exc:
        run_benchmark.main()

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "missing required columns" in err
    assert "Phase" in err


def test_sensitivity_accepts_commercialization_data(tmp_path, monkeypatch, capsys):
    awards = tmp_path / "awards.csv"
    commercialization = tmp_path / "commercialization.csv"
    _write_demo_awards(awards)
    _write_demo_commercialization(commercialization)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_benchmark.py",
            "sensitivity",
            str(awards),
            "--fy",
            "2025",
            "--commercialization",
            str(commercialization),
        ],
    )

    run_benchmark.main()

    assert json.loads(capsys.readouterr().out) == []


def test_subject_only_report_matches_filtered_json(tmp_path, monkeypatch, capsys):
    """--subject-only must recompute counters and apply across BOTH output modes.

    Regression test for Copilot review on PR #418: previously the flag mutated the
    JSON dict after the fact, leaving --report unchanged and counters inconsistent
    with the filtered lists.
    """
    awards = tmp_path / "awards.csv"
    rows = ["Company,UEI,phase,fiscal_year\n"]
    # Not subject and not at-risk: recent Phase I outside the completed window.
    rows.append("New Co,NEWCO456,I,2025\n")
    # Not subject but at-risk: 18 Phase I awards, within 5 of the standard threshold.
    rows.extend(f"Almost Co,ALMOST456,I,{2019 + (i % 5)}\n" for i in range(18))
    # Subject: 21 Phase I awards and enough Phase II awards to pass.
    rows.extend(f"Subject Co,SUBJ123,I,{2019 + (i % 5)}\n" for i in range(21))
    rows.extend(f"Subject Co,SUBJ123,II,{2020 + (i % 5)}\n" for i in range(6))
    awards.write_text("".join(rows), encoding="utf-8")

    # --subject-only + JSON output
    output_json = tmp_path / "results.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_benchmark.py",
            "evaluate",
            str(awards),
            "--fy",
            "2025",
            "--subject-only",
            "--output",
            str(output_json),
        ],
    )
    run_benchmark.main()
    payload = json.loads(output_json.read_text(encoding="utf-8"))

    # No not_subject rows survive the filter.
    for r in payload["transition_results"]:
        assert r["tier"] != "not_subject"
    for r in payload["commercialization_results"]:
        assert r["tier"] != "not_subject"

    # Counters must match the filtered lists.
    assert payload["companies_subject_to_transition"] == len(payload["transition_results"])
    assert payload["companies_subject_to_commercialization"] == len(
        payload["commercialization_results"]
    )
    subject_ids = {r["company_id"] for r in payload["transition_results"]} | {
        r["company_id"] for r in payload["commercialization_results"]
    }
    assert payload["total_companies_evaluated"] == len(subject_ids)
    assert "uei:ALMOST456" not in subject_ids
    assert all(r["company_id"] in subject_ids for r in payload["sensitivity_results"])

    # --subject-only + --report must produce a report whose counter matches the
    # filtered universe (not the unfiltered total_companies_evaluated), and
    # must not leak non-subject at-risk companies through the sensitivity section.
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_benchmark.py",
            "evaluate",
            str(awards),
            "--fy",
            "2025",
            "--subject-only",
            "--report",
        ],
    )
    run_benchmark.main()
    report = capsys.readouterr().out
    assert f"- Total companies evaluated: **{payload['total_companies_evaluated']}**" in report
    assert "Almost Co" not in report


def test_company_accepts_commercialization_data(tmp_path, monkeypatch, capsys):
    awards = tmp_path / "awards.csv"
    commercialization = tmp_path / "commercialization.csv"
    _write_demo_awards(awards)
    _write_demo_commercialization(commercialization)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_benchmark.py",
            "company",
            str(awards),
            "--fy",
            "2025",
            "--id",
            "uei:ACME123",
            "--commercialization",
            str(commercialization),
        ],
    )

    run_benchmark.main()

    result = json.loads(capsys.readouterr().out)
    assert result["transition_rate"]["company_id"] == "uei:ACME123"
    assert result["commercialization_rate"]["avg_sales_per_phase2"] == 250000.0
