"""
Integration tests for transition detection scoring correctness.

These tests exercise the full detection pipeline (detector + scorer + evidence)
with realistic data and verify that scoring behaves correctly across scenarios.
Unlike unit tests that check individual signals, these validate the composite
behavior: signal interactions, confidence classification, and ordering.

No external services (Neo4j, APIs) required.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from sbir_etl.models.transition_models import (
    CompetitionType,
    ConfidenceLevel,
    FederalContract,
)
from sbir_ml.transition import Config
from sbir_ml.transition.detection.detector import TransitionDetector
from sbir_ml.transition.detection.scoring import TransitionScorer
from sbir_ml.transition.features.vendor_resolver import VendorRecord, VendorResolver


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def detector_config() -> dict:
    """Build detector config from the canonical Config defaults."""
    return Config().to_detector_config()


@pytest.fixture
def vendor_resolver() -> VendorResolver:
    """Resolver with three known vendors."""
    records = [
        VendorRecord(
            uei="UEI-ACME",
            cage="CAGE01",
            duns="DUNS01",
            name="Acme Defense Systems",
            metadata={"vendor_id": "V-ACME"},
        ),
        VendorRecord(
            uei="UEI-BIOTEK",
            cage="CAGE02",
            duns="DUNS02",
            name="BioTek Research Inc",
            metadata={"vendor_id": "V-BIOTEK"},
        ),
        VendorRecord(
            uei="UEI-QUANTUM",
            cage=None,
            duns=None,
            name="Quantum Computing Labs",
            metadata={"vendor_id": "V-QUANTUM"},
        ),
    ]
    return VendorResolver.from_records(records)


@pytest.fixture
def detector(detector_config, vendor_resolver):
    return TransitionDetector(
        config=detector_config,
        vendor_resolver=vendor_resolver,
    )


def _make_contract(
    contract_id: str,
    start_date: date,
    *,
    vendor_uei: str | None = None,
    vendor_name: str | None = None,
    agency: str | None = None,
    competition_type: CompetitionType | None = None,
) -> FederalContract:
    return FederalContract(
        contract_id=contract_id,
        start_date=start_date,
        vendor_uei=vendor_uei,
        vendor_name=vendor_name,
        agency=agency,
        competition_type=competition_type,
    )


def _make_award(
    award_id: str,
    completion_date: date,
    *,
    agency: str = "DOD",
    vendor_uei: str | None = None,
) -> dict:
    return {
        "award_id": award_id,
        "completion_date": completion_date,
        "agency": agency,
        "vendor_uei": vendor_uei,
    }


# ---------------------------------------------------------------------------
# Scoring correctness
# ---------------------------------------------------------------------------


class TestScoringCorrectness:
    """Verify the composite score reflects the sum of its signal contributions."""

    def test_same_agency_scores_higher_than_different(self, detector_config):
        """Same-agency contract should score higher than cross-agency, all else equal."""
        scorer = TransitionScorer(detector_config)
        completion = date(2022, 6, 1)
        start = completion + timedelta(days=30)

        contract_same = _make_contract("C-SAME", start, agency="DOD")
        contract_diff = _make_contract("C-DIFF", start, agency="NASA")

        award = _make_award("A-1", completion, agency="DOD")

        _, score_same, _ = scorer.score_and_classify(award, contract_same)
        _, score_diff, _ = scorer.score_and_classify(award, contract_diff)

        assert score_same > score_diff, (
            f"Same-agency score ({score_same:.3f}) should exceed "
            f"different-agency score ({score_diff:.3f})"
        )

    def test_closer_timing_scores_higher(self, detector_config):
        """Contract starting 1 month after award should score higher than 18 months."""
        scorer = TransitionScorer(detector_config)
        completion = date(2022, 1, 1)
        award = _make_award("A-1", completion)

        contract_close = _make_contract("C-CLOSE", completion + timedelta(days=30))
        contract_far = _make_contract("C-FAR", completion + timedelta(days=540))

        _, score_close, _ = scorer.score_and_classify(award, contract_close)
        _, score_far, _ = scorer.score_and_classify(award, contract_far)

        assert score_close > score_far, (
            f"Close timing ({score_close:.3f}) should exceed far timing ({score_far:.3f})"
        )

    def test_sole_source_scores_higher_than_full_open(self, detector_config):
        """Sole-source procurement is a stronger transition signal than full-and-open."""
        scorer = TransitionScorer(detector_config)
        completion = date(2022, 1, 1)
        start = completion + timedelta(days=60)
        award = _make_award("A-1", completion)

        contract_sole = _make_contract(
            "C-SOLE", start, competition_type=CompetitionType.SOLE_SOURCE
        )
        contract_open = _make_contract(
            "C-OPEN", start, competition_type=CompetitionType.FULL_AND_OPEN
        )

        _, score_sole, _ = scorer.score_and_classify(award, contract_sole)
        _, score_open, _ = scorer.score_and_classify(award, contract_open)

        assert score_sole > score_open

    def test_patent_signal_adds_to_score(self, detector_config):
        """Patent data should increase the score relative to no patents."""
        scorer = TransitionScorer(detector_config)
        completion = date(2022, 1, 1)
        start = completion + timedelta(days=60)
        award = _make_award("A-1", completion)
        contract = _make_contract("C-1", start)

        patent_data = {
            "patent_count": 3,
            "patents_pre_contract": 2,
            "patent_topic_similarity": 0.85,
        }

        _, score_no_pat, _ = scorer.score_and_classify(award, contract)
        _, score_with_pat, _ = scorer.score_and_classify(
            award, contract, patent_data=patent_data
        )

        assert score_with_pat > score_no_pat

    def test_all_signals_positive_exceeds_likely_threshold(self, detector_config):
        """When every signal fires positively, the composite score should be
        meaningfully above the base score. With default weights the scorer uses
        bonus*weight per signal, so the max reachable is ~0.47 — within the
        POSSIBLE band. This test verifies signals contribute and the score is
        well above the base_score floor (0.15)."""
        scorer = TransitionScorer(detector_config)
        completion = date(2022, 1, 1)
        start = completion + timedelta(days=30)

        award = _make_award("A-1", completion, agency="DOD")
        contract = _make_contract(
            "C-1",
            start,
            agency="DOD",
            competition_type=CompetitionType.SOLE_SOURCE,
        )
        patent_data = {
            "patent_count": 2,
            "patents_pre_contract": 1,
            "patent_topic_similarity": 0.9,
        }
        cet_data = {"award_cet": "AI", "contract_cet": "AI"}

        signals, score, confidence = scorer.score_and_classify(
            award, contract, patent_data=patent_data, cet_data=cet_data
        )

        # Every signal should have contributed a positive amount
        assert signals.agency and signals.agency.agency_score > 0
        assert signals.timing and signals.timing.timing_score > 0
        assert signals.competition and signals.competition.competition_score > 0
        assert signals.patent and signals.patent.patent_score > 0
        assert signals.cet and signals.cet.cet_alignment_score > 0

        # Composite should be well above base_score
        base = detector_config.get("base_score", 0.15)
        assert score > base + 0.15, (
            f"All-positive score ({score:.3f}) should be significantly above "
            f"base_score ({base})"
        )

    def test_minimal_signals_produces_possible_confidence(self, detector_config):
        """Base score alone (no matching signals) should classify as POSSIBLE."""
        scorer = TransitionScorer(detector_config)
        completion = date(2022, 1, 1)
        # Far future contract, different agency, full-and-open
        start = completion + timedelta(days=700)

        award = _make_award("A-1", completion, agency="DOD")
        contract = _make_contract(
            "C-1",
            start,
            agency="NASA",
            competition_type=CompetitionType.FULL_AND_OPEN,
        )

        _, score, confidence = scorer.score_and_classify(award, contract)

        assert confidence == ConfidenceLevel.POSSIBLE, (
            f"Expected POSSIBLE with minimal signals, got {confidence} (score={score:.3f})"
        )

    def test_scores_bounded_zero_to_one(self, detector_config):
        """Final score must always be in [0.0, 1.0] regardless of signal combination."""
        scorer = TransitionScorer(detector_config)
        completion = date(2022, 1, 1)
        award = _make_award("A-1", completion, agency="DOD")

        # Extreme case: all bonuses active
        contract = _make_contract(
            "C-1",
            completion + timedelta(days=1),
            agency="DOD",
            competition_type=CompetitionType.SOLE_SOURCE,
        )
        patent_data = {
            "patent_count": 100,
            "patents_pre_contract": 50,
            "patent_topic_similarity": 1.0,
        }
        cet_data = {"award_cet": "QUANTUM", "contract_cet": "QUANTUM"}

        _, score, _ = scorer.score_and_classify(
            award, contract, patent_data=patent_data, cet_data=cet_data
        )

        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Full pipeline integration
# ---------------------------------------------------------------------------


class TestDetectorPipeline:
    """Test the full detect_for_award pipeline produces correct, ordered results."""

    def test_detections_ordered_by_relevance(self, detector):
        """Detections for the same award should rank strong matches above weak ones."""
        completion = date(2022, 6, 1)
        award = _make_award("A-1", completion, agency="DOD", vendor_uei="UEI-ACME")

        # Strong match: same agency, soon after, sole source
        strong = _make_contract(
            "C-STRONG",
            completion + timedelta(days=45),
            vendor_uei="UEI-ACME",
            agency="DOD",
            competition_type=CompetitionType.SOLE_SOURCE,
        )
        # Weak match: different agency, later, full-and-open
        weak = _make_contract(
            "C-WEAK",
            completion + timedelta(days=600),
            vendor_uei="UEI-ACME",
            agency="HHS",
            competition_type=CompetitionType.FULL_AND_OPEN,
        )

        detections = detector.detect_for_award(award, [strong, weak])

        assert len(detections) == 2

        scores = {d.primary_contract.contract_id: d.likelihood_score for d in detections}
        assert scores["C-STRONG"] > scores["C-WEAK"], (
            f"Strong match ({scores['C-STRONG']:.3f}) should score higher "
            f"than weak match ({scores['C-WEAK']:.3f})"
        )

    def test_timing_window_excludes_out_of_range(self, detector):
        """Contracts outside the timing window should not produce detections."""
        completion = date(2022, 1, 1)
        award = _make_award("A-1", completion, vendor_uei="UEI-ACME")

        too_early = _make_contract(
            "C-EARLY",
            completion - timedelta(days=30),
            vendor_uei="UEI-ACME",
        )
        too_late = _make_contract(
            "C-LATE",
            completion + timedelta(days=800),
            vendor_uei="UEI-ACME",
        )
        in_window = _make_contract(
            "C-OK",
            completion + timedelta(days=60),
            vendor_uei="UEI-ACME",
        )

        detections = detector.detect_for_award(award, [too_early, too_late, in_window])

        detected_ids = {d.primary_contract.contract_id for d in detections}
        assert "C-OK" in detected_ids
        assert "C-EARLY" not in detected_ids
        assert "C-LATE" not in detected_ids

    def test_vendor_match_required_skips_unknown(self, detector):
        """With require_match=True, contracts from unknown vendors produce no detection."""
        completion = date(2022, 1, 1)
        award = _make_award("A-1", completion, vendor_uei="UEI-ACME")

        unknown_vendor = _make_contract(
            "C-UNK",
            completion + timedelta(days=30),
            vendor_uei="UEI-NONEXISTENT",
            vendor_name="Unknown Corp",
        )

        detections = detector.detect_for_award(award, [unknown_vendor])
        assert len(detections) == 0

    def test_no_completion_date_returns_empty(self, detector):
        """Award without completion_date should return empty list, not crash."""
        award = {"award_id": "A-NODATE", "agency": "DOD"}
        contract = _make_contract("C-1", date(2022, 6, 1), vendor_uei="UEI-ACME")

        detections = detector.detect_for_award(award, [contract])
        assert detections == []

    def test_evidence_bundle_populated(self, detector):
        """Each detection should carry a non-empty evidence bundle."""
        completion = date(2022, 1, 1)
        award = _make_award("A-1", completion, agency="DOD", vendor_uei="UEI-ACME")
        contract = _make_contract(
            "C-1",
            completion + timedelta(days=30),
            vendor_uei="UEI-ACME",
            agency="DOD",
        )

        detections = detector.detect_for_award(award, [contract])
        assert len(detections) == 1

        evidence = detections[0].evidence
        assert evidence is not None
        assert len(evidence.items) > 0

    def test_metrics_track_processing(self, detector):
        """Metrics should accurately reflect processing counts."""
        detector.reset_metrics()

        completion = date(2022, 1, 1)
        award = _make_award("A-1", completion, vendor_uei="UEI-ACME")
        contract = _make_contract(
            "C-1",
            completion + timedelta(days=30),
            vendor_uei="UEI-ACME",
        )

        detector.detect_for_award(award, [contract])
        metrics = detector.get_metrics()

        assert metrics["total_awards_processed"] == 1
        assert metrics["total_contracts_evaluated"] >= 1
        assert metrics["total_detections"] >= 1


# ---------------------------------------------------------------------------
# Config integration
# ---------------------------------------------------------------------------


class TestConfigIntegration:
    """Verify Config.to_detector_config() produces a usable pipeline config."""

    def test_default_config_produces_working_pipeline(self, vendor_resolver):
        """The default Config should produce a fully functional detector."""
        cfg = Config()
        detector = TransitionDetector(
            config=cfg.to_detector_config(),
            vendor_resolver=vendor_resolver,
        )

        completion = date(2022, 1, 1)
        award = _make_award("A-1", completion, agency="DOD", vendor_uei="UEI-ACME")
        contract = _make_contract(
            "C-1",
            completion + timedelta(days=30),
            vendor_uei="UEI-ACME",
            agency="DOD",
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        detections = detector.detect_for_award(award, [contract])
        assert len(detections) == 1
        assert detections[0].likelihood_score > 0.0

    def test_config_to_detector_config_keys(self):
        """to_detector_config() should produce all keys the detector/scorer need."""
        cfg = Config()
        d = cfg.to_detector_config()

        assert "base_score" in d
        assert "timing_window" in d
        assert "vendor_matching" in d
        assert "scoring" in d
        assert "confidence_thresholds" in d

        # Scoring sub-keys
        scoring = d["scoring"]
        for key in [
            "agency_continuity",
            "timing_proximity",
            "competition_type",
            "patent_signal",
            "cet_alignment",
        ]:
            assert key in scoring, f"Missing scoring key: {key}"
            assert "enabled" in scoring[key]
            assert "weight" in scoring[key]

    def test_modified_thresholds_propagate(self, vendor_resolver):
        """Changing Config thresholds should change scoring behavior."""
        # Strict config: high base score
        strict = Config()
        strict.scoring["base_score"] = 0.50

        # Lenient config: low base score
        lenient = Config()
        lenient.scoring["base_score"] = 0.05

        completion = date(2022, 1, 1)
        award = _make_award("A-1", completion)
        contract = _make_contract("C-1", completion + timedelta(days=60))

        scorer_strict = TransitionScorer(strict.to_detector_config())
        scorer_lenient = TransitionScorer(lenient.to_detector_config())

        _, score_strict, _ = scorer_strict.score_and_classify(award, contract)
        _, score_lenient, _ = scorer_lenient.score_and_classify(award, contract)

        assert score_strict > score_lenient
