"""
Patent feature extractor helpers.

This module provides lightweight, dependency-free utilities to extract simple
text and metadata features from patent records for use in training or inference
pipelines. It's intentionally small and import-safe for unit tests and CI.

Key functions:
- normalize_title(text)
- tokenize(text)
- remove_stopwords(tokens, stopwords=None)
- extract_ipc_cpc(metadata_or_text)
- guess_assignee_type(assignee)
- bag_of_keywords_features(text, keywords_map=None)
- extract_features(record, *, keywords_map=None, stopwords=None)

Record shape expected by `extract_features`:
- dict-like with optional keys: "title", "abstract", "assignees",
  "ipc", "cpc", "application_year", "assignee" (singular).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple, Union

# Simple default English stopwords (small subset) to keep import-free and deterministic.
DEFAULT_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "with",
        "we",
        "their",
        "they",
        "were",
        "was",
        "which",
        "such",
    ]
)

# Default keywords_map used as example; callers should supply domain-specific maps.
# Keys are feature names; values are lists of keywords or phrases associated with each feature.
DEFAULT_KEYWORDS_MAP: Mapping[str, Sequence[str]] = {
    "machine_learning": ["machine learning", "deep learning", "neural network", "ml model"],
    "quantum": ["quantum", "qubit", "quantum computing", "quantum information"],
    "battery": ["battery", "lithium", "anode", "cathode"],
    "biotech": ["protein", "enzyme", "antibody", "biological", "biotech"],
    "semiconductor": ["semiconductor", "transistor", "mosfet", "integrated circuit"],
}


_nonword_re = re.compile(r"[^\w\s]", flags=re.UNICODE)
_token_re = re.compile(r"\b\w+\b", flags=re.UNICODE)
_ipc_token_re = re.compile(
    r"\b([A-H]\d{2}[A-Z])(?:\s*\d{1,4}\/\d{1,4})?\b", flags=re.IGNORECASE
)  # captures e.g. G06F 17/30 or G06F
_cpc_token_re = re.compile(
    r"\b([A-Z]{1}\d{2}[A-Z])(?:\s*\d{1,4}\/\d{1,4})?\b", flags=re.IGNORECASE
)  # CPC has similar format


def normalize_title(text: Optional[str]) -> str:
    """
    Normalize a patent title or short text.

    - Convert to lowercase
    - Remove punctuation (non-word characters)
    - Collapse whitespace
    - Strip leading/trailing whitespace

    Returns empty string for falsy input.
    """
    if not text:
        return ""
    s = str(text).lower()
    s = _nonword_re.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokenize(text: Optional[str]) -> List[str]:
    """
    Tokenize text into word tokens using a simple regex.

    Returns empty list for falsy input.
    """
    if not text:
        return []
    return [m.group(0) for m in _token_re.finditer(text)]


def remove_stopwords(tokens: Iterable[str], stopwords: Optional[Iterable[str]] = None) -> List[str]:
    """
    Remove stopwords from an iterable of tokens.

    stopwords: iterable of lowercased tokens to drop. Defaults to DEFAULT_STOPWORDS.
    Returned tokens preserve original token order.
    """
    if tokens is None:
        return []
    sw = set(stopwords) if stopwords is not None else DEFAULT_STOPWORDS
    return [t for t in tokens if t.lower() not in sw]


def extract_ipc_cpc(
    metadata_or_text: Optional[Union[str, Mapping[str, object]]],
) -> Dict[str, List[str]]:
    """
    Try to extract IPC/CPC codes from a metadata mapping or free text.

    Accepts:
    - A mapping with keys like "ipc", "ipc_codes", "cpc", "cpc_codes" whose values
      may be strings or iterables of strings.
    - A string containing potential IPC/CPC tokens (title/abstract).

    Returns dict with keys "ipc" and "cpc" mapping to lists (possibly empty).
    """
    ipc_list: List[str] = []
    cpc_list: List[str] = []

    if metadata_or_text is None:
        return {"ipc": ipc_list, "cpc": cpc_list}

    # If it's a mapping, probe common keys first.
    if isinstance(metadata_or_text, Mapping):
        for key in ("ipc", "ipc_codes", "ipc_code", "ipc_class"):
            if key in metadata_or_text and metadata_or_text[key]:
                raw = metadata_or_text[key]
                ipc_list.extend(_coerce_to_list_of_str(raw))
        for key in ("cpc", "cpc_codes", "cpc_code", "cpc_class"):
            if key in metadata_or_text and metadata_or_text[key]:
                raw = metadata_or_text[key]
                cpc_list.extend(_coerce_to_list_of_str(raw))

        # If not found in keys, try scanning a 'description' or 'title' field.
        if not ipc_list and "description" in metadata_or_text:
            ipc_list.extend(_find_ipc_in_text(str(metadata_or_text["description"])))
        if not cpc_list and "description" in metadata_or_text:
            cpc_list.extend(_find_cpc_in_text(str(metadata_or_text["description"])))

        if not ipc_list and "title" in metadata_or_text:
            ipc_list.extend(_find_ipc_in_text(str(metadata_or_text["title"])))
        if not cpc_list and "title" in metadata_or_text:
            cpc_list.extend(_find_cpc_in_text(str(metadata_or_text["title"])))
    else:
        # Treat as free text
        txt = str(metadata_or_text)
        ipc_list.extend(_find_ipc_in_text(txt))
        cpc_list.extend(_find_cpc_in_text(txt))

    # Normalize: uppercase and unique preserving order
    ipc_list = _unique_preserve_order([i.upper() for i in ipc_list])
    cpc_list = _unique_preserve_order([c.upper() for c in cpc_list])

    return {"ipc": ipc_list, "cpc": cpc_list}


def _coerce_to_list_of_str(value: object) -> List[str]:
    """
    Convert a value to a list of string tokens. Accepts:
    - str: split on common delimiters
    - iterable: coerce each to str
    """
    if value is None:
        return []
    if isinstance(value, str):
        # split common delimiters: comma, semicolon, pipe, whitespace
        parts = re.split(r"[,;|\n\r]+|\s{2,}", value)
        return [p.strip() for p in parts if p and p.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    # fallback
    return [str(value).strip()]


def _find_ipc_in_text(text: str) -> List[str]:
    return [m.group(1) for m in _ipc_token_re.finditer(text)]


def _find_cpc_in_text(text: str) -> List[str]:
    return [m.group(1) for m in _cpc_token_re.finditer(text)]


def _unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def guess_assignee_type(assignee: Optional[Union[str, Sequence[str]]]) -> str:
    """
    Heuristic to guess assignee type.

    Returns one of: "company", "academic", "government", "individual", "unknown"

    Input can be a single string or a sequence of strings. If sequence is provided
    we return the most frequent guess among entries; ties resolve to 'company'.
    """
    if not assignee:
        return "unknown"

    # Normalize to list of strings
    if isinstance(assignee, str):
        names = [assignee]
    else:
        names = [str(x) for x in assignee if x is not None]

    def _guess_one(name: str) -> str:
        s = name.lower()
        if any(
            k in s for k in ("univ", "university", "college", "institute", "school", "research")
        ):
            return "academic"
        if any(
            k in s
            for k in (
                "inc",
                "llc",
                "ltd",
                "corporation",
                "corp",
                "co.",
                "company",
                "technologies",
                "systems",
            )
        ):
            return "company"
        if any(
            k in s
            for k in (
                "department of",
                "doe",
                "us government",
                "government",
                "national",
                "nasa",
                "nih",
                "nhs",
                "ministry",
            )
        ):
            return "government"
        if len(s.split()) <= 2 and any(c.isalpha() for c in s):
            # short names without corporate tokens could be individuals
            return "individual"
        return "company"

    guesses = [_guess_one(n) for n in names]
    # Choose the most common guess
    counts: MutableMapping[str, int] = {}
    for g in guesses:
        counts[g] = counts.get(g, 0) + 1
    # Sort by count desc then by preference order
    pref = ["company", "academic", "government", "individual", "unknown"]
    sorted_guesses = sorted(
        counts.items(), key=lambda kv: (-kv[1], pref.index(kv[0]) if kv[0] in pref else 999)
    )
    return sorted_guesses[0][0] if sorted_guesses else "unknown"


def bag_of_keywords_features(
    text: Optional[str], keywords_map: Optional[Mapping[str, Sequence[str]]] = None
) -> Dict[str, Union[int, float]]:
    """
    Compute simple bag-of-keywords features.

    For each key in keywords_map, counts occurrences of any of the associated
    phrases (case-insensitive, phrase match). Returns a dict with keys:
      - "<key>__count": integer count of occurrences
      - "<key>__presence": 0 or 1 indicating if any occurrence found

    If keywords_map is None, DEFAULT_KEYWORDS_MAP is used.
    """
    if not text:
        text = ""
    if keywords_map is None:
        keywords_map = DEFAULT_KEYWORDS_MAP

    txt = text.lower()
    features: Dict[str, Union[int, float]] = {}
    for feat_name, phrases in keywords_map.items():
        count = 0
        for ph in phrases:
            if not ph:
                continue
            # Overlapping matches allowed; use simple substring count for reproducibility
            count += txt.count(ph.lower())
        features[f"{feat_name}__count"] = int(count)
        features[f"{feat_name}__presence"] = 1 if count > 0 else 0
    return features


@dataclass
class PatentFeatureVector:
    """
    Container for extracted features from a single patent record.

    Fields are intentionally simple Python types for easy serialization/pickling.
    """

    normalized_title: str
    tokens: List[str]
    tokens_no_stopwords: List[str]
    n_tokens: int
    n_tokens_no_stopwords: int
    ipc_codes: List[str]
    cpc_codes: List[str]
    has_ipc: bool
    has_cpc: bool
    assignee_type: str
    keyword_features: Dict[str, Union[int, float]]
    application_year: Optional[int]

    def as_dict(self) -> Dict[str, object]:
        d: Dict[str, object] = {
            "normalized_title": self.normalized_title,
            "tokens": self.tokens,
            "tokens_no_stopwords": self.tokens_no_stopwords,
            "n_tokens": self.n_tokens,
            "n_tokens_no_stopwords": self.n_tokens_no_stopwords,
            "ipc_codes": self.ipc_codes,
            "cpc_codes": self.cpc_codes,
            "has_ipc": self.has_ipc,
            "has_cpc": self.has_cpc,
            "assignee_type": self.assignee_type,
            "keyword_features": self.keyword_features,
            "application_year": self.application_year,
        }
        return d


def extract_features(
    record: Optional[Mapping[str, object]],
    *,
    keywords_map: Optional[Mapping[str, Sequence[str]]] = None,
    stopwords: Optional[Iterable[str]] = None,
) -> PatentFeatureVector:
    """
    Extract a bundle of lightweight features from a patent record.

    record: mapping-like object. Common keys:
      - "title" (preferred)
      - "abstract"
      - "description"
      - "assignees" or "assignee"
      - "ipc" / "cpc" or other metadata

    Returns a PatentFeatureVector instance.

    This function is deterministic and import-safe for unit tests.
    """
    # Defensive defaults
    if record is None:
        record = {}

    title = ""
    # Prefer explicit title keys
    for k in ("title", "invention_title", "name"):
        if k in record and record[k]:
            title = str(record[k])
            break
    if not title and "abstract" in record and record["abstract"]:
        title = str(record["abstract"])[0:512]  # use a short slice of the abstract

    normalized = normalize_title(title)
    tokens = tokenize(normalized)
    tokens_no_sw = remove_stopwords(tokens, stopwords=stopwords)

    ipc_cpc = extract_ipc_cpc(record)
    ipc_codes = ipc_cpc.get("ipc", [])
    cpc_codes = ipc_cpc.get("cpc", [])

    assignee_field = None
    for key in ("assignees", "assignee", "assignee_name"):
        if key in record and record[key]:
            assignee_field = record[key]
            break

    assignee_guess = guess_assignee_type(assignee_field)

    # Keyword features are computed over title + abstract if present
    text_for_keywords = normalized
    if "abstract" in record and record["abstract"]:
        text_for_keywords = f"{text_for_keywords} {normalize_title(str(record['abstract']))}"

    kw_feats = bag_of_keywords_features(text_for_keywords, keywords_map=keywords_map)

    # Application year extract (best-effort)
    app_year = None
    for k in ("application_year", "year", "filing_year", "publication_year"):
        if k in record and record[k]:
            try:
                app_year = int(record[k])
                break
            except Exception:
                # ignore parse errors
                pass

    pfv = PatentFeatureVector(
        normalized_title=normalized,
        tokens=tokens,
        tokens_no_stopwords=tokens_no_sw,
        n_tokens=len(tokens),
        n_tokens_no_stopwords=len(tokens_no_sw),
        ipc_codes=ipc_codes,
        cpc_codes=cpc_codes,
        has_ipc=bool(ipc_codes),
        has_cpc=bool(cpc_codes),
        assignee_type=assignee_guess,
        keyword_features=kw_feats,
        application_year=app_year,
    )
    return pfv


# Expose useful names
__all__ = [
    "normalize_title",
    "tokenize",
    "remove_stopwords",
    "extract_ipc_cpc",
    "guess_assignee_type",
    "bag_of_keywords_features",
    "PatentFeatureVector",
    "extract_features",
    "DEFAULT_KEYWORDS_MAP",
    "DEFAULT_STOPWORDS",
]
