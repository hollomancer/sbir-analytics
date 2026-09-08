"""Probes for the D5 text-trail scorer and its frozen v1 phrase lexicon.

Exploratory tier: covers phrase-matching correctness on realistic and edge
cases (blank abstract, no match, exact match, case variation) and the
`D5TextTrail` status/reason mapping -- not a comprehensive matrix over every
lexicon pattern or every conceivable abstract phrasing.
"""

from __future__ import annotations

import pytest

from scripts.sttr_spinout_linkage.d5_scorer import (
    DEFAULT_LEXICON_PATH,
    load_lexicon,
    score_d5_text_trail,
)
from scripts.sttr_spinout_linkage.kernel import DimensionStatus, SignalAbsentReason


pytestmark = pytest.mark.fast


class TestLoadLexicon:
    def test_loads_the_frozen_v1_lexicon_file(self) -> None:
        lexicon = load_lexicon()
        assert lexicon.version == "v1"
        assert len(lexicon.pattern_ids) >= 5
        assert len(lexicon.compiled) == len(lexicon.pattern_ids)

    def test_raises_on_a_missing_lexicon_file(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            load_lexicon(tmp_path / "does-not-exist.json")

    def test_default_lexicon_path_exists(self) -> None:
        assert DEFAULT_LEXICON_PATH.exists()


class TestScoreD5TextTrail:
    def test_blank_abstract_is_not_measurable_with_source_field_unavailable(self) -> None:
        for blank in (None, "", "   ", float("nan")):
            trail = score_d5_text_trail(blank)
            assert trail.status is DimensionStatus.NOT_MEASURABLE
            assert trail.reason is SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE
            assert trail.spinout_phrase is False

    def test_abstract_with_no_lexicon_match_is_measured_negative(self) -> None:
        abstract = (
            "This Phase II project develops a novel widget for detecting "
            "corrosion in aerospace structures using ultrasonic sensors."
        )
        trail = score_d5_text_trail(abstract)
        assert trail.status is DimensionStatus.MEASURED
        assert trail.spinout_phrase is False
        assert trail.reason is None

    def test_exact_phrase_match_is_measured_positive(self) -> None:
        abstract = "The company was spun out of MIT's Media Lab in 2019."
        trail = score_d5_text_trail(abstract)
        assert trail.status is DimensionStatus.MEASURED
        assert trail.spinout_phrase is True

    def test_match_is_case_insensitive(self) -> None:
        abstract = "The firm was SPUN OUT OF Stanford University."
        trail = score_d5_text_trail(abstract)
        assert trail.spinout_phrase is True

    def test_founded_by_professor_title_matches(self) -> None:
        abstract = "The startup was founded by Professor Jane Smith of UC Berkeley."
        trail = score_d5_text_trail(abstract)
        assert trail.spinout_phrase is True

    def test_founded_by_bare_name_does_not_match(self) -> None:
        """Deliberately excluded per the lexicon's `deliberately_excluded` list:
        a founder name with no academic title or role noun is not distinguishable
        from a non-RI-affiliated founder from text alone."""
        abstract = "The company was founded by John Doe in 2015."
        trail = score_d5_text_trail(abstract)
        assert trail.status is DimensionStatus.MEASURED
        assert trail.spinout_phrase is False

    def test_exclusive_license_from_matches(self) -> None:
        abstract = "The firm holds an exclusive license from the University of Texas."
        trail = score_d5_text_trail(abstract)
        assert trail.spinout_phrase is True

    def test_bare_licensed_from_does_not_match(self) -> None:
        """Deliberately excluded: too generic a phrase to be spinout-specific
        (see the lexicon's `deliberately_excluded` list)."""
        abstract = "The team licensed from a commercial vendor a standard software toolkit."
        trail = score_d5_text_trail(abstract)
        assert trail.spinout_phrase is False

    def test_generic_partnership_language_does_not_match(self) -> None:
        abstract = (
            "This STTR project is conducted in partnership with and in collaboration "
            "with the research institution, which provides technical support."
        )
        trail = score_d5_text_trail(abstract)
        assert trail.status is DimensionStatus.MEASURED
        assert trail.spinout_phrase is False

    def test_based_on_technology_developed_at_matches(self) -> None:
        abstract = "This product is based on technology developed at Carnegie Mellon University."
        trail = score_d5_text_trail(abstract)
        assert trail.spinout_phrase is True
