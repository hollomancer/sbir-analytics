"""Versioned company-name policies with a single 0..1 similarity contract.

Epistemic tier: primitives. Profiles are frozen policies; normalization or
similarity behavior that changes output requires a new named profile
version, never an edit in place.

The profiles preserve current analytical behavior while making differences
explicit and reviewable. They are compatibility policies, not a claim that all
name-matching use cases should have identical recall. New consumers must select
a profile rather than silently inventing another normalization rule.
"""

import re
import unicodedata
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any

from sbir_etl.utils.coercion import _blank


try:
    from rapidfuzz import fuzz
    from rapidfuzz.distance import JaroWinkler
except ImportError:  # pragma: no cover - supported dependency-light fallback
    fuzz = None  # type: ignore[assignment]
    JaroWinkler = None  # type: ignore[assignment, misc]


EPISTEMIC_TIER = "primitives"


class CompanyNameProfile(StrEnum):
    """Named, versioned normalization behavior used by live consumers."""

    ORGANIZATION_KEY_V1 = "organization-key-v1"
    MATCHING_V1 = "matching-v1"
    RECIPIENT_V1 = "recipient-v1"
    ENTITY_RESOLUTION_V1 = "entity-resolution-v1"
    GROUNDTRUTH_V1 = "groundtruth-v1"
    VENDOR_CROSSWALK_V1 = "vendor-crosswalk-v1"
    VENDOR_KEY_V1 = "vendor-key-v1"
    VENDOR_RESOLVER_V1 = "vendor-resolver-v1"
    FORM_D_JOIN_V1 = "form-d-join-v1"
    UCC_V1 = "ucc-v1"
    SEC_EDGAR_V1 = "sec-edgar-v1"
    SEC_EDGAR_TRAILING_V1 = "sec-edgar-trailing-v1"
    NOTICE_KEY_V1 = "notice-key-v1"
    PHASE3_RANKING_V1 = "phase3-ranking-v1"


class CompanyNameMetric(StrEnum):
    """Supported similarity algorithms; every result is scaled to 0..1."""

    RATIO = "ratio"
    TOKEN_SET = "token-set"  # nosec B105 - matching algorithm name, not a credential
    TOKEN_SORT = "token-sort"  # nosec B105 - matching algorithm name, not a credential
    JARO_WINKLER = "jaro-winkler"


SUFFIX_TOKENS: frozenset[str] = frozenset(
    {
        "inc",
        "incorporated",
        "llc",
        "l.l.c",
        "l l c",
        "ltd",
        "limited",
        "corp",
        "corporation",
        "co",
        "lp",
        "llp",
        "company",
        "the",
    }
)

ENHANCED_ABBREVIATIONS = {
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
    "aerospace": "aero",
    "aeronautical": "aero",
    "defense": "def",
    "defence": "def",
    "military": "mil",
    "research": "res",
    "laboratory": "lab",
    "laboratories": "lab",
    "scientific": "sci",
    "science": "sci",
    "biotechnology": "biotech",
    "pharmaceutical": "pharma",
    "pharmaceuticals": "pharma",
    "manufacturing": "mfg",
    "manufacture": "mfg",
    "medical": "med",
    "communications": "comm",
    "communication": "comm",
    "telecommunications": "telecom",
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
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
    "northeast": "ne",
    "northwest": "nw",
    "southeast": "se",
    "southwest": "sw",
    "america": "amer",
    "american": "amer",
    "united": "utd",
    "group": "grp",
    "national": "natl",
}

_GROUNDTRUTH_SUFFIX = re.compile(
    r"\b(INC|INCORPORATED|LLC|L\.?L\.?C|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLP|PC|PLLC)\b\.?",
    re.IGNORECASE,
)
_PHASE3_RANKING_SUFFIX = re.compile(
    r"\b(INC|LLC|CORP\w*|CO|COMPANY|LTD|LP|LLP|PC|PLLC|INCORPORATED)\b\.?",
    re.IGNORECASE,
)
_NOTICE_SUFFIX = re.compile(
    r"\b(INC|INCORPORATED|LLC|CORP|CORPORATION|CO|COMPANY|LTD|LP)\b\.?",
    re.IGNORECASE,
)
_SEC_SUFFIX = re.compile(
    r",?\s*(Inc\.?|Corp\.?|LLC|Ltd\.?|Co\.?|L\.?P\.?|/DE|/NV|/MD|CORP|INC)$",
    re.IGNORECASE,
)
_DOTTED_DESIGNATORS = (
    (re.compile(r"\bp\s*\.\s*l\s*\.\s*l\s*\.\s*c\s*\.?", re.IGNORECASE), "pllc"),
    (re.compile(r"\bl\s*\.\s*l\s*\.\s*c\s*\.?", re.IGNORECASE), "llc"),
    (re.compile(r"\bl\s*\.\s*l\s*\.\s*p\s*\.?", re.IGNORECASE), "llp"),
    (re.compile(r"\bl\s*\.\s*p\s*\.?", re.IGNORECASE), "lp"),
    (re.compile(r"\bp\s*\.\s*c\s*\.?", re.IGNORECASE), "pc"),
)
_TRAILING_DESIGNATOR_PHRASES = (
    ("professional", "limited", "liability", "company"),
    ("limited", "liability", "company"),
    ("limited", "liability", "partnership"),
)
_TRAILING_DESIGNATORS = frozenset(
    {
        "co",
        "company",
        "corp",
        "corporation",
        "inc",
        "incorporated",
        "incorporation",
        "llc",
        "llp",
        "lp",
        "ltd",
        "limited",
        "pc",
        "plc",
        "pllc",
    }
)


