"""
Evidence extraction for CET classifications.

Extracts supporting text excerpts from documents to explain why a particular
CET classification was assigned. Uses spaCy for sentence segmentation and
keyword matching to identify relevant passages.

Features:
- Sentence-level text segmentation
- CET keyword matching
- 50-word excerpt truncation
- Source location tracking (abstract, keywords, solicitation)
- Rationale tag generation
- Evidence ranking (top 3 most relevant)
"""

from typing import Any

from loguru import logger

from src.exceptions import ValidationError
from src.models.cet_models import CETArea, EvidenceStatement


try:
    import spacy
    from spacy.language import Language
except ImportError:
    spacy: Any | None = None
    Language: Any | None = None
    logger.warning("spaCy not available; evidence extraction will be limited")


class EvidenceExtractor:
    """
    Extracts evidence statements supporting CET classifications.

    Uses spaCy for sentence segmentation and keyword matching to identify
    relevant text excerpts that explain why a classification was made.
    """

    def __init__(self, cet_areas: list[CETArea], config: dict[str, Any]):
        """
        Initialize evidence extractor.

        Args:
            cet_areas: List of CET technology areas
            config: Configuration dictionary from classification.yaml
        """
        self.cet_areas = cet_areas
        self.config = config

        # Build CET keyword mapping
        self.cet_keywords = {area.cet_id: area.keywords for area in cet_areas}

        # Build reverse lookup: keyword -> CET IDs
        self.keyword_to_cets: dict[str, list[str]] = {}
        for cet_id, keywords in self.cet_keywords.items():
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower not in self.keyword_to_cets:
                    self.keyword_to_cets[keyword_lower] = []
                self.keyword_to_cets[keyword_lower].append(cet_id)

        # Evidence extraction config
        evidence_config = config.get("evidence", {})
        self.max_statements = evidence_config.get("max_statements", 3)
        self.excerpt_max_words = evidence_config.get("excerpt_max_words", 50)
        self.min_keyword_matches = evidence_config.get("min_keyword_matches", 1)
        self.source_priority = evidence_config.get(
            "source_priority", ["abstract", "keywords", "solicitation", "title"]
        )

        # Initialize spaCy
        self.nlp: Language | None = None
        # Initialize spaCy at runtime if the spacy module is present. Tests may patch the
        # module-level `spacy` variable to simulate availability, so evaluate at init time.
        if spacy is not None:
            try:
                self._initialize_spacy(evidence_config.get("spacy", {}))
            except Exception:
                # If initialization fails for any reason, keep nlp as None and fall back
                # to the simple extractor.
                self.nlp = None

        logger.info(
            f"Initialized EvidenceExtractor: {len(self.cet_keywords)} CET areas, "
            f"{len(self.keyword_to_cets)} keywords"
        )

    def _initialize_spacy(self, spacy_config: dict[str, Any]) -> None:
        """
        Initialize spaCy language model.

        Args:
            spacy_config: spaCy configuration from config
        """
        model_name = spacy_config.get("model", "en_core_web_sm")
        disable = spacy_config.get("disable", ["ner", "parser"])

        try:
            self.nlp = spacy.load(model_name, disable=disable)

            # Enable sentencizer if not already enabled
            if "sentencizer" not in self.nlp.pipe_names:
                self.nlp.add_pipe("sentencizer")

            logger.info(f"Loaded spaCy model: {model_name}")
        except Exception as e:
            logger.error(f"Failed to load spaCy model {model_name}: {e}")
            self.nlp = None

    def extract_evidence(
        self,
        cet_id: str,
        document_parts: dict[str, str],
    ) -> list[EvidenceStatement]:
        """
        Extract evidence statements for a specific CET area.

        Args:
            cet_id: CET area identifier
            document_parts: Dictionary mapping source locations to text
                           (e.g., {"abstract": "...", "keywords": "...", "solicitation": "..."})

        Returns:
            List of EvidenceStatement objects (up to max_statements)
        """
        if spacy is None or self.nlp is None:
            logger.debug("spaCy not available or model not loaded; using simple extraction")
            return self._simple_extraction(cet_id, document_parts)

        # Get CET keywords
        cet_keywords_list = self.cet_keywords.get(cet_id, [])
        if not cet_keywords_list:
            logger.warning(f"No keywords found for CET area: {cet_id}")
            return []

        cet_keywords_lower = [k.lower() for k in cet_keywords_list]

        # Extract candidate sentences from each source
        candidates: list[
            tuple[str, str, list[str], int]
        ] = []  # (sentence, source, keywords, score)

        for source in self.source_priority:
            text = document_parts.get(source, "")
            if not text:
                continue

            # Segment into sentences
            sentences = self._segment_sentences(text)

            # Find sentences with CET keywords
            for sentence in sentences:
                matched_keywords = self._find_keywords(sentence, cet_keywords_lower)

                if len(matched_keywords) >= self.min_keyword_matches:
                    # Score based on number of keyword matches
                    score = len(matched_keywords)
                    candidates.append((sentence, source, matched_keywords, score))

        # Rank candidates by score (descending)
        candidates.sort(key=lambda x: x[3], reverse=True)

        # Take top N candidates
        top_candidates = candidates[: self.max_statements]

        # Convert to EvidenceStatement objects
        evidence_statements = []
        for sentence, source, keywords, _score in top_candidates:
            excerpt = self._truncate_excerpt(sentence)
            rationale = self._generate_rationale(keywords)

            evidence_statements.append(
                EvidenceStatement(
                    excerpt=excerpt,
                    source_location=source,
                    rationale_tag=rationale,
                )
            )

        logger.debug(
            f"Extracted {len(evidence_statements)} evidence statements for {cet_id} "
            f"from {len(candidates)} candidates"
        )

        return evidence_statements

    def _segment_sentences(self, text: str) -> list[str]:
        """
        Segment text into sentences using spaCy.

        Args:
            text: Input text

        Returns:
            List of sentence strings
        """
        if not self.nlp:
            # Fallback: split on periods
            return [s.strip() for s in text.split(".") if s.strip()]

        doc = self.nlp(text)
        sentences = [sent.text.strip() for sent in doc.sents]
        return sentences

    def _find_keywords(self, text: str, keywords: list[str]) -> list[str]:
        """
        Find CET keywords present in text.

        Args:
            text: Text to search
            keywords: List of keywords (lowercase)

        Returns:
            List of matched keywords
        """
        text_lower = text.lower()
        matched = []

        for keyword in keywords:
            # Check for whole word matches (avoid partial matches like "ai" in "iais")
            # Simple approach: check if keyword appears as standalone word
            if (
                f" {keyword} " in f" {text_lower} "
                or text_lower.startswith(f"{keyword} ")
                or text_lower.endswith(f" {keyword}")
            ):
                matched.append(keyword)

        return matched

    def _truncate_excerpt(self, text: str) -> str:
        """
        Truncate text to approximately max_words.

        Args:
            text: Input text

        Returns:
            Truncated text with ellipsis if needed
        """
        words = text.split()

        if len(words) <= self.excerpt_max_words:
            return text

        # Truncate and add ellipsis
        truncated = " ".join(words[: self.excerpt_max_words])
        return f"{truncated}..."

    def _generate_rationale(self, keywords: list[str]) -> str:
        """
        Generate rationale tag explaining why excerpt is relevant.

        Args:
            keywords: List of matched keywords

        Returns:
            Rationale string
        """
        if not keywords:
            return "Relevant to technology area"

        # Format: "Contains: keyword1, keyword2, keyword3"
        keywords_str = ", ".join(keywords[:5])  # Limit to 5 keywords
        return f"Contains: {keywords_str}"

    def _simple_extraction(
        self, cet_id: str, document_parts: dict[str, str]
    ) -> list[EvidenceStatement]:
        """
        Simple evidence extraction when spaCy is not available.

        Falls back to basic text splitting and keyword matching.

        Args:
            cet_id: CET area identifier
            document_parts: Document text parts

        Returns:
            List of EvidenceStatement objects
        """
        cet_keywords_list = self.cet_keywords.get(cet_id, [])
        if not cet_keywords_list:
            return []

        cet_keywords_lower = [k.lower() for k in cet_keywords_list]

        evidence_statements = []

        for source in self.source_priority:
            text = document_parts.get(source, "")
            if not text:
                continue

            # Simple sentence split on periods
            sentences = [s.strip() for s in text.split(".") if s.strip()]

            for sentence in sentences:
                matched = self._find_keywords(sentence, cet_keywords_lower)

                if len(matched) >= self.min_keyword_matches:
                    excerpt = self._truncate_excerpt(sentence)
                    rationale = self._generate_rationale(matched)

                    evidence_statements.append(
                        EvidenceStatement(
                            excerpt=excerpt,
                            source_location=source,
                            rationale_tag=rationale,
                        )
                    )

                    # Stop if we have enough
                    if len(evidence_statements) >= self.max_statements:
                        return evidence_statements

        return evidence_statements

    def extract_batch_evidence(
        self,
        classifications_list: list[list[Any]],  # List of CETClassification lists
        document_parts_list: list[dict[str, str]],
    ) -> list[list[Any]]:
        """
        Extract evidence for a batch of classifications.

        Args:
            classifications_list: List of lists of CETClassification objects
            document_parts_list: List of document_parts dictionaries

        Returns:
            List of classification lists with evidence populated
        """
        if len(classifications_list) != len(document_parts_list):
            raise ValidationError(
                "classifications and document_parts_list must have same length",
                component="ml.evidence_extractor",
                operation="extract_batch_evidence",
                details={
                    "classifications_length": len(classifications_list),
                    "document_parts_length": len(document_parts_list),
                },
            )

        logger.info(f"Extracting evidence for {len(classifications_list)} classifications")

        results = []

        for classifications, document_parts in zip(
            classifications_list, document_parts_list, strict=False
        ):
            # Process each classification in the list
            updated_classifications = []
            for classification in classifications:
                # Extract evidence for this CET
                evidence = self.extract_evidence(classification.cet_id, document_parts)

                # Update classification with evidence
                updated = classification.model_copy(update={"evidence": evidence})
                updated_classifications.append(updated)

            results.append(updated_classifications)

        return results

    def get_statistics(self) -> dict[str, Any]:
        """Get extractor statistics."""
        return {
            "num_cet_areas": len(self.cet_areas),
            "num_keywords": len(self.keyword_to_cets),
            "max_statements": self.max_statements,
            "excerpt_max_words": self.excerpt_max_words,
            "min_keyword_matches": self.min_keyword_matches,
            "source_priority": self.source_priority,
            "spacy_available": spacy is not None,
            "spacy_model_loaded": self.nlp is not None,
        }
