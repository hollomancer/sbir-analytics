"""PR-time polarity and wiring checks for the Phase III retrospective backtest.

These fixtures are not the repository's ≥85% HIGH-precision benchmark.
That number is measured only by a manual run of
``scripts/phase_iii_precision_backtest.py`` against the S3 corpus.

What this module does enforce on every PR:

* slam-dunk same-office Phase III pairs still score HIGH
* obvious non-transitions still score below the HIGH threshold
* ``--strict`` fails when inputs are missing
* mixed-signal pairs keep their current HIGH / not-HIGH polarity, so a
  weight swap or threshold inversion cannot land silently
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_candidates.assets import (
    WEIGHTS_RETROSPECTIVE,
    _score_pair,
    _scorer_config,
)
from sbir_ml.transition.detection.scoring import TransitionScorer


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


HIGH_THRESHOLD = DEFAULT_PRECISION_THRESHOLD


def _pair_row(**overrides: object) -> pd.Series:
    base = {
        "prior_award_id": "PHII-000",
        "prior_recipient_uei": "UEI000",
        "prior_agency": "DEPT OF DEFENSE",
        "prior_sub_agency": "DEPT OF THE NAVY",
        "prior_office": "NAVAL AIR SYSTEMS COMMAND",
        "prior_naics_code": "541715",
        "prior_psc_code": "AC13",
        "prior_title": "AUV navigation",
        "prior_abstract": "Phase II AUV navigation",
        "prior_period_of_performance_end": "2021-06-30",
        "prior_cet": "autonomy",
        "target_id": "CTR-000",
        "target_recipient_uei": "UEI000",
        "target_agency": "DEPT OF DEFENSE",
        "target_sub_agency": "DEPT OF THE NAVY",
        "target_office": "NAVAL AIR SYSTEMS COMMAND",
        "target_naics_code": "541715",
        "target_psc_code": "AC13",
        "target_description": "Vendor production contract for navigation hardware.",
        "target_action_date": "2022-03-15",
        "target_competition_type": "SOLE SOURCE (FAR 6.302)",
        "target_obligated_amount": 2_500_000.0,
        "target_cet": "autonomy",
        "agency_match_level": "office",
    }
    base.update(overrides)
    return pd.Series(base)


def _composite(row: pd.Series, *, text_similarity: float, weights: dict | None = None) -> float:
    scorer = TransitionScorer(_scorer_config(weights or WEIGHTS_RETROSPECTIVE))
    score, _subs, _topical = _score_pair(scorer, row, text_similarity=text_similarity)
    return float(score)


@pytest.fixture
def golden_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    ueis = [f"UEI{i:017d}" for i in range(10)]
    phase_ii = pd.DataFrame([_phase_ii_row(i, u) for i, u in enumerate(ueis)])
    contracts = pd.DataFrame([_strong_contract_row(i, u) for i, u in enumerate(ueis)])
    return contracts, phase_ii


def test_obvious_transitions_score_high(golden_frames):
    """Slam-dunk same-office Phase III pairs must still clear the HIGH threshold.

    This is a polarity smoke test, not the S3-corpus ≥85% precision benchmark.
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


def test_office_sole_cet_full_text_without_lineage_is_exactly_high():
    """0.25+0.15+0.20+0.15+0.10 = 0.85. Lineage off, still HIGH at the floor."""
    score = _composite(_pair_row(), text_similarity=1.0)
    assert score == pytest.approx(0.85, abs=0.02)
    assert score >= HIGH_THRESHOLD


def test_same_office_sole_source_without_cet_or_lineage_stays_below_high():
    """0.25+0.15+0.20 + 0.02 text = 0.62. Must not be HIGH."""
    # _score_pair routes text_similarity through topical similarity (NAICS+PSC+text).
    # Clear codes so taxonomy matches cannot inflate the text term; topical then
    # equals 0.5 * text_similarity, so 0.4 yields the 0.02 text contribution below.
    row = _pair_row(
        prior_cet=None,
        target_cet=None,
        prior_naics_code=None,
        prior_psc_code=None,
        target_naics_code=None,
        target_psc_code=None,
    )
    score = _composite(row, text_similarity=0.4)
    assert score == pytest.approx(0.62, abs=0.02)
    assert score < HIGH_THRESHOLD


def test_weight_swap_flips_the_borderline_high_pair():
    """Cartoon TPs stay HIGH under almost any weights. This pair must not."""
    swapped = dict(WEIGHTS_RETROSPECTIVE)
    swapped["agency_continuity"], swapped["patent_signal"] = (
        swapped["patent_signal"],
        swapped["agency_continuity"],
    )
    row = _pair_row()
    assert _composite(row, text_similarity=1.0) >= HIGH_THRESHOLD
    # agency now 0.05 * 1.0; patent still 0 (no patent input) → ~0.65
    assert _composite(row, text_similarity=1.0, weights=swapped) < HIGH_THRESHOLD
