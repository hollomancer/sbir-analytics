import pandas as pd

from sbir_analytics.assets.phase_iii_candidates.pairing import pair_filter_s2, pair_filter_s3


def _priors() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "award_id": "A-1",
                "recipient_uei": "UEI000000001",
                "agency": "DEFENSE",
                "sub_agency": "NAVY",
                "office": "NAVAIR",
                "naics_code": "541715",
                "psc_code": "AJ11",
                "title": "Autonomous navigation",
                "abstract": "Autonomous aircraft navigation prototype transition",
                "period_of_performance_end": "2026-05-01",
            }
        ]
    )


def test_directed_exact_uei_pair():
    opportunities = pd.DataFrame(
        [
            {
                "notice_id": "O-1",
                "notice_type_code": "u",
                "awardee_uei": "UEI000000001",
                "agency": "DEFENSE",
                "sub_tier": "NAVY",
                "office": "NAVAIR",
                "naics_code": "541715",
                "description": "Phase III continuation of autonomous navigation",
                "posted_date": "2026-07-01",
                "response_deadline": "2099-08-01",
                "active": True,
            }
        ]
    )
    pairs = pair_filter_s2(_priors(), opportunities)
    assert list(pairs["target_id"]) == ["O-1"]
    assert pairs.iloc[0]["agency_match_level"] == "office"


def test_followon_filters_expired_and_irrelevant():
    opportunities = pd.DataFrame(
        [
            {
                "notice_id": "O-live",
                "notice_type_code": "o",
                "agency": "DEFENSE",
                "sub_tier": "NAVY",
                "office": "NAVAIR",
                "naics_code": "541715",
                "psc_code": "AJ11",
                "description": "Autonomous aircraft navigation prototype",
                "response_deadline": "2099-08-01",
                "active": True,
            },
            {
                "notice_id": "O-expired",
                "notice_type_code": "o",
                "agency": "DEFENSE",
                "naics_code": "541715",
                "description": "Autonomous navigation",
                "response_deadline": "2020-01-01",
                "active": True,
            },
        ]
    )
    pairs = pair_filter_s3(_priors(), opportunities)
    assert list(pairs["target_id"]) == ["O-live"]


def test_temporal_gate_drops_notice_posted_before_award_began():
    priors = _priors().assign(award_date="2026-01-15")
    opportunity = {
        "notice_id": "O-early",
        "notice_type_code": "u",
        "awardee_uei": "UEI000000001",
        "agency": "DEFENSE",
        "sub_tier": "NAVY",
        "office": "NAVAIR",
        "naics_code": "541715",
        "description": "Phase III continuation of autonomous navigation",
        "posted_date": "2025-12-01",  # predates the award — cannot be its follow-on
        "response_deadline": "2099-08-01",
        "active": True,
    }
    assert pair_filter_s2(priors, pd.DataFrame([opportunity])).empty

    # Same notice posted after the award start survives.
    late = {**opportunity, "notice_id": "O-late", "posted_date": "2026-07-01"}
    pairs = pair_filter_s2(priors, pd.DataFrame([late]))
    assert list(pairs["target_id"]) == ["O-late"]


def test_temporal_gate_is_neutral_on_missing_dates():
    # No award_date on the prior — the gate must not exclude anything.
    opportunity = {
        "notice_id": "O-nodate",
        "notice_type_code": "u",
        "awardee_uei": "UEI000000001",
        "agency": "DEFENSE",
        "sub_tier": "NAVY",
        "office": "NAVAIR",
        "naics_code": "541715",
        "description": "Phase III continuation of autonomous navigation",
        "posted_date": "2020-01-01",
        "response_deadline": "2099-08-01",
        "active": True,
    }
    pairs = pair_filter_s2(_priors(), pd.DataFrame([opportunity]))
    assert list(pairs["target_id"]) == ["O-nodate"]
