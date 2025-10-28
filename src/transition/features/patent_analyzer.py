"""
Patent Signal Extraction for Transition Detection.

This module analyzes patents filed by SBIR awardees to identify signals that
indicate Phase III commercialization through federal contracts. Patent signals
include timing (patents filed between award and contract), technology transfer
(different assignees), and topic similarity (patent content matches contract scope).
"""

from datetime import date, timedelta
from typing import Dict, List, Optional

from loguru import logger
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.models.patent import Patent
from src.models.transition_models import PatentSignal


class PatentSignalExtractor:
    """
    Extract patent-related signals for transition detection.

    Analyzes patents to determine if they provide evidence of technology
    development and commercialization between SBIR award completion and
    federal contract award.

    Key signals:
    1. Patent timing - Patents filed after SBIR but before contract
    2. Technology transfer - Patents assigned to different entity
    3. Topic similarity - Patent content related to contract work
    4. Patent count - Number of related patents (innovation activity)
    """

    def __init__(
        self,
        topic_similarity_threshold: float = 0.7,
        use_abstract: bool = True,
        use_title: bool = True,
    ):
        """
        Initialize patent signal extractor.

        Args:
            topic_similarity_threshold: Minimum cosine similarity for topic match (0-1)
            use_abstract: Include patent abstract in similarity calculation
            use_title: Include patent title in similarity calculation
        """
        self.topic_similarity_threshold = topic_similarity_threshold
        self.use_abstract = use_abstract
        self.use_title = use_title

        # TF-IDF vectorizer for topic similarity
        self.vectorizer = TfidfVectorizer(
            max_features=500,
            stop_words="english",
            ngram_range=(1, 2),
            lowercase=True,
        )

    def extract_signals(
        self,
        patents: List[Patent],
        award_completion_date: date,
        contract_start_date: date,
        contract_description: Optional[str] = None,
        award_description: Optional[str] = None,
        vendor_name: Optional[str] = None,
    ) -> PatentSignal:
        """
        Extract patent signals for a potential transition.

        Args:
            patents: List of patents associated with the company
            award_completion_date: When the SBIR award was completed
            contract_start_date: When the federal contract started
            contract_description: Contract description for topic matching
            award_description: Award description for additional context
            vendor_name: Vendor/company name to detect technology transfer

        Returns:
            PatentSignal with extracted metrics and scores
        """
        if not patents:
            return PatentSignal(
                patent_count=0,
                patents_pre_contract=0,
                patent_topic_similarity=None,
                patent_score=0.0,
            )

        # Filter patents filed in the relevant time window
        patents_in_window = self._filter_by_timing(
            patents,
            award_completion_date,
            contract_start_date,
        )

        # Count patents filed before contract start
        patents_pre_contract = len(
            [p for p in patents if p.filing_date and p.filing_date <= contract_start_date]
        )

        # Calculate topic similarity if contract description available
        topic_similarity = None
        if contract_description and (self.use_abstract or self.use_title):
            topic_similarity = self._calculate_topic_similarity(
                patents_in_window,
                contract_description,
                award_description,
            )

        # Detect potential technology transfer
        has_tech_transfer = self._detect_technology_transfer(
            patents_in_window,
            vendor_name,
        )

        # Calculate composite patent score
        patent_score = self._calculate_patent_score(
            patent_count=len(patents),
            patents_in_window=len(patents_in_window),
            patents_pre_contract=patents_pre_contract,
            topic_similarity=topic_similarity,
            has_tech_transfer=has_tech_transfer,
        )

        return PatentSignal(
            patent_count=len(patents),
            patents_pre_contract=patents_pre_contract,
            patent_topic_similarity=topic_similarity,
            patent_score=patent_score,
        )

    def _filter_by_timing(
        self,
        patents: List[Patent],
        award_completion_date: date,
        contract_start_date: date,
    ) -> List[Patent]:
        """
        Filter patents filed between award completion and contract start.

        This identifies patents that represent technology developed during
        or shortly after the SBIR award that may have led to the contract.

        Args:
            patents: All patents for the company
            award_completion_date: SBIR award completion
            contract_start_date: Contract start date

        Returns:
            Patents filed in the relevant window
        """
        patents_in_window = []

        for patent in patents:
            if not patent.filing_date:
                continue

            # Allow patents filed up to 6 months before award completion
            # (may have been filed during award execution)
            earliest_date = award_completion_date - timedelta(days=180)

            # Patents filed after contract starts are less relevant
            # (though may still show ongoing innovation)
            latest_date = contract_start_date + timedelta(days=90)

            if earliest_date <= patent.filing_date <= latest_date:
                patents_in_window.append(patent)

        logger.debug(
            f"Found {len(patents_in_window)} patents in timing window "
            f"({earliest_date} to {latest_date})"
        )

        return patents_in_window

    def _calculate_topic_similarity(
        self,
        patents: List[Patent],
        contract_description: str,
        award_description: Optional[str] = None,
    ) -> Optional[float]:
        """
        Calculate topic similarity between patents and contract.

        Uses TF-IDF vectorization and cosine similarity to determine if
        patent content is related to the contract work scope.

        Args:
            patents: Patents to analyze
            contract_description: Contract description text
            award_description: Optional award description for context

        Returns:
            Maximum cosine similarity score (0-1), or None if cannot calculate
        """
        if not patents or not contract_description:
            return None

        # Combine patent texts
        patent_texts = []
        for patent in patents:
            text_parts = []
            if self.use_title and patent.title:
                text_parts.append(patent.title)
            if self.use_abstract and patent.abstract:
                text_parts.append(patent.abstract)

            if text_parts:
                patent_texts.append(" ".join(text_parts))

        if not patent_texts:
            return None

        # Prepare contract text (optionally include award description)
        contract_texts = [contract_description]
        if award_description:
            contract_texts.append(award_description)
        combined_contract = " ".join(contract_texts)

        try:
            # Fit TF-IDF on all documents
            all_docs = patent_texts + [combined_contract]
            tfidf_matrix = self.vectorizer.fit_transform(all_docs)

            # Calculate similarity between each patent and contract
            # Contract is the last document
            contract_vector = tfidf_matrix[-1:]
            patent_vectors = tfidf_matrix[:-1]

            similarities = cosine_similarity(patent_vectors, contract_vector)
            max_similarity = float(similarities.max())

            logger.debug(
                f"Patent-contract topic similarity: {max_similarity:.3f} "
                f"(from {len(patents)} patents)"
            )

            return max_similarity

        except Exception as e:
            logger.warning(f"Failed to calculate topic similarity: {e}")
            return None

    def _detect_technology_transfer(
        self,
        patents: List[Patent],
        vendor_name: Optional[str],
    ) -> bool:
        """
        Detect if patents were assigned to a different entity (technology transfer).

        Technology transfer occurs when patents are assigned to an entity
        other than the SBIR awardee, indicating licensing or acquisition.

        Args:
            patents: Patents to analyze
            vendor_name: Expected assignee name (SBIR awardee)

        Returns:
            True if technology transfer detected
        """
        if not patents or not vendor_name:
            return False

        vendor_name_normalized = vendor_name.upper().strip()

        for patent in patents:
            if not patent.assignee:
                continue

            assignee_normalized = patent.assignee.upper().strip()

            # Simple name matching (could be enhanced with fuzzy matching)
            if vendor_name_normalized not in assignee_normalized:
                logger.debug(
                    f"Technology transfer detected: patent assigned to "
                    f"'{patent.assignee}' vs vendor '{vendor_name}'"
                )
                return True

        return False

    def _calculate_patent_score(
        self,
        patent_count: int,
        patents_in_window: int,
        patents_pre_contract: int,
        topic_similarity: Optional[float],
        has_tech_transfer: bool,
    ) -> float:
        """
        Calculate composite patent score.

        Combines multiple patent signals into a normalized score (0-1).

        Scoring components:
        - Has patents: 0.3 base score
        - Patents in timing window: 0.2
        - Patents filed before contract: 0.2
        - Topic similarity above threshold: 0.2
        - Technology transfer (reduces score): -0.1

        Args:
            patent_count: Total patents for company
            patents_in_window: Patents in relevant time window
            patents_pre_contract: Patents filed before contract
            topic_similarity: Topic similarity score (0-1)
            has_tech_transfer: Technology transfer detected

        Returns:
            Normalized patent score (0-1)
        """
        score = 0.0

        # Base score for having patents
        if patent_count > 0:
            score += 0.3

        # Bonus for patents in timing window
        if patents_in_window > 0:
            score += 0.2

        # Bonus for patents filed before contract
        if patents_pre_contract > 0:
            score += 0.2

        # Bonus for topic similarity
        if topic_similarity is not None and topic_similarity >= self.topic_similarity_threshold:
            score += 0.2

        # Penalty for technology transfer (suggests licensing rather than direct commercialization)
        if has_tech_transfer:
            score -= 0.1

        # Ensure score stays in [0, 1]
        return max(0.0, min(1.0, score))


__all__ = ["PatentSignalExtractor"]
