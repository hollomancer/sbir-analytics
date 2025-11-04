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
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass

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


def normalize_title(text: str | None) -> str:
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


def tokenize(text: str | None) -> list[str]:
    """
    Tokenize text into word tokens using a simple regex.

    Returns empty list for falsy input.
    """
    if not text:
        return []
    return [m.group(0) for m in _token_re.finditer(text)]


def remove_stopwords(tokens: Iterable[str], stopwords: Iterable[str] | None = None) -> list[str]:
    """
    Remove stopwords from an iterable of tokens.

    stopwords: iterable of lowercased tokens to drop. Defaults to DEFAULT_STOPWORDS.
    Also removes single alphabetic characters (but keeps numeric single characters).
    Returned tokens preserve original token order.
    """
    if tokens is None:
        return []
    sw = set(stopwords) if stopwords is not None else DEFAULT_STOPWORDS
    filtered = []
    for t in tokens:
        t_lower = t.lower()
        # Remove stopwords
        if t_lower in sw:
            continue
        # Remove single alphabetic characters (but keep numeric single chars like '3')
        if len(t) == 1 and t.isalpha():
            continue
        filtered.append(t)
    return filtered


def extract_ipc_cpc(
    metadata_or_text: str | Mapping[str, object] | None,
) -> dict[str, list[str]]:
    """
    Try to extract IPC/CPC codes from a metadata mapping or free text.

    Accepts:
    - A mapping with keys like "ipc", "ipc_codes", "cpc", "cpc_codes" whose values
      may be strings or iterables of strings.
    - A string containing potential IPC/CPC tokens (title/abstract).

    Returns dict with keys "ipc" and "cpc" mapping to lists (possibly empty).
    """
    ipc_list: list[str] = []
    cpc_list: list[str] = []

    if metadata_or_text is None:
        return {"ipc": ipc_list, "cpc": cpc_list}

    # If it's a mapping, probe common keys first.
    if isinstance(metadata_or_text, Mapping):
        for key in ("ipc", "ipc_codes", "ipc_code", "ipc_class"):
            if key in metadata_or_text and metadata_or_text[key]:
                raw = metadata_or_text[key]
                raw_list = _coerce_to_list_of_str(raw)
                ipc_list.extend(raw_list)
                # Also extract base classes from full codes (e.g., "G06F 17/30" -> "G06F")
                for code in raw_list:
                    # Extract base class if code contains a space (e.g., "G06F 17/30")
                    parts = code.split()
                    if parts:
                        base_class = parts[0].upper()
                        if base_class not in ipc_list:
                            ipc_list.append(base_class)
        for key in ("cpc", "cpc_codes", "cpc_code", "cpc_class"):
            if key in metadata_or_text and metadata_or_text[key]:
                raw = metadata_or_text[key]
                raw_list = _coerce_to_list_of_str(raw)
                cpc_list.extend(raw_list)
                # Also extract base classes from full codes (e.g., "G06F 17/30" -> "G06F")
                for code in raw_list:
                    # Extract base class if code contains a space (e.g., "G06F 17/30")
                    parts = code.split()
                    if parts:
                        base_class = parts[0].upper()
                        if base_class not in cpc_list:
                            cpc_list.append(base_class)

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


def _coerce_to_list_of_str(value: object) -> list[str]:
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
    if isinstance(value, list | tuple | set):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    # fallback
    return [str(value).strip()]


def _find_ipc_in_text(text: str) -> list[str]:
    """Extract IPC codes from text. Returns both base class (e.g., G06F) and full codes (e.g., G06F 17/30)."""
    codes = []
    for m in _ipc_token_re.finditer(text):
        base_class = m.group(1).upper()
        full_match = m.group(0).upper()
        # Add base class
        if base_class not in codes:
            codes.append(base_class)
        # Add full code if different from base class
        if full_match != base_class and full_match not in codes:
            codes.append(full_match)
    return codes


def _find_cpc_in_text(text: str) -> list[str]:
    """Extract CPC codes from text. Returns both base class (e.g., G06F) and full codes (e.g., G06F 17/30)."""
    codes = []
    for m in _cpc_token_re.finditer(text):
        base_class = m.group(1).upper()
        full_match = m.group(0).upper()
        # Add base class
        if base_class not in codes:
            codes.append(base_class)
        # Add full code if different from base class
        if full_match != base_class and full_match not in codes:
            codes.append(full_match)
    return codes


