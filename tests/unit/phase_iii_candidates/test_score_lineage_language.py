"""Unit tests for TransitionScorer.score_lineage_language (Phase III spec §1.4)."""

from __future__ import annotations

import pytest

from sbir_ml.transition.detection.scoring import TransitionScorer


pytestmark = pytest.mark.fast


def _config(weight: float = 0.10, saturation: int = 3) -> dict:
    return {
        "scoring": {
            "lineage_language": {
                "enabled": True,
                "weight": weight,
                "saturation_matches": saturation,
            }
        }
    }


class TestLineageLanguageDefaults:
    def test_no_config_yields_zero(self):
        scorer = TransitionScorer({})
        assert scorer.score_lineage_language("Phase III follow-on production award") == 0.0

    def test_disabled_config_yields_zero(self):
        scorer = TransitionScorer(
            {"scoring": {"lineage_language": {"enabled": False, "weight": 0.25}}}
        )
        assert scorer.score_lineage_language("Phase III derives from the prior effort.") == 0.0

    def test_none_description_yields_zero(self):
        scorer = TransitionScorer(_config())
        assert scorer.score_lineage_language(None) == 0.0

    def test_empty_description_yields_zero(self):
        scorer = TransitionScorer(_config())
        assert scorer.score_lineage_language("") == 0.0


class TestLineagePhraseMatches:
    def test_single_phrase_scales_by_saturation(self):
        scorer = TransitionScorer(_config(weight=0.10, saturation=3))
        # One distinct phrase -> 1/3 of configured weight.
        score = scorer.score_lineage_language("This award is a Phase III continuation.")
        assert score == pytest.approx(0.10 * (1.0 / 3.0), abs=1e-6)

    def test_saturates_at_configured_threshold(self):
        scorer = TransitionScorer(_config(weight=0.10, saturation=3))
        text = (
            "Phase III derives from the prior SBIR effort. This is a prototype "
            "transition follow-on production covering the interface control document."
        )
        # Hits: "phase iii", "derives from", "prototype transition",
        # "follow-on production", "interface control document" -> >= 3 distinct,
        # so score == weight.
        score = scorer.score_lineage_language(text)
        assert score == pytest.approx(0.10, abs=1e-6)

    def test_data_rights_vocab_contributes(self):
        scorer = TransitionScorer(_config(weight=0.10, saturation=3))
        text = (
            "Deliverables include the technical data package, source code, and "
            "government purpose rights for the test article."
        )
        # 3 distinct data-rights phrases -> full weight.
        score = scorer.score_lineage_language(text)
        assert score == pytest.approx(0.10, abs=1e-6)

    def test_case_insensitive(self):
        scorer = TransitionScorer(_config(weight=0.10, saturation=3))
        a = scorer.score_lineage_language("phase III derives from prior work")
        b = scorer.score_lineage_language("PHASE III DERIVES FROM PRIOR WORK")
        assert a == b
        assert a > 0.0

    def test_repeated_phrase_does_not_compound(self):
        scorer = TransitionScorer(_config(weight=0.10, saturation=3))
        # Same phrase five times -> only 1 distinct match.
        text = "Phase III. Phase III. Phase III. Phase III. Phase III."
        score = scorer.score_lineage_language(text)
        assert score == pytest.approx(0.10 * (1.0 / 3.0), abs=1e-6)

    def test_respects_weight_zero(self):
        scorer = TransitionScorer(_config(weight=0.0))
        assert scorer.score_lineage_language("Phase III derives from prior work.") == 0.0


class TestLineageAdversarialNegatives:
    """Adversarial negatives: text that mentions lineage-adjacent phrases in
    unrelated contexts should not generate a false positive."""

    def test_combustion_phase_iii_is_false_positive_caveat(self):
        """Combustion "Phase III" of a chemical reaction triggers the phrase match.

        This is a known limitation of a cheap phrase-match v1. The phrase
        matches because the surface form is the same; downstream precision
        depends on signal combination, not this single method. The test
        documents the known weakness rather than claiming robustness.
        """
        scorer = TransitionScorer(_config(weight=0.10, saturation=3))
        text = "The reaction proceeds through Phase III of combustion in the chamber."
        score = scorer.score_lineage_language(text)
        # One distinct phrase match -> saturation-scaled weight.
        assert score == pytest.approx(0.10 * (1.0 / 3.0), abs=1e-6)

    def test_prototype_in_non_transition_context_does_not_match(self):
        """The phrase list is 'prototype transition', not 'prototype' alone.

        An abstract mentioning 'prototype' on its own should not match.
        """
        scorer = TransitionScorer(_config(weight=0.10, saturation=3))
        text = "We built a prototype robot and tested it."
        assert scorer.score_lineage_language(text) == 0.0

    def test_phase_substring_does_not_match(self):
        """Word boundaries keep 'superphase iiixyz' from matching."""
        scorer = TransitionScorer(_config(weight=0.10, saturation=3))
        assert scorer.score_lineage_language("superphase iiixyz assembly") == 0.0

    def test_generic_phase_i_or_ii_does_not_match(self):
        scorer = TransitionScorer(_config(weight=0.10, saturation=3))
        assert scorer.score_lineage_language("Phase I award for feasibility study.") == 0.0
        assert scorer.score_lineage_language("Phase II SBIR development effort.") == 0.0

    def test_extends_bare_word_still_matches(self):
        """'Extends' is on the list. A sentence that happens to use it will match.

        This is a known precision cost of the bare-word 'extends' entry. We
        document it — downstream weighting tempers the effect.
        """
        scorer = TransitionScorer(_config(weight=0.10, saturation=3))
        text = "The company extends its product line with consumer goods."
        # One distinct match.
        score = scorer.score_lineage_language(text)
        assert score == pytest.approx(0.10 * (1.0 / 3.0), abs=1e-6)


class TestLineageBoundedScore:
    def test_always_in_zero_one(self):
        scorer = TransitionScorer(_config(weight=0.9, saturation=1))
        # Saturation=1 + high weight: a single match hits the full weight but
        # must still be bounded by 1.0.
        text = "Phase III derives from prototype transition follow-on production."
        score = scorer.score_lineage_language(text)
        assert 0.0 <= score <= 1.0
