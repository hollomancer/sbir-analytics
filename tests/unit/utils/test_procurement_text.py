"""Tests for the deterministic explanation helpers in procurement_text."""

from sbir_etl.utils.procurement_text import (
    extract_connection_sentences,
    shared_technical_phrases,
    split_sentences,
)


ABSTRACT = (
    "Autonomous ground mobility and sensing for obstacle characterization. "
    "The vehicle can map obstacles and fuse electro-optical and lidar data while "
    "operating on unprepared terrain. Its mission software can share breach-lane "
    "information with maneuver formations."
)
NOTICE = (
    "The Army seeks integration and demonstration of autonomous ground vehicles that "
    "map obstacles, fuse electro-optical and lidar data, and share breach-lane "
    "information with maneuver formations."
)


def test_split_sentences_handles_terminal_punctuation():
    assert split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]
    assert split_sentences(None) == []
    assert split_sentences("   ") == []


def test_connection_picks_non_leading_award_sentence():
    connection = extract_connection_sentences(ABSTRACT, NOTICE)

    assert connection is not None
    award_sentence, opportunity_sentence = connection
    # The buried connecting claim, not the abstract's leading summary.
    assert award_sentence.startswith("The vehicle can map obstacles")
    assert opportunity_sentence.startswith("The Army seeks integration")


def test_connection_returns_none_when_best_is_the_leading_sentence():
    # Single-sentence abstract: leading sentence is all there is — nothing to add.
    assert extract_connection_sentences("Autonomous obstacle mapping robots.", NOTICE) is None


def test_connection_returns_none_below_shared_token_threshold():
    abstract = "Quantum error correction. Superconducting qubit control electronics at scale."
    assert extract_connection_sentences(abstract, NOTICE) is None


def test_shared_phrases_are_multiword_and_read_as_written():
    phrases = shared_technical_phrases(ABSTRACT, NOTICE)

    assert "share breach-lane information" in phrases  # trigram, hyphen preserved
    assert "map obstacles" in phrases
    assert "fuse electro-optical" in phrases
    # No stopword-bridged grams and no bigram already covered by a trigram.
    assert all(" and " not in f" {phrase} " for phrase in phrases)
    assert "breach-lane information" not in phrases


def test_shared_phrases_empty_when_no_multiword_overlap():
    assert shared_technical_phrases("Autonomous robots.", "Robotic autonomy platform.") == []
    assert shared_technical_phrases(None, NOTICE) == []
