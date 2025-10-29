"""
Transition scoring algorithm for SBIR commercialization likelihood estimation.

This module implements a multi-signal scoring system that combines:
- Agency continuity (same agency contracts indicate strong relationship)
- Timing proximity (contracts soon after award completion)
- Competition type (sole source indicates targeted procurement)
- Patent signals (commercialization readiness indicators)
- CET area alignment (technology area consistency)
- Text similarity (optional, description matching)

The scorer uses configurable weights and thresholds from YAML configuration
to produce a composite likelihood score (0.0-1.0) and confidence classification.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger

from src.models.transition_models import (
    AgencySignal,
    CETSignal,
    CompetitionSignal,
    CompetitionType,
    ConfidenceLevel,
    FederalContract,
    PatentSignal,
    TimingSignal,
    TransitionSignals,
)


class TransitionScorer:
    """
    Composite scoring algorithm for transition likelihood estimation.

    Combines multiple independent signals with configurable weights to produce
    a final likelihood score and confidence classification.

    Example:
        ```python
        config = {
            "base_score": 0.15,
            "scoring": {
                "agency_continuity": {
                    "enabled": True,
                    "weight": 0.25,
                    "same_agency_bonus": 0.25
                },
                # ... other signals
            },
            "confidence_thresholds": {
                "high": 0.85,
                "likely": 0.65
            }
        }

        scorer = TransitionScorer(config)
        signals = scorer.score_transition(
            award_data={...},
            contract_data={...}
        )
        score = scorer.compute_final_score(signals)
        confidence = scorer.classify_confidence(score)
        ```
    """

    def __init__(self, config: dict[str, Any]):
        """
        Initialize scorer with configuration.

        Args:
            config: Configuration dict with scoring weights and thresholds.
                    Expected keys:
                    - base_score: Baseline minimum score
                    - scoring: Dict of signal configs (agency_continuity, timing_proximity, etc.)
                    - confidence_thresholds: Dict with 'high' and 'likely' thresholds
        """
        self.config = config
        self.base_score = config.get("base_score", 0.15)

        # Extract scoring configuration
        scoring_config = config.get("scoring", {})
        self.agency_config = scoring_config.get("agency_continuity", {})
        self.timing_config = scoring_config.get("timing_proximity", {})
        self.competition_config = scoring_config.get("competition_type", {})
        self.patent_config = scoring_config.get("patent_signal", {})
        self.cet_config = scoring_config.get("cet_alignment", {})
        self.vendor_config = scoring_config.get("vendor_match", {})

        # Extract confidence thresholds
        thresholds = config.get("confidence_thresholds", {})
        self.high_threshold = thresholds.get("high", 0.85)
        self.likely_threshold = thresholds.get("likely", 0.65)

        logger.debug(
            "Initialized TransitionScorer",
            extra={
                "base_score": self.base_score,
                "high_threshold": self.high_threshold,
                "likely_threshold": self.likely_threshold,
            },
        )

    def score_agency_continuity(
        self,
        award_data: dict[str, Any],
        contract: FederalContract,
    ) -> AgencySignal:
        """
        Score agency continuity between SBIR award and federal contract.

        Same agency strongly suggests relationship; cross-agency within same
        department provides weaker signal.

        Args:
            award_data: Award information
            contract: FederalContract object

        Returns:
            AgencySignal with continuity scoring
        """
        award_agency = award_data.get("agency")
        contract_agency = contract.agency
        award_department = award_data.get("department")
        contract_department = contract.sub_agency

        if not award_agency or not contract_agency:
            return AgencySignal(same_agency=False, agency_score=0.0)

        # Normalize agencies for comparison (uppercase, strip)
        award_agency_norm = str(award_agency).upper().strip()
        contract_agency_norm = str(contract_agency).upper().strip()

        same_agency = award_agency_norm == contract_agency_norm

        # Check department if available
        same_department = False
        if award_department and contract_department:
            award_dept_norm = str(award_department).upper().strip()
            contract_dept_norm = str(contract_department).upper().strip()
            same_department = award_dept_norm == contract_dept_norm

        # Calculate score based on configuration
        if same_agency:
            bonus = self.agency_config.get("same_agency_bonus", 0.25)
            score = bonus * self.agency_config.get("weight", 0.25)
        elif same_department:
            bonus = self.agency_config.get("cross_service_bonus", 0.125)
            score = bonus * self.agency_config.get("weight", 0.25)
        else:
            # Different department - minimal bonus
            bonus = self.agency_config.get("different_dept_bonus", 0.05)
            score = bonus * self.agency_config.get("weight", 0.25)

        return AgencySignal(
            same_agency=same_agency,
            same_department=same_department if award_department and contract_department else None,
            agency_score=min(score, 1.0),  # Cap at 1.0
        )

    def score_timing_proximity(
        self,
        award_data: dict[str, Any],
        contract: FederalContract,
    ) -> TimingSignal:
        """
        Score timing proximity between award completion and contract start.

        Closer timing indicates stronger likelihood of transition. Uses
        configured time windows with decay multipliers.

        Args:
            award_data: Award information
            contract: FederalContract object

        Returns:
            TimingSignal with days/months and timing score
        """
        award_completion_date = award_data.get("completion_date")
        contract_start_date = contract.start_date

        if not award_completion_date or not contract_start_date:
            return TimingSignal(timing_score=0.0)

        # Calculate days between
        days_between = (contract_start_date - award_completion_date).days

        # Handle contracts before award completion (negative days)
        if days_between < 0:
            logger.warning(
                "Contract starts before award completion",
                extra={
                    "days_between": days_between,
                    "award_completion": award_completion_date.isoformat(),
                    "contract_start": contract_start_date.isoformat(),
                },
            )
            return TimingSignal(
                days_between_award_and_contract=days_between,
                months_between_award_and_contract=days_between / 30.0,
                timing_score=0.0,
            )

        # Calculate months
        months_between = days_between / 30.0

        # Score based on configured windows
        windows = self.timing_config.get("windows", [])
        timing_weight = self.timing_config.get("weight", 0.20)

        score = 0.0
        for window in windows:
            range_def = window.get("range", [])
            if len(range_def) == 2:
                min_days, max_days = range_def
                if min_days <= days_between <= max_days:
                    window_score = window.get("score", 0.0)
                    score = window_score * timing_weight
                    break

        # Apply beyond window penalty if configured
        if score == 0.0:
            beyond_penalty = self.timing_config.get("beyond_window_penalty", 0.0)
            score = beyond_penalty

        return TimingSignal(
            days_between_award_and_contract=days_between,
            months_between_award_and_contract=round(months_between, 1),
            timing_score=min(score, 1.0),
        )

    def score_competition_type(self, contract: FederalContract) -> CompetitionSignal:
        """
        Score competition type as indicator of targeted procurement.

        Sole source and limited competition indicate vendor was specifically
        targeted, suggesting prior relationship (stronger signal).

        Args:
            contract: FederalContract object

        Returns:
            CompetitionSignal with competition scoring
        """
        competition_type = contract.competition_type
        if not competition_type:
            return CompetitionSignal(competition_type=CompetitionType.OTHER, competition_score=0.0)

        competition_weight = self.competition_config.get("weight", 0.20)

        # Map competition type to bonus
        if competition_type == CompetitionType.SOLE_SOURCE:
            bonus = self.competition_config.get("sole_source_bonus", 0.20)
        elif competition_type == CompetitionType.LIMITED:
            bonus = self.competition_config.get("limited_competition_bonus", 0.10)
        elif competition_type == CompetitionType.FULL_AND_OPEN:
            bonus = self.competition_config.get("full_and_open_bonus", 0.0)
        else:
            # OTHER or unknown
            bonus = 0.0

        score = bonus * competition_weight

        return CompetitionSignal(
            competition_type=competition_type,
            competition_score=min(score, 1.0),
        )

    def score_patent_signal(
        self,
        patent_data: dict[str, Any] | None = None,
    ) -> PatentSignal:
        """
        Score patent-based commercialization signals.

        Patents indicate technology readiness and commercialization activity.
        Patents filed before contract and high topic similarity provide stronger signals.

        Args:
            patent_data: Optional patent information (count, pre_contract_count, similarity)

        Returns:
            PatentSignal with patent-based scoring
        """
        if not patent_data:
            return PatentSignal(patent_score=0.0)

        patent_count = patent_data.get("patent_count", 0)
        patents_pre_contract = patent_data.get("patents_pre_contract", 0)
        patent_topic_similarity = patent_data.get("patent_topic_similarity")

        patent_weight = self.patent_config.get("weight", 0.15)
        score = 0.0

        # Has patents bonus
        if patent_count > 0:
            has_patent_bonus = self.patent_config.get("has_patent_bonus", 0.05)
            score += has_patent_bonus

        # Patents filed before contract (readiness indicator)
        if patents_pre_contract > 0:
            pre_contract_bonus = self.patent_config.get("patent_pre_contract_bonus", 0.03)
            score += pre_contract_bonus

        # Topic similarity (if patent descriptions match contract/award)
        if patent_topic_similarity is not None:
            similarity_threshold = self.patent_config.get("patent_similarity_threshold", 0.7)
            if patent_topic_similarity >= similarity_threshold:
                topic_bonus = self.patent_config.get("patent_topic_match_bonus", 0.02)
                score += topic_bonus

        # Apply weight
        weighted_score = score * patent_weight

        return PatentSignal(
            patent_count=patent_count,
            patents_pre_contract=patents_pre_contract,
            patent_topic_similarity=patent_topic_similarity,
            patent_score=min(weighted_score, 1.0),
        )

    def score_cet_alignment(
        self,
        cet_data: dict[str, Any] | None = None,
    ) -> CETSignal:
        """
        Score CET (Critical & Emerging Technology) area alignment.

        Same CET area between award and contract suggests technology continuity.

        Args:
            cet_data: Optional CET alignment data

        Returns:
            CETSignal with alignment scoring
        """
        if not cet_data:
            return CETSignal(cet_alignment_score=0.0)

        award_cet = cet_data.get("award_cet")
        contract_cet = cet_data.get("contract_cet")

        if not award_cet or not contract_cet:
            return CETSignal(
                award_cet=award_cet, contract_cet=contract_cet, cet_alignment_score=0.0
            )

        # Normalize for comparison
        award_cet_norm = str(award_cet).upper().strip()
        contract_cet_norm = str(contract_cet).upper().strip()

        cet_weight = self.cet_config.get("weight", 0.10)

        if award_cet_norm == contract_cet_norm:
            # Exact match
            bonus = self.cet_config.get("same_cet_area_bonus", 0.05)
            score = bonus * cet_weight
        else:
            # Could implement "related" CET area logic here
            # For now, no bonus if not exact match
            score = 0.0

        return CETSignal(
            award_cet=award_cet,
            contract_cet=contract_cet,
            cet_alignment_score=min(score, 1.0),
        )

    def score_text_similarity(self, contract: FederalContract) -> float:
        """
        Score optional text similarity between award and contract descriptions.

        This is an optional signal that can be enabled/disabled via configuration.

        Args:
            contract: FederalContract object

        Returns:
            Weighted contribution to final score
        """
        similarity_score = contract.text_similarity_score
        if similarity_score is None:
            return 0.0

        # Check if text similarity is enabled in config
        text_config = self.config.get("scoring", {}).get("text_similarity", {})
        if not text_config.get("enabled", False):
            return 0.0

        weight = text_config.get("weight", 0.0)
        return min(similarity_score * weight, 1.0)

    def compute_final_score(self, signals: TransitionSignals) -> float:
        """
        Compute composite final score from all signals.

        Combines base score with weighted contributions from all enabled signals.

        Args:
            signals: TransitionSignals object with all signal scores

        Returns:
            Final likelihood score (0.0-1.0)
        """
        score = self.base_score

        # Add signal contributions
        if signals.agency and self.agency_config.get("enabled", True):
            score += signals.agency.agency_score

        if signals.timing and self.timing_config.get("enabled", True):
            score += signals.timing.timing_score

        if signals.competition and self.competition_config.get("enabled", True):
            score += signals.competition.competition_score

        if signals.patent and self.patent_config.get("enabled", True):
            score += signals.patent.patent_score

        if signals.cet and self.cet_config.get("enabled", True):
            score += signals.cet.cet_alignment_score

        if signals.text_similarity_score is not None:
            score += self.score_text_similarity(signals.text_similarity_score)

        # Ensure score is in valid range
        return min(max(score, 0.0), 1.0)

    def classify_confidence(self, likelihood_score: float) -> ConfidenceLevel:
        """
        Classify transition likelihood score into confidence band.

        Uses configured thresholds to categorize as HIGH, LIKELY, or POSSIBLE.

        Args:
            likelihood_score: Composite score (0.0-1.0)

        Returns:
            ConfidenceLevel enum value
        """
        if likelihood_score >= self.high_threshold:
            return ConfidenceLevel.HIGH
        elif likelihood_score >= self.likely_threshold:
            return ConfidenceLevel.LIKELY
        else:
            return ConfidenceLevel.POSSIBLE

    def score_transition(
        self,
        award_data: dict[str, Any],
        contract: FederalContract,
        patent_data: dict[str, Any] | None = None,
        cet_data: dict[str, Any] | None = None,
    ) -> TransitionSignals:
        """
        Convenience method to score all signals from input data dictionaries.

        Args:
            award_data: Award information (agency, completion_date, cet, etc.)
            contract: FederalContract object
            patent_data: Optional patent information (count, pre_contract_count, similarity)
            cet_data: Optional CET alignment data

        Returns:
            TransitionSignals object with all computed signals
        """
        # Score agency continuity
        agency_signal = self.score_agency_continuity(
            award_data=award_data,
            contract=contract,
        )

        # Score timing
        timing_signal = self.score_timing_proximity(
            award_data=award_data,
            contract=contract,
        )

        # Score competition type
        competition_signal = self.score_competition_type(contract)

        # Score patents
        patent_signal = self.score_patent_signal(patent_data)

        # Score CET alignment
        cet_signal = self.score_cet_alignment(cet_data)

        # Optional text similarity
        text_similarity = self.score_text_similarity(contract)

        return TransitionSignals(
            agency=agency_signal,
            timing=timing_signal,
            competition=competition_signal,
            patent=patent_signal,
            cet=cet_signal,
            text_similarity_score=text_similarity,
        )

    def score_and_classify(
        self,
        award_data: dict[str, Any],
        contract: FederalContract,
        patent_data: dict[str, Any] | None = None,
        cet_data: dict[str, Any] | None = None,
    ) -> tuple[TransitionSignals, float, ConfidenceLevel]:
        """
        End-to-end scoring: compute signals, final score, and confidence.

        Args:
            award_data: Award information
            contract: FederalContract object
            patent_data: Optional patent information
            cet_data: Optional CET alignment data

        Returns:
            Tuple of (signals, final_score, confidence_level)
        """
        signals = self.score_transition(award_data, contract, patent_data, cet_data)
        final_score = self.compute_final_score(signals)
        confidence = self.classify_confidence(final_score)

        return signals, final_score, confidence
