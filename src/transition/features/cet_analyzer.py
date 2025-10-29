"""
CET (Critical and Emerging Technologies) Signal Extraction for Transition Detection.

This module provides methods to extract CET area alignment signals between SBIR awards
and federal contracts, supporting technology-focused transition scoring.
"""

from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
import re

from ...models.transition_models import CETSignal


# CET Area Keyword Mappings
# Maps CET areas to keywords commonly found in contract descriptions
CET_KEYWORD_MAPPINGS = {
    "Artificial Intelligence": [
        "artificial intelligence",
        "machine learning",
        "neural network",
        "deep learning",
        "NLP",
        "computer vision",
        "AI/ML",
        "autonomous",
        "LLM",
    ],
    "Advanced Computing": [
        "quantum computing",
        "high-performance computing",
        "HPC",
        "parallel computing",
        "edge computing",
        "GPU",
        "TPU",
    ],
    "Biotechnology": [
        "biotechnology",
        "genetic engineering",
        "CRISPR",
        "gene therapy",
        "synthetic biology",
        "biomanufacturing",
        "biodefense",
        "vaccine",
    ],
    "Advanced Manufacturing": [
        "advanced manufacturing",
        "additive manufacturing",
        "3D printing",
        "nanotechnology",
        "precision manufacturing",
        "smart manufacturing",
        "Industry 4.0",
    ],
    "Quantum Information Science": [
        "quantum",
        "quantum sensing",
        "quantum communication",
        "quantum computing",
        "quantum cryptography",
        "entanglement",
    ],
    "Biotechnology and Biodefense": [
        "biodefense",
        "pandemic preparedness",
        "biosecurity",
        "pathogen detection",
        "medical countermeasures",
    ],
    "Microelectronics": [
        "microelectronics",
        "semiconductor",
        "chip design",
        "semiconductor manufacturing",
        "photonic",
        "RF electronics",
    ],
    "Hypersonics": [
        "hypersonic",
        "hypersonic vehicle",
        "thermal protection",
        "scramjet",
        "mach",
    ],
    "Space Technology": [
        "space",
        "satellite",
        "launch",
        "orbital",
        "spacecraft",
        "lunar",
        "deep space",
    ],
    "Climate Resilience": [
        "climate",
        "resilience",
        "sustainability",
        "renewable energy",
        "carbon capture",
        "green energy",
    ],
}


@dataclass
class CETAnalysisResult:
    """Result of CET area analysis."""

    award_cet: Optional[str]
    contract_cet: Optional[str]
    alignment_score: float
    confidence: str
    notes: Optional[str] = None


