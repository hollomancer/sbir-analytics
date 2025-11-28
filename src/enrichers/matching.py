"""Enhanced matching utilities for company and researcher name matching.

This module provides advanced name matching capabilities including:
1. Phonetic matching (Metaphone, Double Metaphone)
2. Jaro-Winkler distance for prefix-weighted matching
3. Enhanced abbreviation dictionary for normalization
4. ORCID-first researcher matching strategy

All features can be enabled/disabled via configuration.
"""

from __future__ import annotations

from typing import Any


try:
    import jellyfish
except ImportError:  # pragma: no cover
    jellyfish = None  # type: ignore

try:
    from rapidfuzz.distance import JaroWinkler
except ImportError:  # pragma: no cover
    JaroWinkler = None  # type: ignore


# Enhanced abbreviation dictionary for company name normalization
ENHANCED_ABBREVIATIONS = {
    # Technology terms
    "technologies": "tech",
    "technology": "tech",
    "systems": "sys",
    "system": "sys",
    "solutions": "sol",
    "solution": "sol",
    "software": "sw",
    "engineering": "eng",
    "engineer": "eng",
    "development": "dev",
    "developer": "dev",
    "advanced": "adv",
    "international": "intl",
    # Aerospace & Defense
    "aerospace": "aero",
    "aeronautical": "aero",
    "defense": "def",
    "defence": "def",
    "military": "mil",
    # Research & Science
    "research": "res",
    "laboratory": "lab",
    "laboratories": "lab",
    "scientific": "sci",
    "science": "sci",
    # Industry-specific
    "biotechnology": "biotech",
    "pharmaceutical": "pharma",
    "pharmaceuticals": "pharma",
    "manufacturing": "mfg",
    "manufacture": "mfg",
    "medical": "med",
    "communications": "comm",
    "communication": "comm",
    "telecommunications": "telecom",
    # Business terms
    "associates": "assoc",
    "associate": "assoc",
    "consulting": "consult",
    "consultants": "consult",
    "services": "svc",
    "service": "svc",
    "enterprises": "ent",
    "enterprise": "ent",
    "industries": "ind",
    "industry": "ind",
    "management": "mgmt",
    # Directional
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
    "northeast": "ne",
    "northwest": "nw",
    "southeast": "se",
    "southwest": "sw",
    # Common words
    "america": "amer",
    "american": "amer",
    "united": "utd",
    "group": "grp",
    "national": "natl",
}


def get_phonetic_code(name: str, algorithm: str = "metaphone") -> str | None:
    """Get phonetic encoding of a name.

    Args:
        name: Name to encode
        algorithm: Phonetic algorithm to use. Options:
                  - "metaphone": Single Metaphone code
                  - "double_metaphone": Double Metaphone (returns primary code)
                  - "soundex": Soundex code

    Returns:
        Phonetic code string, or None if jellyfish is not available or name is empty

    Examples:
        >>> get_phonetic_code("Smith", "metaphone")
        'SM0'
        >>> get_phonetic_code("Smyth", "metaphone")
        'SM0'
    """
    if not jellyfish or not name:
        return None

    name_clean = str(name).strip()
    if not name_clean:
        return None

    # Define valid algorithms
    valid_algorithms = {"metaphone", "double_metaphone", "soundex"}
    if algorithm not in valid_algorithms:
        return None

    try:
        if algorithm == "metaphone":
            return jellyfish.metaphone(name_clean)
        elif algorithm == "double_metaphone":
            # Use match_rating_codex as it provides a phonetic code similar to double metaphone
            return jellyfish.match_rating_codex(name_clean)
        elif algorithm == "soundex":
            return jellyfish.soundex(name_clean)
    except Exception:  # pragma: no cover
        return None

    return None


def phonetic_match(name1: str, name2: str, algorithm: str = "metaphone") -> bool:
    """Check if two names match phonetically.

    Args:
        name1: First name
        name2: Second name
        algorithm: Phonetic algorithm to use (see get_phonetic_code)

    Returns:
        True if phonetic codes match, False otherwise

    Examples:
        >>> phonetic_match("Smith Technologies", "Smyth Technologies")
        True
        >>> phonetic_match("Acme Corp", "Ecma Corp")
        True
    """
    if not jellyfish or not name1 or not name2:
        return False

    code1 = get_phonetic_code(name1, algorithm)
    code2 = get_phonetic_code(name2, algorithm)

    return code1 is not None and code1 == code2


