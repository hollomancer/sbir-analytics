"""Unit tests for the topical-similarity helper (Phase III candidate spec §1.3).

Includes adversarial negatives that verify the feature bag does not credit
spurious topical matches when codes disagree or text overlap collapses to
stopwords. The text channel is corpus-fitted TF-IDF cosine (Phase 2 of the
why-it-connects design), not token Jaccard.
"""

from __future__ import annotations

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_candidates.similarity import (
    DEFAULT_WEIGHTS,
    compute_text_similarity_batch,
    compute_topical_similarity,
)


pytestmark = pytest.mark.fast


class TestCodeAgreement:
    def test_exact_naics_and_psc_match_with_strong_text(self):
        prior = {
            "naics_code": "541715",
            "psc_code": "AJ11",
            "title": "Autonomous unmanned aerial vehicle navigation",
            "abstract": "Reinforcement learning pipeline for UAV obstacle avoidance.",
        }
        target = {
            "naics_code": "541715",
            "psc_code": "AJ11",
            "description": "Autonomous UAV navigation with reinforcement learning pipeline.",
        }
        score = compute_topical_similarity(prior, target)
        # NAICS + PSC contribute 0.30 + 0.20 = 0.50; text cosine is high.
        assert score > 0.7

    def test_naics_mismatch_drops_contribution(self):
        prior = {
            "naics_code": "541715",
            "psc_code": "AJ11",
            "title": "UAV navigation",
            "abstract": "Obstacle avoidance",
        }
        target = {
            "naics_code": "722110",  # restaurants — unrelated
            "psc_code": "AJ11",
            "description": "UAV navigation obstacle avoidance",
        }
        score = compute_topical_similarity(prior, target)
        # Text + PSC contribute; NAICS explicitly mismatches.
        assert 0.4 <= score <= 0.9
        # Removing the PSC too should drop further.
        target_no_psc = {**target, "psc_code": None}
        assert compute_topical_similarity(prior, target_no_psc) < score

    def test_missing_codes_return_zero_for_code_channels(self):
        prior = {"naics_code": None, "psc_code": None, "title": "a b c", "abstract": "d e f"}
        target = {"naics_code": None, "psc_code": None, "description": "a b c d e f"}
        score = compute_topical_similarity(prior, target)
        # Only text contributes; single-character tokens are dropped by the vectorizer.
        assert score == 0.0


class TestTextChannel:
    def test_identical_texts_saturate_the_text_weight(self):
        prior = {
            "naics_code": None,
            "psc_code": None,
            "title": "hypersonic propulsion scramjet combustor",
            "abstract": "additive-manufactured nickel superalloy liner",
        }
        target = {
            "naics_code": None,
            "psc_code": None,
            "description": (
                "hypersonic propulsion scramjet combustor additive-manufactured nickel "
                "superalloy liner"
            ),
        }
        score = compute_topical_similarity(prior, target)
        # Identical text on both sides -> cosine 1.0 -> exactly the text weight.
        assert score == pytest.approx(DEFAULT_WEIGHTS["text"], abs=1e-6)

    def test_stopword_only_overlap_does_not_credit(self):
        prior = {
            "naics_code": None,
            "psc_code": None,
            "title": "the of and for to in on at with by",
            "abstract": None,
        }
        target = {
            "naics_code": None,
            "psc_code": None,
            "description": "the of and for to in on at with by",
        }
        score = compute_topical_similarity(prior, target)
        # English stopwords are removed, so the text cosine is 0.
        assert score == 0.0

    def test_totally_different_descriptions_score_zero(self):
        prior = {
            "naics_code": None,
            "psc_code": None,
            "title": "hypersonic scramjet propulsion",
            "abstract": None,
        }
        target = {
            "naics_code": None,
            "psc_code": None,
            "description": "pediatric oncology clinical trial enrollment",
        }
        score = compute_topical_similarity(prior, target)
        assert score == 0.0

    def test_batch_idf_downweights_corpus_common_terms(self):
        """Corpus-fitted idf: a match on a run-ubiquitous word counts less than rare jargon."""

        pairs = pd.DataFrame(
            [
                # Every row mentions "system"; only this pair shares rare jargon too.
                {
                    "prior_title": "scramjet combustor system",
                    "prior_abstract": None,
                    "target_description": "scramjet combustor demonstration system",
                },
                # This pair shares only the ubiquitous word.
                {
                    "prior_title": "logistics resupply system",
                    "prior_abstract": None,
                    "target_description": "oncology enrollment system",
                },
                {
                    "prior_title": "sensor system",
                    "prior_abstract": None,
                    "target_description": "radar system",
                },
            ]
        )
        sims = compute_text_similarity_batch(pairs)
        assert len(sims) == 3
        assert sims[0] > sims[1]  # rare-jargon match beats common-word-only match
        assert all(0.0 <= value <= 1.0 for value in sims)

    def test_batch_empty_frame_returns_empty(self):
        assert compute_text_similarity_batch(pd.DataFrame()) == []


