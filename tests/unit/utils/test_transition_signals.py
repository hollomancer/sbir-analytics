"""Unit tests for transition signal enrichment helpers."""

from sbir_etl.utils.transition_signals import (
    classify_deficiency,
    enrich_cohort_with_signals,
)


def test_classify_entity_resolution():
    assert classify_deficiency({"uei": "", "award_year": 2015}) == "ENTITY_RESOLUTION_FAILURE"


def test_classify_insufficient_time():
    row = {"uei": "ABC", "award_year": 2099, "digest_found": True}
    assert classify_deficiency(row) == "INSUFFICIENT_TIME"


def test_enrich_deficiency_class_ignores_other_positive_signals():
    # A data-quality problem (not in the FPDS/obligation digest) holds even
    # when some other channel (Form D here) shows a positive signal — the two
    # questions are independent. This must reproduce build_nano_cohort.py's
    # original classification exactly (verified against real nanotech data):
    # a prior version of this function short-circuited to a single
    # "SUPPLEMENTED_BY_OTHER_CHANNEL" bucket whenever any positive signal
    # existed, which does not match.
    cohort = [
        {
            "uei": "U1",
            "company": "Acme",
            "agency": "Department of Defense",
            "award_year": 2015,
        }
    ]
    digest = {}  # not in digest → FIRM_ACTIVITY_ABSENT
    fd = {"ACME": {"form_d_total_raised": 1.0, "form_d_filing_count": 1, "form_d_latest_date": ""}}
    out = enrich_cohort_with_signals(cohort, digest, {}, fd)
    assert out[0]["sig_form_d_detected"] is True
    assert out[0]["deficiency_class"] == "FIRM_ACTIVITY_ABSENT"


def test_enrich_ma_requires_signal_count():
    cohort = [
        {"uei": "U1", "company": "Acme", "agency": "Department of Defense", "award_year": 2015}
    ]
    ma = {"ACME": {"ma_signal_count": 0, "ma_confidence": "low"}}
    out = enrich_cohort_with_signals(
        cohort,
        {
            "U1": {
                "has_fy_phase3": False,
                "phase3_awards_n": 0,
                "phase3_total_usd": 0.0,
                "fy_contracts_in_fpds": 0,
                "fy_grants_in_fabs": 0,
            }
        },
        ma,
        {},
    )
    assert out[0]["sig_ma_detected"] is False
