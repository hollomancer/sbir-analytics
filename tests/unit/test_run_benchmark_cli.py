"""CLI smoke tests for scripts/run_benchmark.py."""

from __future__ import annotations

import json
import sys

import pytest

from scripts import run_benchmark


def _write_demo_awards(path) -> None:
    path.write_text(
        "Company,UEI,phase,fiscal_year\n"
        "Acme Labs,ACME123,I,2021\n"
        "Acme Labs,ACME123,II,2022\n",
        encoding="utf-8",
    )


def _write_demo_commercialization(path) -> None:
    path.write_text(
        "company_id,total_sales_and_investment,patent_count\n"
        "uei:ACME123,250000,1\n",
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