class TestAdversarialNegatives:
    def test_naics_match_but_no_token_overlap(self):
        """NAICS-matching projects with different subject matter.

        NAICS 541715 covers a large R&D swath. Same code, wildly different
        projects. The NAICS channel should still credit; text and PSC
        should not.
        """
        prior = {
            "naics_code": "541715",
            "psc_code": None,
            "title": "Quantum dot solar cell materials",
            "abstract": "Colloidal synthesis",
        }
        target = {
            "naics_code": "541715",
            "psc_code": None,
            "description": "Shipboard firefighting robot actuator suite",
        }
        score = compute_topical_similarity(prior, target)
        # Only NAICS channel fires.
        assert score == pytest.approx(DEFAULT_WEIGHTS["naics"], abs=1e-6)

    def test_empty_inputs_yield_zero(self):
        assert compute_topical_similarity({}, {}) == 0.0

    def test_nullable_pandas_text_yields_zero(self):
        prior = {"title": pd.NA, "abstract": float("nan")}
        target = {"description": pd.NA}
        assert compute_topical_similarity(prior, target) == 0.0

    def test_score_is_bounded(self):
        prior = {
            "naics_code": "541715",
            "psc_code": "AJ11",
            "title": "alpha beta gamma delta epsilon",
            "abstract": "zeta eta theta iota kappa",
        }
        target = {
            "naics_code": "541715",
            "psc_code": "AJ11",
            "description": "alpha beta gamma delta epsilon zeta eta theta iota kappa",
        }
        score = compute_topical_similarity(prior, target)
        assert 0.0 <= score <= 1.0

    def test_user_weights_that_exceed_one_are_clamped(self):
        """If a caller passes broken weights, the result still stays in [0, 1]."""
        prior = {"naics_code": "A", "psc_code": "A", "title": "alpha", "abstract": "alpha"}
        target = {"naics_code": "A", "psc_code": "A", "description": "alpha"}
        score = compute_topical_similarity(
            prior, target, weights={"naics": 1.0, "psc": 1.0, "text": 1.0}
        )
        assert score == 1.0

    def test_precomputed_text_similarity_bypasses_fit(self):
        prior = {"naics_code": "541715", "psc_code": None, "title": "x", "abstract": None}
        target = {"naics_code": "541715", "psc_code": None, "description": "y"}
        score = compute_topical_similarity(prior, target, text_similarity=1.0)
        assert score == pytest.approx(DEFAULT_WEIGHTS["naics"] + DEFAULT_WEIGHTS["text"], abs=1e-6)


def test_missing_codes_do_not_count_as_agreement():
    import pandas as pd

    from sbir_analytics.assets.phase_iii_candidates.similarity import normalize_code

    for missing in (None, float("nan"), pd.NA, pd.NaT, "", "  ", "N/A"):
        assert normalize_code(missing) is None

    # Two missing codes must contribute nothing — otherwise unrelated text clears
    # the 0.10 S3 topical gate on absence alone.
    assert (
        compute_topical_similarity(
            {"naics_code": pd.NA, "psc_code": float("nan"), "title": "alpha"},
            {"naics_code": pd.NA, "psc_code": float("nan"), "description": "beta"},
            text_similarity=0.0,
        )
        == 0.0
    )
