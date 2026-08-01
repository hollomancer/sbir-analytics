"""id_xref signal: scored for opportunity classes, zero-weighted for RETROSPECTIVE."""

from __future__ import annotations

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_candidates.assets import (
    HIGH_THRESHOLD_DIRECTED,
    WEIGHTS_DIRECTED,
    WEIGHTS_RETROSPECTIVE,
    score_candidate_pairs,
)
from sbir_etl.models.phase_iii_candidate import SignalClass


pytestmark = pytest.mark.fast


def _pair(description: str) -> dict:
    return {
        "prior_award_id": "N00014-20-C-0055",
        "prior_recipient_uei": "UEI000000001",
        "prior_agency": "DEFENSE",
        "prior_sub_agency": "NAVY",
        "prior_office": "NAVAIR",
        "prior_naics_code": "541715",
        "prior_psc_code": "AJ11",
        "prior_title": "Autonomous navigation",
        "prior_abstract": "Autonomous aircraft navigation prototype",
        "prior_period_of_performance_end": "2026-05-01",
        "prior_cet": None,
        "target_id": "O-1",
        "target_recipient_uei": "UEI000000001",
        "target_agency": "DEFENSE",
        "target_sub_agency": "NAVY",
        "target_office": "NAVAIR",
        "target_naics_code": "541715",
        "target_psc_code": "AJ11",
        "target_description": description,
        "target_action_date": "2026-07-01",
        "target_competition_type": "u",
        "target_obligated_amount": None,
        "agency_match_level": "office",
    }


def test_id_xref_credits_a_notice_citing_the_award_number():
    pairs = pd.DataFrame(
        [
            _pair("Sole source continuation of work under contract N00014-20-C-0055."),
            _pair("Sole source continuation of unrelated navigation work."),
        ]
    )
    frame, _evidence = score_candidate_pairs(
        pairs,
        signal_class=SignalClass.DIRECTED,
        weights=WEIGHTS_DIRECTED,
        high_threshold=HIGH_THRESHOLD_DIRECTED,
    )

    citing, plain = frame.iloc[0], frame.iloc[1]
    assert citing["id_xref_score"] == pytest.approx(WEIGHTS_DIRECTED["id_xref"])
    assert plain["id_xref_score"] == 0.0
    assert citing["candidate_score"] > plain["candidate_score"]


def test_retrospective_weight_for_id_xref_is_zero():
    # Keeps the RETROSPECTIVE composite — and its precision gate — unchanged.
    assert WEIGHTS_RETROSPECTIVE["id_xref"] == 0.0
    assert sum(WEIGHTS_RETROSPECTIVE.values()) == pytest.approx(1.0)
