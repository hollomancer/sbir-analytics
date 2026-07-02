"""PR-time precision canary for the Phase III retrospective backtest.

The full ≥0.85 HIGH-precision benchmark runs against the S3 corpus in the
``transition-mvp`` CI job (workflow_dispatch only). These tests keep the
benchmark exercised on every PR with a small deterministic fixture: obvious
true-positive pairs must clear the threshold, obvious non-transitions must
not, and the data-missing sentinel must fail loudly in ``--strict`` mode.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from phase_iii_precision_backtest import (  # noqa: E402
    DEFAULT_PRECISION_THRESHOLD,
    main,
    run_backtest,
)


def _phase_ii_row(i: int, uei: str) -> dict:
    return {
        "award_id": f"PHII-{i:03d}",
        "recipient_uei": uei,
        "agency": "DEPT OF DEFENSE",
        "sub_agency": "DEPT OF THE NAVY",
        "office": "NAVAL AIR SYSTEMS COMMAND",
        "naics_code": "541715",
        "psc_code": "AC13",
        "title": "Advanced autonomous underwater vehicle navigation system",
        "abstract": (
            "Development of an advanced autonomous underwater vehicle navigation "
            "system using inertial sensors and machine learning for GPS-denied "
            "environments under SBIR Phase II."
        ),
        "period_of_performance_end": "2021-06-30",
        "cet": "autonomy",
    }


def _strong_contract_row(i: int, uei: str) -> dict:
    """A DoD-coded Phase III contract that is an unambiguous transition.

    Same agency/sub-tier/office as the prior, action date inside the full-credit
    timing window, sole-source, matching CET, topically similar description with
    three distinct lineage phrases ("Phase III", "derives from", "continuation of").
    """
    return {
        "contract_id": f"CTR-{i:03d}",
        "vendor_uei": uei,
        "awarding_agency_name": "DEPT OF DEFENSE",
        "awarding_sub_tier_agency_name": "DEPT OF THE NAVY",
        "awarding_office_name": "NAVAL AIR SYSTEMS COMMAND",
        "naics_code": "541715",
        "psc_code": "AC13",
        "transaction_description": (
            "SBIR Phase III follow-on production of the advanced autonomous "
            "underwater vehicle navigation system using inertial sensors and "
            "machine learning for GPS-denied environments. This effort derives "
            "from and is a continuation of the vendor's SBIR Phase II award."
        ),
        "action_date": "2022-03-15",
        "extent_competed": "SOLE SOURCE (FAR 6.302)",
        "type_of_set_aside": "SBIR PHASE III",
        "federal_action_obligation": 2_500_000.0,
        "research": "SR3",
        "cet": "autonomy",
    }


def _weak_contract_row(i: int, uei: str) -> dict:
    """A DoD-coded Phase III contract with almost no transition evidence.

    Different agency, action date far outside the timing window, full-and-open
    competition, no CET, and an unrelated description with no lineage language.
    """
    return {
        "contract_id": f"WEAK-{i:03d}",
        "vendor_uei": uei,
        "awarding_agency_name": "GENERAL SERVICES ADMINISTRATION",
        "awarding_sub_tier_agency_name": "FEDERAL ACQUISITION SERVICE",
        "awarding_office_name": "GSA REGION 4",
        "naics_code": "561210",
        "psc_code": "S208",
        "transaction_description": "Janitorial and custodial services for federal buildings.",
        "action_date": "2031-01-15",
        "extent_competed": "FULL AND OPEN COMPETITION",
        "type_of_set_aside": "NONE",
        "federal_action_obligation": 80_000.0,
        "research": "SR3",
        "cet": None,
    }


@pytest.fixture
def golden_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    ueis = [f"UEI{i:017d}" for i in range(10)]
    phase_ii = pd.DataFrame([_phase_ii_row(i, u) for i, u in enumerate(ueis)])
    contracts = pd.DataFrame([_strong_contract_row(i, u) for i, u in enumerate(ueis)])
    return contracts, phase_ii


def test_golden_positives_meet_precision_benchmark(golden_frames):
    """CLAUDE.md's ≥85% precision benchmark, exercised on every PR.

    If a scoring/weight change drops unambiguous transitions below the HIGH
    threshold, the production backtest would fail the same way — fix the
    regression or consciously retune the weights and this fixture together.
    """
    contracts, phase_ii = golden_frames
    report = run_backtest(
        contracts=contracts, phase_ii=phase_ii, threshold=DEFAULT_PRECISION_THRESHOLD
    )
    assert not report.get("data_missing")
    assert report["sample_size"] == 10
    assert report["precision"] >= DEFAULT_PRECISION_THRESHOLD


def test_weak_pairs_stay_below_threshold(golden_frames):
    """Guards the other direction: the threshold must still reject non-transitions."""
    _, phase_ii = golden_frames
    ueis = [f"UEI{i:017d}" for i in range(10)]
    weak = pd.DataFrame([_weak_contract_row(i, u) for i, u in enumerate(ueis)])
    report = run_backtest(contracts=weak, phase_ii=phase_ii, threshold=DEFAULT_PRECISION_THRESHOLD)
    assert report["sample_size"] == 10
    assert report["high_confidence_count"] == 0


def test_strict_mode_fails_when_data_missing(tmp_path, monkeypatch):
    """``--strict`` must exit non-zero on missing inputs — no vacuous CI pass."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "phase_iii_precision_backtest.py",
            "--strict",
            "--contracts",
            str(tmp_path / "missing_contracts.parquet"),
            "--phase-ii",
            str(tmp_path / "missing_phase_ii.parquet"),
            "--report",
            str(tmp_path / "backtest.json"),
        ],
    )
    assert main() == 2


def test_default_mode_writes_sentinel_and_exits_zero(tmp_path, monkeypatch):
    """Without ``--strict``, missing data is a warning sentinel (local/dev use)."""
    report_path = tmp_path / "backtest.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "phase_iii_precision_backtest.py",
            "--contracts",
            str(tmp_path / "missing_contracts.parquet"),
            "--phase-ii",
            str(tmp_path / "missing_phase_ii.parquet"),
            "--report",
            str(report_path),
        ],
    )
    assert main() == 0
    assert report_path.exists()