def _unique_preserve_order(items: Iterable[str]) -> list[str]:
    seen = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def guess_assignee_type(assignee: str | Sequence[str] | None) -> str:
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
        words = s.split()
        
        # Check for individual names first (short names, typically 2 words or less)
        # This must come before government check to avoid matching surnames like "Doe"
        if len(words) <= 2 and any(c.isalpha() for c in s):
            # Check if it's clearly NOT a government/academic/company entity
            has_corporate = any(
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
            )
            has_academic = any(
                k in s for k in ("univ", "university", "college", "institute", "school", "research")
            )
            # For "doe", only match if it's clearly a government reference (standalone or with "department")
            has_government = any(
                k in s
                for k in (
                    "department of",
                    "us government",
                    "government",
                    "national",
                    "nasa",
                    "nih",
                    "nhs",
                    "ministry",
                )
            ) or (s.strip() == "doe" or "department of energy" in s)
            if not (has_corporate or has_academic or has_government):
                return "individual"
        
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
        # "doe" as standalone or with "department of energy" context (not as surname)
        if s.strip() == "doe" or "department of energy" in s:
            return "government"
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
    text: str | None, keywords_map: Mapping[str, Sequence[str]] | None = None
) -> dict[str, int | float]:
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
    features: dict[str, int | float] = {}
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
    tokens: list[str]
    tokens_no_stopwords: list[str]
    n_tokens: int
    n_tokens_no_stopwords: int
    ipc_codes: list[str]
    cpc_codes: list[str]
    has_ipc: bool
    has_cpc: bool
    assignee_type: str
    keyword_features: dict[str, int | float]
    application_year: int | None

    def as_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
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
    record: Mapping[str, object] | None,
    *,
    keywords_map: Mapping[str, Sequence[str]] | None = None,
    stopwords: Iterable[str] | None = None,
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


# Simple keyword map loader helpers


def load_keywords_map(path: object | None = None) -> Mapping[str, Sequence[str]]:
    """
    Load a CET patent keywords map from YAML.

    Behavior:
    - If path is None, attempts to read 'config/cet/patent_keywords.yaml'.
    - Accepts either a flat mapping {group: [phrases]} or a nested mapping under 'cet_keywords'.
    - Returns an empty dict on any error (file missing, yaml missing).
    """
    try:
        # Local imports for import-safety
        from pathlib import Path  # type: ignore

        import yaml  # type: ignore
    except Exception:
        return {}

    # Resolve path
    if path is None:
        candidate = Path("config/cet/patent_keywords.yaml")
    else:
        candidate = Path(path) if not isinstance(path, Path) else path

    if not candidate.exists():
        return {}

    try:
        data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return {}
        # Allow both nested and flat schemas
        if "cet_keywords" in data and isinstance(data["cet_keywords"], dict):
            kw_map = data["cet_keywords"]
        else:
            kw_map = data
        # Coerce to mapping[str, list[str]]
        out: dict[str, list[str]] = {}
        for k, v in kw_map.items():
            if not k:
                continue
            if isinstance(v, str):
                out[str(k)] = [v]
            elif isinstance(v, list | tuple):
                out[str(k)] = [str(x) for x in v if x]
            else:
                # Fallback to string
                out[str(k)] = [str(v)]
        return out
    except Exception:
        return {}


def get_keywords_map(
    preferred: Mapping[str, Sequence[str]] | None = None,
) -> Mapping[str, Sequence[str]]:
    """
    Return a keywords_map to use for feature extraction:
    - If 'preferred' is provided and non-empty, return it.
    - Else, try to load from config via load_keywords_map().
    - Else, fall back to DEFAULT_KEYWORDS_MAP defined in this module.
    """
    if preferred:
        return preferred
    loaded = load_keywords_map()
    if loaded:
        return loaded
    return DEFAULT_KEYWORDS_MAP  # type: ignore


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
    "load_keywords_map",
    "get_keywords_map",
]
