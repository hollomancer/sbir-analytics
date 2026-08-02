"""Tests for the SBIR Phase III self-label filter."""

from scripts.phase3_benchmark.extract_phase3_selflabeled import (
    classify_notice,
    is_self_labeled,
)


def test_matches_explicit_phase_iii():
    assert is_self_labeled("SBIR Phase III ELITE v3", "")
    assert is_self_labeled("", "Intent to Award Sole Source, SBIR Phase III Contract")
    assert is_self_labeled("Small Business Innovation Research (SBIR) Phase III award", "")


def test_matches_638_and_sole_source():
    assert is_self_labeled("", "awarded under 15 U.S.C. 638 authority")
    assert is_self_labeled("Notice of Sole Source Award - Air Force SBIR/STTR program", "")


def test_rejects_bare_sbir_mention_without_phase_iii():
    # a plain SBIR mention (e.g. a Phase I/II notice) is NOT a Phase III self-label
    assert not is_self_labeled("SBIR Phase I topic release", "seeking Phase I proposals")
    assert not is_self_labeled("Research services", "General R&D requirement, no SBIR.")


def test_classify_award_intent_sources_sought():
    # confirmed award (retrospective positive)
    assert classify_notice({"Type": "Award Notice", "AwardNumber": "N00024-23-C-5209"}) == "award"
    # pre-award intent naming the firm (forward positive)
    assert (
        classify_notice(
            {"Type": "Special Notice", "Title": "Notice of Intent to Sole Source: SBIR Phase III"}
        )
        == "intent_sole_source"
    )
    # open Phase III need (forward-opportunity feed)
    assert (
        classify_notice({"Type": "Sources Sought", "Title": "Approved SBIR Phase III with IT"})
        == "sources_sought"
    )