def _matching_v1(
    value: Any,
    *,
    remove_suffixes: bool,
    abbreviations: dict[str, str] | None,
) -> str:
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]", " ", text)
    if remove_suffixes:
        text = re.sub(
            r"\b(incorporated|incorporation|inc|corp|corporation|llc|llp|lp|ltd|limited"
            r"|plc|liability|partnership|co|company)\b",
            "",
            text,
        )
    else:
        text = re.sub(r"\b(incorporated|incorporation)\b", "inc", text)
        text = re.sub(r"\b(company|co)\b", "company", text)
        text = re.sub(r"\b(limited|ltd)\b", "ltd", text)
    if abbreviations:
        text = " ".join(abbreviations.get(token, token) for token in text.split())
    return " ".join(text.split())


def _organization_key_v1(value: Any) -> str:
    """Build a comparison key by removing only trailing legal designators."""
    text = unicodedata.normalize("NFKD", str(value).strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    for pattern, replacement in _DOTTED_DESIGNATORS:
        text = pattern.sub(replacement, text)
    tokens = re.sub(r"[^a-z0-9\s]", " ", text).split()
    while len(tokens) > 1:
        phrase = next(
            (
                candidate
                for candidate in _TRAILING_DESIGNATOR_PHRASES
                if len(tokens) > len(candidate) and tuple(tokens[-len(candidate) :]) == candidate
            ),
            None,
        )
        if phrase is not None:
            del tokens[-len(phrase) :]
            continue
        if tokens[-1] in _TRAILING_DESIGNATORS:
            tokens.pop()
            continue
        break
    return " ".join(tokens).upper()


def normalize_company_name(
    value: Any,
    *,
    profile: CompanyNameProfile,
    abbreviations: dict[str, str] | None = None,
) -> str:
    """Normalize ``value`` using an explicit, versioned company-name profile."""

    if _blank(value):
        return ""
    if profile is CompanyNameProfile.ORGANIZATION_KEY_V1:
        return _organization_key_v1(value)
    if profile is CompanyNameProfile.MATCHING_V1:
        return _matching_v1(value, remove_suffixes=False, abbreviations=abbreviations)
    if profile is CompanyNameProfile.RECIPIENT_V1:
        return _matching_v1(value, remove_suffixes=True, abbreviations=abbreviations)

    text = str(value)
    if profile is CompanyNameProfile.ENTITY_RESOLUTION_V1:
        text = text.upper().strip()
        for suffix in (" INC", " LLC", " LP", " LLP", " CORP", " CO", " LTD", " PLC"):
            if text.endswith(suffix):
                text = text[: -len(suffix)]
        text = text.rstrip(",. ")
        text = re.sub(r"[^A-Z0-9\s]", "", text)
        return " ".join(text.split())
    if profile is CompanyNameProfile.GROUNDTRUTH_V1:
        text = _GROUNDTRUTH_SUFFIX.sub(" ", text.upper())
        return " ".join(re.sub(r"[^A-Z0-9 ]", " ", text).split())
    if profile is CompanyNameProfile.VENDOR_CROSSWALK_V1:
        text = " ".join(text.strip().split())
        return (
            text.replace(",", " ").replace(".", " ").replace("/", " ").replace("&", " AND ").strip()
        )
    if profile in {
        CompanyNameProfile.VENDOR_KEY_V1,
        CompanyNameProfile.VENDOR_RESOLVER_V1,
    }:
        text = " ".join(text.strip().split())
        text = text.replace(",", " ").replace(".", " ").replace("/", " ").replace("&", " AND ")
        aliases = {
            "incorporated": "inc",
            "inc": "inc",
            "corporation": "corp",
            "corp": "corp",
            "company": "co",
            "co": "co",
            "limited": "ltd",
            "ltd": "ltd",
            "llc": "llc",
            "llp": "llp",
        }
        return " ".join(aliases.get(token, token) for token in text.lower().split())
    if profile is CompanyNameProfile.FORM_D_JOIN_V1:
        return " ".join(text.strip().upper().split())
    if profile is CompanyNameProfile.UCC_V1:
        text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
        replacements = abbreviations or ENHANCED_ABBREVIATIONS
        text = " ".join(replacements.get(token, token) for token in text.split())
        return " ".join(token for token in text.split() if token not in SUFFIX_TOKENS)
    if profile in {
        CompanyNameProfile.SEC_EDGAR_V1,
        CompanyNameProfile.SEC_EDGAR_TRAILING_V1,
    }:
        text = text.strip().upper()
        iterations = 3 if profile is CompanyNameProfile.SEC_EDGAR_V1 else 1
        for _ in range(iterations):
            cleaned = _SEC_SUFFIX.sub("", text).strip()
            if cleaned == text:
                break
            text = cleaned
        return text
    if profile is CompanyNameProfile.NOTICE_KEY_V1:
        text = _NOTICE_SUFFIX.sub("", text)
        return re.sub(r"[^A-Z0-9]", "", text.upper())
    if profile is CompanyNameProfile.PHASE3_RANKING_V1:
        text = _PHASE3_RANKING_SUFFIX.sub(" ", text.upper())
        return " ".join(re.sub(r"[^A-Z0-9 ]", " ", text).split())
    raise ValueError(f"unsupported company-name profile: {profile}")


def _fallback_token_set(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    intersection = " ".join(sorted(left_tokens & right_tokens))
    left_joined = " ".join(sorted(left_tokens))
    right_joined = " ".join(sorted(right_tokens))
    return max(
        SequenceMatcher(None, intersection, left_joined).ratio(),
        SequenceMatcher(None, intersection, right_joined).ratio(),
        SequenceMatcher(None, left_joined, right_joined).ratio(),
    )


def _raw_name(value: Any) -> str:
    return "" if _blank(value) else str(value)


def company_name_similarity(
    left: Any,
    right: Any,
    *,
    metric: CompanyNameMetric,
    profile: CompanyNameProfile | None = None,
    prefix_weight: float = 0.1,
) -> float:
    """Return company-name similarity on a stable 0..1 scale."""

    left_text = normalize_company_name(left, profile=profile) if profile else _raw_name(left)
    right_text = normalize_company_name(right, profile=profile) if profile else _raw_name(right)
    if not left_text or not right_text:
        return 0.0
    if fuzz is not None:
        scorers = {
            CompanyNameMetric.RATIO: fuzz.ratio,
            CompanyNameMetric.TOKEN_SET: fuzz.token_set_ratio,
            CompanyNameMetric.TOKEN_SORT: fuzz.token_sort_ratio,
        }
        if metric in scorers:
            return float(scorers[metric](left_text, right_text)) / 100.0
    if metric is CompanyNameMetric.JARO_WINKLER and JaroWinkler is not None:
        return float(JaroWinkler.similarity(left_text, right_text, prefix_weight=prefix_weight))
    if metric is CompanyNameMetric.TOKEN_SET:
        return _fallback_token_set(left_text, right_text)
    if metric is CompanyNameMetric.TOKEN_SORT:
        left_text = " ".join(sorted(left_text.split()))
        right_text = " ".join(sorted(right_text.split()))
    return float(SequenceMatcher(None, left_text, right_text).ratio())


def _rapidfuzz_100(left: Any, right: Any, metric: CompanyNameMetric, **kwargs: Any) -> float:
    score = company_name_similarity(left, right, metric=metric) * 100.0
    score_cutoff = kwargs.get("score_cutoff")
    return 0.0 if score_cutoff is not None and score < float(score_cutoff) else score


def rapidfuzz_token_set_100(left: Any, right: Any, **kwargs: Any) -> float:
    """RapidFuzz-compatible token-set scorer backed by the shared contract."""

    return _rapidfuzz_100(left, right, CompanyNameMetric.TOKEN_SET, **kwargs)


def rapidfuzz_token_sort_100(left: Any, right: Any, **kwargs: Any) -> float:
    """RapidFuzz-compatible token-sort scorer backed by the shared contract."""

    return _rapidfuzz_100(left, right, CompanyNameMetric.TOKEN_SORT, **kwargs)


def rapidfuzz_ratio_100(left: Any, right: Any, **kwargs: Any) -> float:
    """RapidFuzz-compatible ratio scorer backed by the shared contract."""

    return _rapidfuzz_100(left, right, CompanyNameMetric.RATIO, **kwargs)


def rapidfuzz_jaro_winkler_100(
    left: Any,
    right: Any,
    *,
    prefix_weight: float = 0.1,
    **kwargs: Any,
) -> float:
    """RapidFuzz-compatible Jaro-Winkler scorer backed by the shared contract."""

    score = (
        company_name_similarity(
            left,
            right,
            metric=CompanyNameMetric.JARO_WINKLER,
            prefix_weight=prefix_weight,
        )
        * 100.0
    )
    score_cutoff = kwargs.get("score_cutoff")
    return 0.0 if score_cutoff is not None and score < float(score_cutoff) else score
