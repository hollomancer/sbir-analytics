"""Tests for CET-area agreement facts."""

from pathlib import Path

from sbir_etl.reporting.procurement_transition.cet_vocabulary import (
    cet_agreement_fact,
    load_cet_vocabulary,
)


TAXONOMY = str(Path("config/cet/taxonomy.yaml"))


def test_vocabulary_loads_all_areas():
    vocabulary = load_cet_vocabulary(TAXONOMY)

    assert len(vocabulary) == 21
    assert "autonomous navigation" in vocabulary["autonomous systems"]


def test_agreement_fact_quotes_matched_keywords():
    fact = cet_agreement_fact(
        "Autonomous Systems",
        "Demonstration using autonomous navigation and path planning in denied environments.",
        taxonomy_path=TAXONOMY,
    )

    assert fact is not None
    assert fact.startswith("Both fall in the Autonomous Systems critical-technology area")
    assert "“autonomous navigation”" in fact
    assert "“path planning”" in fact


def test_agreement_fact_none_without_keyword_hit():
    fact = cet_agreement_fact(
        "Autonomous Systems",
        "Supply administrative office furniture.",
        taxonomy_path=TAXONOMY,
    )
    assert fact is None


def test_agreement_fact_none_for_unknown_or_missing_label():
    assert (
        cet_agreement_fact("Not A Real Area", "autonomous navigation", taxonomy_path=TAXONOMY)
        is None
    )
    assert cet_agreement_fact(None, "autonomous navigation", taxonomy_path=TAXONOMY) is None


def test_missing_taxonomy_degrades_to_empty():
    assert load_cet_vocabulary("/nonexistent/taxonomy.yaml") == {}
    assert (
        cet_agreement_fact(
            "Autonomous Systems", "autonomous navigation", taxonomy_path="/nonexistent/x.yaml"
        )
        is None
    )