def jaro_winkler_similarity(name1: str, name2: str, prefix_weight: float = 0.1) -> float:
    """Calculate Jaro-Winkler similarity between two names.

    Jaro-Winkler gives extra weight to matching prefixes, making it
    particularly good for company names where the first word is often
    most distinctive.

    Args:
        name1: First name
        name2: Second name
        prefix_weight: Weight given to matching prefix (0.0-0.25)

    Returns:
        Similarity score from 0.0 to 100.0 (scaled to match RapidFuzz convention)

    Examples:
        >>> jaro_winkler_similarity("Boeing Systems", "Boeing Solutions")
        > 85.0  # High due to matching "Boeing" prefix
    """
    if not JaroWinkler or not name1 or not name2:
        return 0.0

    try:
        # JaroWinkler.similarity returns 0.0-1.0, scale to 0-100
        score = JaroWinkler.similarity(str(name1), str(name2), prefix_weight=prefix_weight)
        return score * 100.0
    except Exception:  # pragma: no cover
        return 0.0


def apply_enhanced_abbreviations(name: str, abbreviations: dict[str, str] | None = None) -> str:
    """Apply enhanced abbreviation dictionary to normalize a name.

    Args:
        name: Name to normalize
        abbreviations: Custom abbreviation dict, or None to use default ENHANCED_ABBREVIATIONS

    Returns:
        Name with abbreviations applied

    Examples:
        >>> apply_enhanced_abbreviations("Acme Technologies International")
        'acme tech intl'
        >>> apply_enhanced_abbreviations("Advanced Aerospace Defense Systems")
        'adv aero def sys'
    """
    if not name:
        return ""

    if abbreviations is None:
        abbreviations = ENHANCED_ABBREVIATIONS

    s = str(name).lower().strip()
    tokens = s.split()

    # Apply abbreviations token by token
    normalized_tokens = []
    for token in tokens:
        normalized = abbreviations.get(token, token)
        normalized_tokens.append(normalized)

    return " ".join(normalized_tokens)


class MatchingConfig:
    """Configuration for enhanced matching features."""

    def __init__(self, config_dict: dict[str, Any] | None = None):
        """Initialize matching configuration from dictionary.

        Args:
            config_dict: Configuration dictionary with keys:
                - enable_phonetic_matching: bool (default: False)
                - phonetic_algorithm: str (default: "metaphone")
                - enable_jaro_winkler: bool (default: False)
                - jaro_winkler_prefix_weight: float (default: 0.1)
                - jaro_winkler_threshold: int (default: 90)
                - enable_enhanced_abbreviations: bool (default: False)
                - custom_abbreviations: dict (default: None)
        """
        if config_dict is None:
            config_dict = {}

        self.enable_phonetic_matching = config_dict.get("enable_phonetic_matching", False)
        self.phonetic_algorithm = config_dict.get("phonetic_algorithm", "metaphone")

        self.enable_jaro_winkler = config_dict.get("enable_jaro_winkler", False)
        self.jaro_winkler_prefix_weight = config_dict.get("jaro_winkler_prefix_weight", 0.1)
        self.jaro_winkler_threshold = config_dict.get("jaro_winkler_threshold", 90)

        self.enable_enhanced_abbreviations = config_dict.get("enable_enhanced_abbreviations", False)
        self.custom_abbreviations = config_dict.get("custom_abbreviations", None)

    def get_abbreviations(self) -> dict[str, str]:
        """Get the abbreviations dictionary to use.

        Returns merged dictionary of default + custom abbreviations.
        """
        if not self.enable_enhanced_abbreviations:
            return {}

        abbrev = ENHANCED_ABBREVIATIONS.copy()
        if self.custom_abbreviations:
            abbrev.update(self.custom_abbreviations)

        return abbrev