class CETSignalExtractor:
    """
    Extract CET (Critical and Emerging Technologies) signals for transition detection.

    Provides methods to:
    - Extract award CET classification
    - Infer contract CET from description
    - Calculate alignment between award and contract CET areas
    - Generate CET signal scores for transition likelihood
    """

    def __init__(self, cet_keyword_mappings: Optional[Dict[str, List[str]]] = None):
        """
        Initialize CET Signal Extractor.

        Args:
            cet_keyword_mappings: Optional custom keyword mappings for CET areas.
                                 Defaults to global CET_KEYWORD_MAPPINGS.
        """
        self.keyword_mappings = cet_keyword_mappings or CET_KEYWORD_MAPPINGS
        # Precompile regex patterns for efficiency
        self.compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> Dict[str, List]:
        """Precompile regex patterns for all CET keywords for efficiency."""
        compiled = {}
        for cet_area, keywords in self.keyword_mappings.items():
            patterns = []
            for keyword in keywords:
                # Create case-insensitive word boundary patterns
                pattern = re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)
                patterns.append(pattern)
            compiled[cet_area] = patterns
        return compiled

    def extract_award_cet(self, award_data: dict) -> Optional[str]:
        """
        Extract CET classification from award data.

        Looks for CET area in award fields:
        - cet_area
        - cet_code
        - technology_area
        - focus_area

        Args:
            award_data: Award dictionary or model instance

        Returns:
            CET area string if found, None otherwise
        """
        if not award_data:
            return None

        # Convert to dict if it's a Pydantic model
        if hasattr(award_data, "model_dump"):
            award_dict = award_data.model_dump()
        elif hasattr(award_data, "__dict__"):
            award_dict = award_data.__dict__
        else:
            award_dict = award_data

        # Check common field names for CET classification
        cet_field_names = [
            "cet_area",
            "cet_code",
            "technology_area",
            "focus_area",
            "research_area",
            "CET",
        ]

        for field_name in cet_field_names:
            value = award_dict.get(field_name) or award_dict.get(field_name.lower())
            if value and isinstance(value, str) and value.strip():
                return value.strip()

        return None

    def infer_contract_cet(
        self, contract_description: Optional[str]
    ) -> Tuple[Optional[str], float]:
        """
        Infer CET area from contract description using keyword matching.

        Performs case-insensitive keyword matching against CET area mappings.
        Returns the best-matching CET area and a confidence score based on
        keyword density.

        Args:
            contract_description: Contract description text

        Returns:
            Tuple of (cet_area, confidence_score) where confidence is 0.0-1.0
        """
        if not contract_description or not isinstance(contract_description, str):
            return None, 0.0

        description_lower = contract_description.lower()
        best_match = None
        best_score = 0.0

        for cet_area, patterns in self.compiled_patterns.items():
            match_count = 0
            for pattern in patterns:
                matches = pattern.findall(description_lower)
                match_count += len(matches)

            if match_count > 0:
                # Score based on keyword density (normalized by description length)
                # Cap at 1.0 to avoid inflating scores
                score = min(1.0, (match_count / (len(description_lower) / 100.0)))

                if score > best_score:
                    best_score = score
                    best_match = cet_area

        return best_match, best_score

    def calculate_alignment(self, award_cet: Optional[str], contract_cet: Optional[str]) -> float:
        """
        Calculate CET area alignment score between award and contract.

        Scores:
        - 1.0: Exact match (case-insensitive)
        - 0.5: Partial match (one area contains keywords from the other)
        - 0.0: No match or missing data

        Args:
            award_cet: Award CET area
            contract_cet: Contract CET area (inferred)

        Returns:
            Alignment score (0.0–1.0)
        """
        # Handle missing data
        if not award_cet or not contract_cet:
            return 0.0

        award_cet_norm = award_cet.strip().lower()
        contract_cet_norm = contract_cet.strip().lower()

        # Exact match
        if award_cet_norm == contract_cet_norm:
            return 1.0

        # Partial match (substring or shared keywords)
        if award_cet_norm in contract_cet_norm or contract_cet_norm in award_cet_norm:
            return 0.5

        return 0.0

    def extract_signal(
        self,
        award_data: dict,
        contract_description: Optional[str],
        weight: float = 0.10,
    ) -> CETSignal:
        """
        Extract complete CET signal for a transition candidate.

        Combines award CET extraction, contract CET inference, and alignment
        calculation into a single signal object.

        Args:
            award_data: Award dictionary or model instance
            contract_description: Contract description text
            weight: Weight of this signal in overall transition score (default: 0.10)

        Returns:
            CETSignal object with populated fields
        """
        award_cet = self.extract_award_cet(award_data)
        contract_cet, cet_confidence = self.infer_contract_cet(contract_description)
        alignment = self.calculate_alignment(award_cet, contract_cet)

        # Score contribution: alignment * weight
        cet_score = alignment * weight

        return CETSignal(
            award_cet=award_cet,
            contract_cet=contract_cet,
            cet_alignment_score=cet_score,
        )

    def batch_extract_signals(
        self,
        awards: List[dict],
        contracts: List[dict],
        weight: float = 0.10,
    ) -> List[Tuple[int, int, CETSignal]]:
        """
        Extract CET signals for multiple award-contract pairs.

        Args:
            awards: List of award dictionaries
            contracts: List of contract dictionaries with description fields
            weight: Weight of CET signal in overall score

        Returns:
            List of (award_idx, contract_idx, signal) tuples
        """
        signals = []

        for award_idx, award in enumerate(awards):
            for contract_idx, contract in enumerate(contracts):
                description = contract.get("description") if isinstance(contract, dict) else None
                signal = self.extract_signal(award, description, weight)
                signals.append((award_idx, contract_idx, signal))

        return signals

    def get_analysis_report(
        self, award_data: dict, contract_description: Optional[str]
    ) -> CETAnalysisResult:
        """
        Generate a detailed CET analysis report for a single award-contract pair.

        Useful for debugging and understanding CET area inference decisions.

        Args:
            award_data: Award dictionary or model instance
            contract_description: Contract description text

        Returns:
            CETAnalysisResult with detailed analysis information
        """
        award_cet = self.extract_award_cet(award_data)
        contract_cet, contract_confidence = self.infer_contract_cet(contract_description)
        alignment = self.calculate_alignment(award_cet, contract_cet)

        # Determine confidence classification
        if alignment == 1.0:
            confidence = "exact_match"
        elif alignment == 0.5:
            confidence = "partial_match"
        else:
            confidence = "no_match"

        notes = None
        if not award_cet:
            notes = "Award has no CET classification"
        elif not contract_cet:
            notes = "Contract description did not match any CET area keywords"
        elif alignment == 0.0:
            notes = f"Award CET ({award_cet}) does not align with inferred contract CET ({contract_cet})"

        return CETAnalysisResult(
            award_cet=award_cet,
            contract_cet=contract_cet,
            alignment_score=alignment,
            confidence=confidence,
            notes=notes,
        )


def create_cet_extractor(
    custom_keywords: Optional[Dict[str, List[str]]] = None,
) -> CETSignalExtractor:
    """
    Factory function to create a CETSignalExtractor instance.

    Args:
        custom_keywords: Optional custom CET keyword mappings

    Returns:
        Initialized CETSignalExtractor
    """
    return CETSignalExtractor(cet_keyword_mappings=custom_keywords)
