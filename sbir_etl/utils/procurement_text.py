"""Shared deterministic text signals for procurement-transition screening."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import pandas as pd


DIRECTED_LINEAGE_TERMS: tuple[str, ...] = (
    "phase iii",
    "phase 3",
    "derives from",
    "prototype transition",
    "follow-on production",
    "continuation of",
    "sole source",
    "notice of intent",
)

SCORING_LINEAGE_PHRASES: tuple[str, ...] = (
    "phase iii",
    "phase 3",
    "derives from",
    "extends",
    "completes",
    "prototype transition",
    "follow-on production",
    "continuation of",
    "technical data package",
    "interface control document",
    "source code",
    "government purpose rights",
    "unlimited rights",
)
PUBLIC_LINEAGE_PHRASES: tuple[str, ...] = tuple(
    dict.fromkeys((*SCORING_LINEAGE_PHRASES, *DIRECTED_LINEAGE_TERMS))
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "and",
        "or",
        "for",
        "to",
        "in",
        "on",
        "at",
        "with",
        "by",
        "is",
        "are",
        "be",
        "as",
        "this",
        "that",
        "these",
        "those",
        "from",
        "we",
        "our",
    }
)


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "nat", "none", "<na>"} else None


def tokenize_technical_text(text: Any) -> set[str]:
    """Return the content tokens used by procurement topical-similarity scoring."""

    normalized = _coerce_text(text)
    if normalized is None:
        return set()
    tokens = {match.group(0).lower() for match in _TOKEN_RE.finditer(normalized)}
    return {token for token in tokens if token not in _STOPWORDS and len(token) > 2}


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: Any) -> list[str]:
    """Split text into non-empty sentences on terminal punctuation."""

    normalized = _coerce_text(text)
    if normalized is None:
        return []
    return [
        sentence.strip() for sentence in _SENTENCE_SPLIT_RE.split(normalized) if sentence.strip()
    ]


def extract_connection_sentences(
    award_text: Any,
    opportunity_text: Any,
    *,
    min_shared: int = 3,
) -> tuple[str, str] | None:
    """Return the (award sentence, opportunity sentence) pair that best connects the texts.

    Picks the cross-pair sharing the most technical tokens, requiring at least
    ``min_shared``. Returns None when the award's best sentence is its leading
    sentence — that sentence is already displayed elsewhere, so quoting it again
    adds nothing. On multi-paragraph abstracts this surfaces the buried
    connecting claim.
    """

    award_sentences = split_sentences(award_text)
    opportunity_sentences = split_sentences(opportunity_text)
    if len(award_sentences) < 2 or not opportunity_sentences:
        return None

    award_tokens = [tokenize_technical_text(sentence) for sentence in award_sentences]
    opportunity_tokens = [tokenize_technical_text(sentence) for sentence in opportunity_sentences]

    best: tuple[int, int, int] | None = None  # (shared, opp_index, award_index)
    for opp_index, opp_toks in enumerate(opportunity_tokens):
        for award_index, award_toks in enumerate(award_tokens):
            shared = len(award_toks & opp_toks)
            if shared < min_shared:
                continue
            key = (shared, -opp_index, -award_index)
            if best is None or key > (best[0], -best[1], -best[2]):
                best = (shared, opp_index, award_index)
    if best is None or best[2] == 0:
        return None
    return award_sentences[best[2]], opportunity_sentences[best[1]]


# Display-oriented tokens: hyphenated terms ("electro-optical") stay whole so
# extracted phrases read as written. Scoring continues to use _TOKEN_RE.
_PHRASE_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")


def _ordered_tokens(text: Any) -> list[str]:
    normalized = _coerce_text(text)
    if normalized is None:
        return []
    return [match.group(0).lower() for match in _PHRASE_TOKEN_RE.finditer(normalized)]


def _candidate_grams(tokens: list[str], size: int) -> list[tuple[str, ...]]:
    grams: list[tuple[str, ...]] = []
    for start in range(len(tokens) - size + 1):
        gram = tuple(tokens[start : start + size])
        if any(token in _STOPWORDS for token in gram):
            continue
        if not any(len(token) > 2 for token in gram):
            continue
        grams.append(gram)
    return grams


def shared_technical_phrases(
    left_text: Any,
    right_text: Any,
    *,
    max_phrases: int = 6,
) -> list[str]:
    """Return multi-word technical phrases (2-3 grams) present in both texts.

    Phrases neither start nor end with a stopword; bigrams contained in a
    selected trigram are dropped; results follow first appearance in
    ``right_text``. Empty when the texts share no multi-word phrase — callers
    fall back to single-token overlap.
    """

    left_tokens = _ordered_tokens(left_text)
    right_tokens = _ordered_tokens(right_text)
    if not left_tokens or not right_tokens:
        return []

    selected: list[tuple[str, ...]] = []
    for size in (3, 2):
        left_grams = set(_candidate_grams(left_tokens, size))
        if not left_grams:
            continue
        for gram in _candidate_grams(right_tokens, size):  # right order preserved
            if gram not in left_grams or gram in selected:
                continue
            joined = f" {' '.join(gram)} "
            if any(joined in f" {' '.join(chosen)} " for chosen in selected):
                continue
            selected.append(gram)
    return [" ".join(gram) for gram in selected[:max_phrases]]


def find_lineage_phrases(
    text: Any,
    *,
    phrases: Iterable[str] = PUBLIC_LINEAGE_PHRASES,
) -> tuple[str, ...]:
    """Return distinct lineage phrases present in text, preserving vocabulary order."""

    normalized = _coerce_text(text)
    if normalized is None:
        return ()
    return tuple(
        phrase
        for phrase in phrases
        if re.search(r"\b" + re.escape(phrase) + r"\b", normalized, flags=re.IGNORECASE)
    )


__all__ = [
    "DIRECTED_LINEAGE_TERMS",
    "PUBLIC_LINEAGE_PHRASES",
    "SCORING_LINEAGE_PHRASES",
    "extract_connection_sentences",
    "find_lineage_phrases",
    "shared_technical_phrases",
    "split_sentences",
    "tokenize_technical_text",
]