class ResearcherMatcher:
    """Researcher matching with ORCID-first strategy."""

    def __init__(self, config_dict: dict[str, Any] | None = None):
        """Initialize researcher matcher.

        Args:
            config_dict: Configuration dictionary with keys:
                - enable_orcid_matching: bool (default: True)
                - enable_email_matching: bool (default: True)
                - enable_affiliation_matching: bool (default: True)
                - orcid_confidence: int (default: 100)
                - email_confidence: int (default: 95)
                - affiliation_confidence: int (default: 80)
        """
        if config_dict is None:
            config_dict = {}

        self.enable_orcid_matching = config_dict.get("enable_orcid_matching", True)
        self.enable_email_matching = config_dict.get("enable_email_matching", True)
        self.enable_affiliation_matching = config_dict.get("enable_affiliation_matching", True)

        self.orcid_confidence = config_dict.get("orcid_confidence", 100)
        self.email_confidence = config_dict.get("email_confidence", 95)
        self.affiliation_confidence = config_dict.get("affiliation_confidence", 80)

    def match_researcher(
        self,
        query_researcher: dict[str, Any],
        candidate_researcher: dict[str, Any],
    ) -> tuple[bool, int, str]:
        """Match two researcher records using identifier-first strategy.

        Matching hierarchy:
        1. ORCID (if enabled) - 100% confidence
        2. Email (if enabled) - 95% confidence
        3. Affiliation + Last Name (if enabled) - 80% confidence

        Args:
            query_researcher: Query researcher dict with keys: orcid, email, name, affiliation
            candidate_researcher: Candidate researcher dict with same keys

        Returns:
            Tuple of (matched: bool, confidence: int, method: str)

        Examples:
            >>> matcher = ResearcherMatcher()
            >>> query = {"orcid": "0000-0001-2345-6789", "name": "John Smith"}
            >>> candidate = {"orcid": "0000-0001-2345-6789", "name": "J. Smith"}
            >>> matched, confidence, method = matcher.match_researcher(query, candidate)
            >>> matched, confidence, method
            (True, 100, 'orcid-exact')
        """
        # ORCID matching (highest priority)
        if self.enable_orcid_matching:
            query_orcid = self._normalize_orcid(query_researcher.get("orcid", ""))
            cand_orcid = self._normalize_orcid(candidate_researcher.get("orcid", ""))

            if query_orcid and cand_orcid and query_orcid == cand_orcid:
                return (True, self.orcid_confidence, "orcid-exact")

        # Email matching
        if self.enable_email_matching:
            query_email = self._normalize_email(query_researcher.get("email", ""))
            cand_email = self._normalize_email(candidate_researcher.get("email", ""))

            if query_email and cand_email and query_email == cand_email:
                return (True, self.email_confidence, "email-exact")

        # Affiliation + Last Name matching
        if self.enable_affiliation_matching:
            query_name = query_researcher.get("name", "")
            cand_name = candidate_researcher.get("name", "")
            query_affiliation = query_researcher.get("affiliation", "")
            cand_affiliation = candidate_researcher.get("affiliation", "")

            if all([query_name, cand_name, query_affiliation, cand_affiliation]):
                query_last = self._extract_last_name(query_name)
                cand_last = self._extract_last_name(cand_name)
                query_aff_norm = self._normalize_affiliation(query_affiliation)
                cand_aff_norm = self._normalize_affiliation(cand_affiliation)

                if (
                    query_last
                    and cand_last
                    and query_last.lower() == cand_last.lower()
                    and query_aff_norm
                    and cand_aff_norm
                    and query_aff_norm == cand_aff_norm
                ):
                    return (True, self.affiliation_confidence, "affiliation-lastname")

        return (False, 0, "no-match")

    @staticmethod
    def _normalize_orcid(orcid: str) -> str:
        """Normalize ORCID to standard format (digits only)."""
        if not orcid:
            return ""
        # Extract only digits from ORCID
        return "".join(c for c in str(orcid) if c.isdigit())

    @staticmethod
    def _normalize_email(email: str) -> str:
        """Normalize email address (lowercase, strip)."""
        if not email:
            return ""
        return str(email).strip().lower()

    @staticmethod
    def _extract_last_name(full_name: str) -> str:
        """Extract last name from full name.

        Handles formats like:
        - "John Smith" -> "Smith"
        - "Smith, John" -> "Smith"
        - "Dr. John Smith Jr." -> "Smith"
        """
        if not full_name:
            return ""

        name = str(full_name).strip()

        # Handle "Last, First" format
        if "," in name:
            return name.split(",")[0].strip()

        # Handle "First Last" format - take last token excluding suffixes
        suffixes = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "dr", "dr.", "prof", "prof."}
        tokens = name.split()
        if tokens:
            # Filter out suffixes and titles
            name_tokens = [t for t in tokens if t.lower() not in suffixes]
            if name_tokens:
                return name_tokens[-1]

        return ""

    @staticmethod
    def _normalize_affiliation(affiliation: str) -> str:
        """Normalize affiliation for matching."""
        if not affiliation:
            return ""

        aff = str(affiliation).lower().strip()

        # Remove common words
        remove_words = {
            "university",
            "of",
            "the",
            "college",
            "institute",
            "laboratory",
            "department",
        }

        tokens = aff.split()
        filtered = [t for t in tokens if t not in remove_words]

        return " ".join(filtered) if filtered else aff
